"""MEXC Futures client — auth bằng u_id (web token).

Signature scheme (đã verify từ source bot khác):
    g    = md5(u_id + timestamp).hexdigest()[7:]
    sign = md5(timestamp + body_json + g).hexdigest()

Headers: Authorization=u_id, x-mxc-nonce=timestamp, x-mxc-sign=sign

Dùng curl_cffi với impersonate="chrome" để vượt Akamai 403.
"""
import time
import json
import hashlib
import requests
from typing import Optional

try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    HAS_CFFI = False
    print("[WARN] curl_cffi chưa được cài, có thể bị 403 Akamai")

PUBLIC_BASE = "https://contract.mexc.com"
SECRET_BASE = "https://futures.mexc.com/api/v1"


class MexcClient:
    def __init__(self, api_key: str = "", api_secret: str = "",
                 uid: str = "", proxy: str = ""):
        # api_key/api_secret giữ lại cho tương thích, không dùng
        self.api_key = api_key
        self.api_secret = api_secret
        self.uid = (uid or "").strip()
        self.proxy = (proxy or "").strip()

        # Session cho public endpoints (dùng requests bình thường được)
        self.session = requests.Session()
        if self.proxy:
            self.session.proxies = {"http": self.proxy, "https": self.proxy}

        self._contract_cache: dict = {}
        self._cache_time: float = 0

    # ---------------- Signature ----------------
    def _sign(self, ts: str, payload: dict) -> str:
        g = hashlib.md5((self.uid + ts).encode()).hexdigest()[7:]
        body_json = json.dumps(payload, separators=(',', ':'))
        return hashlib.md5((ts + body_json + g).encode()).hexdigest()

    def _headers(self, ts: str, sign: str) -> dict:
        return {
            "accept": "*/*",
            "authorization": self.uid,
            "content-type": "application/json",
            "x-mxc-nonce": ts,
            "x-mxc-sign": sign,
            "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
            "origin": "https://futures.mexc.com",
            "referer": "https://futures.mexc.com/",
        }

    def _private_request(self, method: str, endpoint: str,
                         payload: dict = None, params: dict = None) -> dict:
        if not self.uid:
            return {"success": False, "message": "Missing UID (web token)"}

        ts = str(int(time.time() * 1000))
        if payload is None:
            payload = {}
        sign = self._sign(ts, payload)
        headers = self._headers(ts, sign)
        url = f"{SECRET_BASE}{endpoint}"
        body = json.dumps(payload, separators=(',', ':')) if payload else "{}"

        try:
            if HAS_CFFI:
                proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
                if method == "GET":
                    r = cffi_requests.get(url, headers=headers, params=params,
                                          impersonate="chrome",
                                          proxies=proxies, timeout=15)
                else:
                    r = cffi_requests.post(url, headers=headers, data=body,
                                           impersonate="chrome",
                                           proxies=proxies, timeout=15)
            else:
                if method == "GET":
                    r = self.session.get(url, headers=headers, params=params, timeout=15)
                else:
                    r = self.session.post(url, headers=headers, data=body, timeout=15)

            try:
                return r.json()
            except Exception:
                return {"success": False,
                        "message": f"HTTP {r.status_code}: {r.text[:300]}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ---------------- Public ----------------
    def get_all_contracts(self, force_refresh: bool = False) -> list:
        if not force_refresh and self._contract_cache and (time.time() - self._cache_time) < 300:
            return list(self._contract_cache.values())
        try:
            r = self.session.get(f"{PUBLIC_BASE}/api/v1/contract/detail", timeout=10)
            data = r.json()
            if data.get("success"):
                contracts = data.get("data", [])
                self._contract_cache = {c["symbol"]: c for c in contracts}
                self._cache_time = time.time()
                return contracts
        except Exception as e:
            print(f"[MEXC] get_all_contracts lỗi: {e}")
        return []

    def has_symbol(self, base_coin: str) -> Optional[str]:
        if not self._contract_cache:
            self.get_all_contracts()
        target = f"{base_coin.upper()}_USDT"
        if target in self._contract_cache:
            c = self._contract_cache[target]
            if c.get("state", 0) == 0:
                return target
        return None

    def get_ticker_price(self, symbol: str) -> Optional[float]:
        try:
            r = self.session.get(f"{PUBLIC_BASE}/api/v1/contract/ticker",
                                 params={"symbol": symbol}, timeout=5)
            data = r.json()
            if data.get("success"):
                d = data.get("data", {})
                return float(d.get("lastPrice", 0)) or None
        except Exception as e:
            print(f"[MEXC] get_ticker_price lỗi: {e}")
        return None

    def get_contract_detail(self, symbol: str) -> Optional[dict]:
        if not self._contract_cache:
            self.get_all_contracts()
        return self._contract_cache.get(symbol)

    # ---------------- Private ----------------
    def get_assets(self) -> dict:
        return self._private_request("GET", "/private/account/assets")

    def get_positions(self) -> list:
        r = self._private_request("GET", "/private/position/open_positions")
        if r.get("success") and r.get("data"):
            d = r["data"]
            return d if isinstance(d, list) else [d]
        return []

    def get_trigger_orders(self, symbol: str = None) -> list:
        params = {"symbol": symbol} if symbol else None
        r = self._private_request("GET", "/private/planorder/list/orders", params=params)
        if r.get("success") and r.get("data"):
            d = r["data"]
            return d if isinstance(d, list) else [d]
        return []

    def cancel_trigger_order(self, order_id, symbol: str) -> dict:
        # MEXC nhận list các order trigger để cancel
        return self._private_request("POST", "/private/planorder/cancel",
                                     [{"orderId": str(order_id), "symbol": symbol}])

    def cancel_all_triggers(self, symbol: str) -> dict:
        return self._private_request("POST", "/private/planorder/cancel_all",
                                     {"symbol": symbol})

    def close_position(self, symbol: str, position_id=None) -> dict:
        """Đóng vị thế bằng market (reduce-only). Nếu có position_id MEXC dùng /position/close."""
        # Lấy position
        positions = self.get_positions()
        pos = None
        for p in positions:
            if p.get("symbol") == symbol:
                if position_id is None or str(p.get("positionId")) == str(position_id):
                    pos = p
                    break
        if not pos:
            return {"success": False, "message": f"Không tìm thấy vị thế {symbol}"}

        position_type = pos.get("positionType")  # 1=long, 2=short
        hold_vol = pos.get("holdVol") or pos.get("vol") or 0
        leverage = pos.get("leverage", 10)
        open_type = pos.get("openType", 1)
        if not hold_vol:
            return {"success": False, "message": "holdVol = 0"}

        # Close LONG = side 3, Close SHORT = side 2 (reduceOnly)
        side = 3 if position_type == 1 else 2
        order_res = self.place_order(
            symbol=symbol, side=side, vol=hold_vol, leverage=leverage,
            order_type=5, open_type=open_type, reduce_only=True,
        )

        # Cancel toàn bộ trigger còn lại của symbol
        cancel_res = self.cancel_all_triggers(symbol)

        return {
            "success": order_res.get("success", False),
            "close_order": order_res,
            "cancel_triggers": cancel_res,
        }

    def set_leverage(self, symbol: str, leverage: int, open_type: int = 1) -> dict:
        return self._private_request("POST", "/private/position/change_leverage", {
            "symbol": symbol,
            "leverage": leverage,
            "openType": open_type,
        })

    def place_order(self, symbol: str, side: int, vol, leverage: int,
                    order_type: int = 5, price: str = "0",
                    open_type: int = 1, reduce_only: bool = False) -> dict:
        payload = {
            "symbol": symbol,
            "side": side,                 # 1=Open Long, 2=Close Short, 3=Open Short, 4=Close Long
            "type": order_type,           # 5 = Market
            "vol": str(vol),
            "openType": open_type,        # 1=isolated, 2=cross
            "leverage": leverage,
            "price": str(price),
            "positionMode": 1,
        }
        if reduce_only:
            payload["reduceOnly"] = True
        return self._private_request("POST", "/private/order/create", payload)

    def open_long(self, symbol: str, vol, leverage: int, open_type: int = 1) -> dict:
        return self.place_order(symbol, 1, vol, leverage, open_type=open_type)

    def place_trigger_order(self, symbol: str, side: int, vol, trigger_price: float,
                            trigger_type: int, leverage: int, open_type: int = 1) -> dict:
        """trigger_type: 1 = price>=trigger (TP-LONG / SL-SHORT)
                         2 = price<=trigger (SL-LONG / TP-SHORT)"""
        return self._private_request("POST", "/private/planorder/place", {
            "symbol": symbol,
            "side": side,
            "vol": str(vol),
            "triggerPrice": str(trigger_price),
            "triggerType": trigger_type,
            "orderType": 5,
            "openType": open_type,
            "leverage": leverage,
            "executeCycle": 1,
            "trend": trigger_type,
            "reduceOnly": True,
        })

    # ---------------- Helpers ----------------
    def calculate_volume(self, symbol: str, usdt_size: float, price: float, leverage: int) -> int:
        c = self.get_contract_detail(symbol)
        if not c:
            return 0
        contract_size = float(c.get("contractSize", 0)) or 0
        if contract_size <= 0 or price <= 0:
            return 0
        vol = (usdt_size * leverage) / (price * contract_size)
        return max(1, int(vol))

    def round_price(self, symbol: str, price: float) -> float:
        c = self.get_contract_detail(symbol)
        if not c:
            return price
        unit = float(c.get("priceUnit", 0)) or 0
        if unit <= 0:
            return price
        return round(round(price / unit) * unit, 10)

    def execute_long_signal(self, base_coin: str, usdt_size: float, leverage: int,
                            tp_percent: float, sl_percent: float,
                            margin_type: str = "isolated") -> dict:
        symbol = self.has_symbol(base_coin)
        if not symbol:
            return {"success": False, "message": f"{base_coin} không có trên MEXC futures"}

        price = self.get_ticker_price(symbol)
        if not price:
            return {"success": False, "message": f"Không lấy được giá {symbol}"}

        open_type = 1 if margin_type == "isolated" else 2
        vol = self.calculate_volume(symbol, usdt_size, price, leverage)
        if vol <= 0:
            return {"success": False, "message": "Volume = 0, kiểm tra contract size"}

        # Set leverage (có thể fail nếu đã set sẵn, không sao)
        self.set_leverage(symbol, leverage, open_type)

        order = self.open_long(symbol, vol, leverage, open_type)
        if not order.get("success"):
            return {"success": False,
                    "message": f"Long fail: {order.get('message', order.get('code'))}",
                    "order": order}

        tp_price = self.round_price(symbol, price * (1 + tp_percent / 100))
        sl_price = self.round_price(symbol, price * (1 - sl_percent / 100))

        # Close LONG = side 3 với reduceOnly=True (đúng theo MEXC web)
        # TP-LONG: price >= tp_price -> trigger_type=1
        # SL-LONG: price <= sl_price -> trigger_type=2
        tp_res = self.place_trigger_order(symbol, 3, vol, tp_price, 1, leverage, open_type)
        sl_res = self.place_trigger_order(symbol, 3, vol, sl_price, 2, leverage, open_type)

        return {
            "success": True,
            "symbol": symbol,
            "entry_price": price,
            "vol": vol,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "order": order,
            "tp": tp_res,
            "sl": sl_res,
        }
