"""Test đặt lệnh LONG trên MEXC Futures với vol = 50 USDT.

Sử dụng config từ config.json (api_key, api_secret, uid, proxy, leverage, tp%, sl%).
Coin test: lấy tham số dòng lệnh hoặc mặc định 'BTC'.

Cách chạy:
    python test_long.py            # mặc định BTC
    python test_long.py SOL        # đổi coin
    python test_long.py SOL 50     # đổi coin + vol USDT
"""
import sys
import json
import os

from mexc_client import MexcClient

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")


def main():
    coin = sys.argv[1].upper() if len(sys.argv) > 1 else "BTC"
    usdt_size = float(sys.argv[2]) if len(sys.argv) > 2 else 50.0

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    m = cfg["mexc"]
    leverage = int(m.get("leverage", 10))
    tp = float(m.get("tp_percent", 5))
    sl = float(m.get("sl_percent", 2))
    margin = m.get("margin_type", "isolated")

    print("=" * 60)
    print(f" TEST LONG: coin={coin} | vol={usdt_size} USDT | lev=x{leverage}")
    print(f" TP={tp}%   SL={sl}%   margin={margin}")
    print(f" Proxy: {m.get('proxy') or '(none)'}")
    print(f" UID  : {m.get('uid') or '(none)'}")
    print("=" * 60)

    client = MexcClient(
        api_key=m["api_key"],
        api_secret=m["api_secret"],
        uid=m.get("uid", ""),
        proxy=m.get("proxy", ""),
    )

    # 1) Tải contracts
    contracts = client.get_all_contracts()
    print(f"[1] Đã tải {len(contracts)} contracts MEXC")

    symbol = client.has_symbol(coin)
    if not symbol:
        print(f"[X] {coin} không có trên MEXC futures. Thoát.")
        return
    print(f"[2] Symbol hợp lệ: {symbol}")

    # 2) Kiểm tra auth
    assets = client.get_assets()
    if not assets.get("success"):
        print(f"[X] Auth fail: {assets.get('message')}")
        return
    print("[3] Auth OK")

    # 3) Giá hiện tại
    price = client.get_ticker_price(symbol)
    print(f"[4] Giá {symbol}: {price}")

    # 4) Tính vol contracts
    vol = client.calculate_volume(symbol, usdt_size, price, leverage)
    print(f"[5] Volume contracts: {vol}")
    if vol <= 0:
        print("[X] Volume = 0. Thoát.")
        return

    # 5) Thực thi long signal đầy đủ (set leverage + market long + TP/SL)
    print("[6] Đang vào lệnh...")
    result = client.execute_long_signal(
        base_coin=coin,
        usdt_size=usdt_size,
        leverage=leverage,
        tp_percent=tp,
        sl_percent=sl,
        margin_type=margin,
    )

    print("=" * 60)
    print(" KẾT QUẢ:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("=" * 60)


if __name__ == "__main__":
    main()
