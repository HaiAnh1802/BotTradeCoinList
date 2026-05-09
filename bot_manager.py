"""Bot Manager: quản lý Telegram listener + xử lý signal + lưu log."""
import os
import re
import json
import asyncio
import threading
from collections import deque
from datetime import datetime
from typing import Optional

from telethon import TelegramClient, events

from mexc_client import MexcClient

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")


def load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def extract_listing_coin(text: str) -> Optional[str]:
    """Trích xuất ứng viên đầu tiên (giữ tương thích cũ)."""
    cands = extract_listing_candidates(text)
    return cands[0] if cands else None


def extract_listing_candidates(text: str) -> list:
    """Trích xuất danh sách ứng viên ticker/name từ tin nhắn, ưu tiên cao trước.
    Vd: 'Pharos (PROS) MarketCap: ...' -> ['PROS', 'PHAROS']
    """
    if not text:
        return []
    BLACKLIST = {"KRW", "USD", "USDT", "USDC", "BTC", "ETH", "BNB",
                 "EUR", "JPY", "GBP", "TRY", "BUSD", "DAI", "FDUSD",
                 "MARKET", "MARKETS", "SPOT", "FUTURES", "PERP", "PERPETUAL",
                 "LISTING", "LISTED", "UPBIT", "BINANCE", "BITHUMB", "MEXC",
                 "OKX", "COINBASE", "BYBIT", "KRAKEN", "GATE", "KUCOIN",
                 "NEW", "PAIR", "PAIRS", "TRADE", "TRADING", "AUTO", "MATCH"}

    candidates: list = []

    def add(sym: str):
        sym = sym.upper().strip()
        if 2 <= len(sym) <= 15 and sym not in BLACKLIST and sym not in candidates:
            candidates.append(sym)

    # 1. Cashtag $TICKER
    for m in re.finditer(r'\$([A-Z0-9]{2,15})\b', text):
        add(m.group(1))

    # 2. Pattern "Name (TICKER)" - cả ticker và name đều add
    for m in re.finditer(r'\b([A-Za-z][A-Za-z0-9 ]{1,20})\s*\(([A-Z0-9]{2,15})\)', text):
        add(m.group(2))                     # ticker
        add(m.group(1).replace(' ', ''))    # name (xoá space)

    # 3. "TICKER MarketCap:"
    for m in re.finditer(r'\b([A-Z0-9]{2,15})\s+MarketCap:', text):
        add(m.group(1))

    # 4. "(TICKER)" độc lập
    for m in re.finditer(r'\(([A-Z0-9]{2,15})\)', text):
        add(m.group(1))

    # 5. "Listing: TICKER"
    for m in re.finditer(r'[Ll]isting[:\s]+([A-Z0-9]{2,15})\b', text):
        add(m.group(1))

    return candidates


class BotManager:
    """Singleton quản lý bot."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.config = load_config()
        self.logs: deque = deque(maxlen=500)
        self.signals: deque = deque(maxlen=200)   # lịch sử coin được trade
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.client: Optional[TelegramClient] = None
        self.mexc: Optional[MexcClient] = None
        self.processed_coins: set = set()         # tránh trade trùng coin
        self._lock = threading.Lock()

        # Theo dõi positions: {symbol: {"opened_ts", "tp_id", "sl_id", "vol", ...}}
        self.tracked_positions: dict = {}
        self.position_monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop = threading.Event()

        # ---- Auth (đăng nhập Telegram lần đầu) ----
        self.auth_loop: Optional[asyncio.AbstractEventLoop] = None
        self.auth_thread: Optional[threading.Thread] = None
        self.auth_client: Optional[TelegramClient] = None
        self.auth_phone: Optional[str] = None
        self.auth_phone_code_hash: Optional[str] = None

    # ---------------- Public API ----------------
    def get_config(self) -> dict:
        return self.config

    def update_config(self, new_cfg: dict) -> dict:
        self.config.update(new_cfg)
        save_config(self.config)
        return self.config

    def get_logs(self) -> list:
        return list(self.logs)

    def get_signals(self) -> list:
        return list(self.signals)

    def get_status(self) -> dict:
        return {
            "running": self.running,
            "mexc_contracts": len(self.mexc._contract_cache) if self.mexc else 0,
            "processed_coins": len(self.processed_coins),
            "groups": self.config.get("telegram", {}).get("target_groups", []),
        }

    def log(self, msg: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = {"time": ts, "level": level, "msg": msg}
        self.logs.append(entry)
        print(f"[{ts}] {level.upper()}: {msg}")

    def start(self) -> dict:
        with self._lock:
            if self.running:
                return {"success": False, "message": "Bot đang chạy"}
            cfg = self.config
            tg = cfg.get("telegram", {})
            if not tg.get("api_id") or not tg.get("api_hash") or not tg.get("phone"):
                return {"success": False, "message": "Thiếu thông tin Telegram"}

            self.thread = threading.Thread(target=self._run_loop, daemon=True)
            self.thread.start()
            return {"success": True, "message": "Đã khởi động"}

    def stop(self) -> dict:
        with self._lock:
            if not self.running:
                return {"success": False, "message": "Bot không chạy"}
            if self.loop and self.client:
                fut = asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop)
                try:
                    fut.result(timeout=5)
                except Exception:
                    pass
            self.running = False
            return {"success": True, "message": "Đã dừng"}

    def reset_processed(self):
        self.processed_coins.clear()
        self.log("Đã reset danh sách coin đã xử lý")

    def refresh_mexc_contracts(self) -> int:
        if not self.mexc:
            cfg = self.config["mexc"]
            self.mexc = MexcClient(
                cfg.get("api_key", ""),
                cfg.get("api_secret", ""),
                cfg.get("uid", ""),
                cfg.get("proxy", ""),
            )
        contracts = self.mexc.get_all_contracts(force_refresh=True)
        self.log(f"Đã tải {len(contracts)} contracts từ MEXC")
        return len(contracts)

    def test_mexc(self) -> dict:
        cfg = self.config["mexc"]
        client = MexcClient(
            cfg.get("api_key", ""), cfg.get("api_secret", ""),
            cfg.get("uid", ""), cfg.get("proxy", ""),
        )
        contracts = client.get_all_contracts()
        result = {"contracts": len(contracts)}
        if cfg.get("api_key") and cfg.get("api_secret"):
            assets = client.get_assets()
            result["auth"] = assets.get("success", False)
            result["auth_message"] = assets.get("message", "")
        else:
            result["auth"] = None
            result["auth_message"] = "Chưa cấu hình API key"
        return result

    # ---------------- Telegram Auth ----------------
    def _ensure_auth_loop(self):
        """Tạo event loop chạy nền cho auth nếu chưa có."""
        if self.auth_loop and self.auth_loop.is_running():
            return
        self.auth_loop = asyncio.new_event_loop()

        def _runner(loop):
            asyncio.set_event_loop(loop)
            loop.run_forever()

        self.auth_thread = threading.Thread(target=_runner, args=(self.auth_loop,), daemon=True)
        self.auth_thread.start()

    def _run_on_auth_loop(self, coro, timeout=60):
        fut = asyncio.run_coroutine_threadsafe(coro, self.auth_loop)
        return fut.result(timeout=timeout)

    def telegram_status(self) -> dict:
        """Kiểm tra session đã đăng nhập hay chưa (không cần OTP)."""
        if self.running:
            return {"authorized": True, "running": True}

        tg = self.config.get("telegram", {})
        if not tg.get("api_id") or not tg.get("api_hash"):
            return {"authorized": False, "running": False, "message": "Thiếu API ID/Hash"}

        self._ensure_auth_loop()

        async def _check():
            client = TelegramClient(tg["session_name"], int(tg["api_id"]), tg["api_hash"])
            await client.connect()
            ok = await client.is_user_authorized()
            await client.disconnect()
            return ok

        try:
            ok = self._run_on_auth_loop(_check(), timeout=20)
            return {"authorized": bool(ok), "running": False}
        except Exception as e:
            return {"authorized": False, "running": False, "message": str(e)}

    def telegram_connect(self) -> dict:
        """Bước 1: gửi mã OTP về Telegram của user."""
        tg = self.config.get("telegram", {})
        if not tg.get("api_id") or not tg.get("api_hash") or not tg.get("phone"):
            return {"success": False, "message": "Thiếu API ID/Hash/Phone"}

        self._ensure_auth_loop()

        async def _connect():
            # Đóng client auth cũ nếu còn
            if self.auth_client:
                try:
                    await self.auth_client.disconnect()
                except Exception:
                    pass
            client = TelegramClient(tg["session_name"], int(tg["api_id"]), tg["api_hash"])
            await client.connect()
            if await client.is_user_authorized():
                await client.disconnect()
                return {"authorized": True}

            sent = await client.send_code_request(tg["phone"])
            self.auth_client = client
            self.auth_phone = tg["phone"]
            self.auth_phone_code_hash = sent.phone_code_hash
            return {"authorized": False, "code_sent": True}

        try:
            res = self._run_on_auth_loop(_connect(), timeout=30)
            if res.get("authorized"):
                self.log("Telegram đã đăng nhập sẵn")
                return {"success": True, "authorized": True, "message": "Đã đăng nhập sẵn"}
            self.log(f"Đã gửi OTP tới {tg['phone']}")
            return {"success": True, "authorized": False, "code_required": True,
                    "message": f"Đã gửi mã OTP tới {tg['phone']}"}
        except Exception as e:
            self.log(f"Lỗi gửi OTP: {e}", "error")
            return {"success": False, "message": str(e)}

    def telegram_verify(self, code: str, password: Optional[str] = None) -> dict:
        """Bước 2: nhập OTP (và 2FA password nếu có)."""
        if not self.auth_client or not self.auth_phone_code_hash:
            return {"success": False, "message": "Chưa gửi OTP. Bấm Kết nối trước."}

        from telethon.errors import SessionPasswordNeededError

        async def _verify():
            try:
                await self.auth_client.sign_in(
                    phone=self.auth_phone,
                    code=str(code).strip(),
                    phone_code_hash=self.auth_phone_code_hash,
                )
            except SessionPasswordNeededError:
                if not password:
                    return {"success": False, "need_password": True,
                            "message": "Tài khoản bật 2FA, cần nhập password"}
                await self.auth_client.sign_in(password=password)

            ok = await self.auth_client.is_user_authorized()
            await self.auth_client.disconnect()
            return {"success": bool(ok), "authorized": bool(ok)}

        try:
            res = self._run_on_auth_loop(_verify(), timeout=30)
            if res.get("authorized"):
                self.log("Telegram đăng nhập thành công")
                self.auth_client = None
                self.auth_phone_code_hash = None
                res["message"] = "Đăng nhập thành công"
            return res
        except Exception as e:
            self.log(f"Lỗi xác minh OTP: {e}", "error")
            return {"success": False, "message": str(e)}

    # ---------------- Position tracking ----------------
    def get_positions_combined(self) -> list:
        """Lấy positions trực tiếp từ MEXC (live) và merge với data tracked."""
        if not self.mexc:
            cfg = self.config["mexc"]
            self.mexc = MexcClient(
                cfg.get("api_key", ""), cfg.get("api_secret", ""),
                cfg.get("uid", ""), cfg.get("proxy", ""),
            )
        live = self.mexc.get_positions()
        result = []
        for p in live:
            symbol = p.get("symbol")
            tracked = self.tracked_positions.get(symbol, {})
            ptype = p.get("positionType")  # 1=long, 2=short
            result.append({
                "symbol": symbol,
                "coin": tracked.get("coin", symbol.replace("_USDT", "")),
                "side": "LONG" if ptype == 1 else "SHORT",
                "leverage": p.get("leverage"),
                "hold_vol": p.get("holdVol"),
                "entry_price": p.get("holdAvgPrice") or tracked.get("entry_price"),
                "mark_price": p.get("priceFair") or p.get("mark"),
                "liq_price": p.get("liquidatePrice"),
                "pnl": p.get("realised", 0),
                "unrealized_pnl": p.get("unrealizedPnl") or p.get("pnl"),
                "margin": p.get("im") or p.get("oim"),
                "tp_price": tracked.get("tp_price"),
                "sl_price": tracked.get("sl_price"),
                "tp_id": tracked.get("tp_id"),
                "sl_id": tracked.get("sl_id"),
                "position_id": p.get("positionId"),
                "opened": tracked.get("opened"),
            })
        return result

    def close_position(self, symbol: str) -> dict:
        if not self.mexc:
            return {"success": False, "message": "MEXC chưa khởi tạo"}
        self.log(f"Đóng vị thế {symbol}...")
        res = self.mexc.close_position(symbol)
        if res.get("success"):
            self.log(f"✅ Đã đóng {symbol} + cancel TP/SL", "success")
            self.tracked_positions.pop(symbol, None)
        else:
            self.log(f"❌ Đóng {symbol} fail: {res}", "error")
        return res

    def _ensure_position_monitor(self):
        """Khởi động thread monitor positions nếu chưa chạy."""
        if self.position_monitor_thread and self.position_monitor_thread.is_alive():
            return
        self._monitor_stop.clear()
        self.position_monitor_thread = threading.Thread(
            target=self._monitor_positions, daemon=True
        )
        self.position_monitor_thread.start()
        self.log("Bắt đầu theo dõi vị thế (auto cancel TP/SL khi khớp)")

    def _monitor_positions(self):
        """Định kỳ check positions. Khi 1 symbol biến mất khỏi live (= TP hoặc SL khớp)
        thì cancel toàn bộ trigger còn lại của symbol đó."""
        import time as _t
        while not self._monitor_stop.is_set():
            try:
                if not self.mexc or not self.tracked_positions:
                    _t.sleep(3)
                    continue
                live = self.mexc.get_positions()
                live_symbols = {p.get("symbol") for p in live}
                # Symbol nào đã track nhưng không còn trong live = đã đóng
                closed = [s for s in list(self.tracked_positions.keys())
                          if s not in live_symbols]
                for sym in closed:
                    self.log(f"📌 {sym} đã đóng (TP/SL khớp) — cancel trigger còn lại")
                    try:
                        self.mexc.cancel_all_triggers(sym)
                    except Exception as e:
                        self.log(f"Cancel triggers lỗi: {e}", "warn")
                    self.tracked_positions.pop(sym, None)
            except Exception as e:
                self.log(f"Monitor positions lỗi: {e}", "warn")
            _t.sleep(3)

    # ---------------- Internal ----------------
    def _run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._async_main())
        except Exception as e:
            self.log(f"Bot lỗi: {e}", "error")
        finally:
            self.running = False
            self.log("Bot đã dừng")

    async def _async_main(self):
        cfg = self.config
        tg = cfg["telegram"]
        mexc_cfg = cfg["mexc"]

        self.mexc = MexcClient(
            mexc_cfg.get("api_key", ""), mexc_cfg.get("api_secret", ""),
            mexc_cfg.get("uid", ""), mexc_cfg.get("proxy", ""),
        )
        contracts = self.mexc.get_all_contracts()
        self.log(f"Đã tải {len(contracts)} contracts từ MEXC")

        self.client = TelegramClient(tg["session_name"], int(tg["api_id"]), tg["api_hash"])
        await self.client.connect()
        if not await self.client.is_user_authorized():
            self.log("Chưa đăng nhập Telegram. Bấm 'Kết nối Telegram' trên giao diện.", "error")
            await self.client.disconnect()
            return
        self.log("Đã đăng nhập Telegram")

        # Resolve groups
        await self.client.get_dialogs()  # cache entities
        target_ids = []
        for g in tg.get("target_groups", []):
            try:
                ent = await self.client.get_entity(int(g) if str(g).lstrip("-").isdigit() else g)
                target_ids.append(ent.id)
                self.log(f"Theo dõi: {getattr(ent, 'title', g)}")
            except Exception as e:
                self.log(f"Không lấy được nhóm {g}: {e}", "warn")

        if not target_ids:
            self.log("Không có nhóm nào hợp lệ", "error")
            await self.client.disconnect()
            return

        @self.client.on(events.NewMessage(chats=target_ids))
        async def handler(event):
            try:
                await self._handle_message(event)
            except Exception as e:
                self.log(f"Lỗi xử lý tin: {e}", "error")

        self.running = True
        self.log("Bot đang lắng nghe tin nhắn...")
        self._ensure_position_monitor()
        await self.client.run_until_disconnected()

    async def _handle_message(self, event):
        text = event.raw_text or ""
        # Log toàn bộ tin nhắn nhận được (rút gọn nếu quá dài)
        preview = text.replace("\n", " ⏎ ").strip()
        if len(preview) > 300:
            preview = preview[:300] + "..."
        chat_id = getattr(event, "chat_id", "?")
        self.log(f"📩 [Tele {chat_id}] {preview or '(empty)'}")

        candidates = extract_listing_candidates(text)
        if not candidates:
            return

        cfg = self.config
        trading = cfg.get("trading", {})

        self.log(f"Ứng viên coin: {', '.join(candidates)}")

        # Thử từng ứng viên trên MEXC để tìm symbol đúng
        coin = None
        symbol = None
        for cand in candidates:
            if cand in self.processed_coins:
                continue
            sym = self.mexc.has_symbol(cand)
            if sym:
                coin, symbol = cand, sym
                break

        if not symbol:
            self.log(f"Không có ứng viên nào trên MEXC futures: {candidates}", "warn")
            for c in candidates:
                self.processed_coins.add(c)
            return

        self.log(f"{coin} CÓ trên MEXC = {symbol}", "success")

        # Kiểm tra đã có vị thế đang mở trên MEXC chưa
        if symbol in self.tracked_positions:
            self.log(f"⚠️ {symbol} đã có lệnh đang theo dõi — bỏ qua", "warn")
            self.processed_coins.add(coin)
            return
        try:
            existing = await asyncio.to_thread(self.mexc.get_positions)
            if any(p.get("symbol") == symbol for p in existing):
                self.log(f"⚠️ {symbol} đã có vị thế trên MEXC — bỏ qua", "warn")
                self.processed_coins.add(coin)
                return
        except Exception as e:
            self.log(f"Check vị thế lỗi: {e}", "warn")

        if not trading.get("enabled"):
            self.log("Trading TẮT — chỉ ghi log, không vào lệnh", "warn")
            self.processed_coins.add(coin)
            self.signals.append({
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "coin": coin, "symbol": symbol, "executed": False,
                "reason": "trading disabled"
            })
            return

        if not trading.get("auto_long_on_signal"):
            self.log("auto_long_on_signal=false, bỏ qua", "warn")
            return

        # Vào lệnh
        mexc_cfg = cfg["mexc"]
        result = await asyncio.to_thread(
            self.mexc.execute_long_signal,
            coin,
            float(mexc_cfg.get("position_size_usdt", 5)),
            int(mexc_cfg.get("leverage", 10)),
            float(mexc_cfg.get("tp_percent", 5)),
            float(mexc_cfg.get("sl_percent", 2)),
            mexc_cfg.get("margin_type", "isolated"),
        )

        self.processed_coins.add(coin)
        self.signals.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "coin": coin,
            "symbol": symbol,
            "executed": result.get("success", False),
            "entry_price": result.get("entry_price"),
            "tp_price": result.get("tp_price"),
            "sl_price": result.get("sl_price"),
            "vol": result.get("vol"),
            "message": result.get("message", ""),
        })

        if result.get("success"):
            self.log(
                f"✅ LONG {symbol} @ {result['entry_price']} | "
                f"TP={result['tp_price']} SL={result['sl_price']} vol={result['vol']}",
                "success"
            )
            # Track position để tự động cancel TP/SL còn lại khi 1 cái khớp
            self.tracked_positions[symbol] = {
                "symbol": symbol,
                "coin": coin,
                "entry_price": result.get("entry_price"),
                "tp_price": result.get("tp_price"),
                "sl_price": result.get("sl_price"),
                "vol": result.get("vol"),
                "tp_id": (result.get("tp") or {}).get("data"),
                "sl_id": (result.get("sl") or {}).get("data"),
                "opened": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "side": "LONG",
            }
            self._ensure_position_monitor()
        else:
            self.log(f"❌ Vào lệnh fail: {result.get('message')}", "error")


def get_bot() -> BotManager:
    return BotManager()
