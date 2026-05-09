# MEXC Futures API Documentation

## Tài liệu API vào lệnh MEXC đang sử dụng trong Project

---

## Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Xác thực](#2-xác-thực)
3. [Base URLs](#3-base-urls)
4. [Position Mode](#4-position-mode)
5. [API Endpoints](#5-api-endpoints)
6. [Order Parameters](#6-order-parameters)
7. [Modules chính](#7-modules-chính)
8. [Ví dụ sử dụng](#8-ví-dụ-sử-dụng)

---

## 1. Tổng quan

Project sử dụng **hai phương thức** để kết nối với MEXC Futures:

### 1.1 Official API (Legacy)

- Sử dụng `api_key` và `api_secret`
- Signature: **HMAC-SHA256**
- Files: `mexc_client.py`, `mexc_trader.py`

### 1.2 Secret API (Chính)

- Sử dụng `u_id` cookie từ browser
- Signature: **MD5**
- Bypass TLS fingerprint với `curl_cffi`
- Files: `mexc_secret_api.py`, `order_executor.py`

---

## 2. Xác thực

### 2.1 Official API (HMAC-SHA256)

```python
# Signature format
sign_str = api_key + str(timestamp) + body_json
signature = HMAC_SHA256(api_secret, sign_str)

# Headers
headers = {
    "Content-Type": "application/json",
    "ApiKey": api_key,
    "Request-Time": str(timestamp),  # milliseconds
    "Signature": signature
}
```

### 2.2 Secret API (MD5)

```python
# Signature format
g = MD5(u_id + timestamp)[7:]  # substring từ index 7
payload_json = json.dumps(payload, separators=(',', ':'))
signature = MD5(timestamp + payload_json + g)

# Headers
headers = {
    "accept": "*/*",
    "authorization": u_id,  # Cookie u_id (bắt đầu bằng "WEB...")
    "content-type": "application/json",
    "x-mxc-nonce": timestamp,
    "x-mxc-sign": signature,
    "user-agent": "Mozilla/5.0...",
    "origin": "https://futures.mexc.com",
    "referer": "https://futures.mexc.com/"
}
```

---

## 3. Base URLs

| API Type         | Base URL                          |
| ---------------- | --------------------------------- |
| Futures Contract | `https://contract.mexc.com`       |
| Futures Secret   | `https://futures.mexc.com/api/v1` |
| Spot             | `https://api.mexc.com`            |

---

## 4. Position Mode

⚠️ **QUAN TRỌNG**: Account đang sử dụng **ONE-WAY MODE** (`positionMode=1`)

### 4.1 Side Values cho One-Way Mode

| Action          | Side Value | Description              |
| --------------- | ---------- | ------------------------ |
| **Open Long**   | `1`        | BUY                      |
| **Open Short**  | `3`        | SELL                     |
| **Close Long**  | `3`        | SELL + `reduceOnly=true` |
| **Close Short** | `1`        | BUY + `reduceOnly=true`  |

### 4.2 Side Values cho Hedge Mode (KHÔNG SỬ DỤNG)

| Action      | Side Value |
| ----------- | ---------- |
| Open Long   | `1`        |
| Open Short  | `2`        |
| Close Short | `3`        |
| Close Long  | `4`        |

---

## 5. API Endpoints

### 5.1 Public Endpoints

| Endpoint                                  | Method | Description            |
| ----------------------------------------- | ------ | ---------------------- |
| `/api/v1/contract/detail?symbol={symbol}` | GET    | Lấy thông tin contract |
| `/api/v1/contract/ticker`                 | GET    | Lấy tất cả tickers     |
| `/api/v1/contract/ticker?symbol={symbol}` | GET    | Lấy ticker của symbol  |
| `/api/v1/contract/kline/{symbol}`         | GET    | Lấy candlestick data   |

### 5.2 Private Endpoints - Account

| Endpoint                                        | Method | Description                       |
| ----------------------------------------------- | ------ | --------------------------------- |
| `/api/v1/private/account/assets`                | GET    | Lấy thông tin tài khoản & balance |
| `/api/v1/private/position/open_positions`       | GET    | Lấy danh sách positions đang mở   |
| `/api/v1/private/position/change_leverage`      | POST   | Thay đổi leverage                 |
| `/api/v1/private/position/change_position_mode` | POST   | Thay đổi position mode            |

### 5.3 Private Endpoints - Orders

| Endpoint                                  | Method | Description                   |
| ----------------------------------------- | ------ | ----------------------------- |
| `/api/v1/private/order/submit`            | POST   | Đặt lệnh Market/Limit         |
| `/api/v1/private/order/create`            | POST   | Tạo lệnh (Secret API)         |
| `/api/v1/private/order/cancel`            | POST   | Hủy lệnh                      |
| `/api/v1/private/order/cancel_all`        | POST   | Hủy tất cả lệnh               |
| `/api/v1/private/order/list/open_orders`  | GET    | Lấy các lệnh đang mở          |
| `/api/v1/private/order/chase_limit_order` | POST   | Chase order theo best bid/ask |

### 5.4 Private Endpoints - Plan Orders (TP/SL)

| Endpoint                                     | Method | Description                       |
| -------------------------------------------- | ------ | --------------------------------- |
| `/api/v1/private/planorder/place`            | POST   | Đặt lệnh trigger (TP/SL)          |
| `/api/v1/private/planorder/list/orders`      | GET    | Lấy danh sách plan orders         |
| `/api/v1/private/planorder/list/plan_orders` | GET    | Lấy plan orders (variant)         |
| `/api/v1/private/planorder/cancel`           | POST   | Hủy plan order                    |
| `/api/v1/private/planorder/cancel_all`       | POST   | Hủy tất cả plan orders của symbol |

---

## 6. Order Parameters

### 6.1 Market Order Payload

```python
payload = {
    "symbol": "BTC_USDT",          # Trading pair
    "side": 1,                      # 1=BUY, 3=SELL
    "type": 5,                      # 5=Market, 1=Limit
    "vol": "100",                   # Volume (số contracts)
    "openType": 1,                  # 1=Isolated, 2=Cross
    "leverage": 20,                 # Đòn bẩy (1-200)
    "price": "0",                   # Giá (=0 cho market)
    "positionMode": 1,              # 1=One-way mode

    # Optional
    "reduceOnly": True,             # True = chỉ đóng lệnh
    "stopLossPrice": "40000",       # Giá SL
    "takeProfitPrice": "50000"      # Giá TP
}
```

### 6.2 Limit Order Payload

```python
payload = {
    "symbol": "BTC_USDT",
    "side": 1,
    "type": "1",                    # "1" = Limit
    "vol": 100,
    "price": "45000",               # Giá limit
    "openType": 1,
    "leverage": 20,
    "priceProtect": "0"             # "0" = Off
}
```

### 6.3 Plan Order (TP/SL) Payload

```python
payload = {
    "symbol": "BTC_USDT",
    "side": 1,                      # Close side (1=BUY đóng SHORT, 3=SELL đóng LONG)
    "vol": "100",
    "triggerPrice": "40000",        # Giá trigger
    "triggerType": 1,               # 1=>=, 2=<=
    "orderType": 5,                 # 5=Market when triggered
    "openType": 2,                  # 1=Isolated, 2=Cross
    "leverage": 20,
    "executeCycle": 1,              # 1=GTC (Good Till Cancel)
    "trend": 1                      # REQUIRED!
}
```

### 6.4 Trigger Type Logic

| Position | Order Type  | Condition           | triggerType |
| -------- | ----------- | ------------------- | ----------- |
| LONG     | Take Profit | Giá TĂNG >= trigger | `1`         |
| LONG     | Stop Loss   | Giá GIẢM <= trigger | `2`         |
| SHORT    | Take Profit | Giá GIẢM <= trigger | `2`         |
| SHORT    | Stop Loss   | Giá TĂNG >= trigger | `1`         |

### 6.5 Order Type Values

| Value | Type                      |
| ----- | ------------------------- |
| `1`   | Limit                     |
| `2`   | Post Only                 |
| `3`   | Immediate or Cancel (IOC) |
| `4`   | Fill or Kill (FOK)        |
| `5`   | Market                    |

### 6.6 Open Type Values

| Value | Type            |
| ----- | --------------- |
| `1`   | Isolated Margin |
| `2`   | Cross Margin    |

---

## 7. Modules chính

### 7.1 MexcSecretAPI (`mexc_secret_api.py`)

**Core client** sử dụng u_id cookie.

```python
from mexc_secret_api import MexcSecretAPI, Side

# Khởi tạo
client = MexcSecretAPI(u_id="WEB...", proxy="http://user:pass@host:port")

# Test connection
client.test_connection()  # True/False
client.test_auth()        # True/False

# Account
balance = client.get_balance("USDT")  # float
positions = client.get_positions()    # List[Position]

# Trading
client.long(symbol, vol, leverage)    # Open Long
client.short(symbol, vol, leverage)   # Open Short
client.close_long(symbol, vol)        # Close Long
client.close_short(symbol, vol)       # Close Short
client.close_all()                    # Close tất cả

# TP/SL
client.place_stop_loss(symbol, side, vol, trigger_price, is_short=True)
client.place_take_profit(symbol, side, vol, trigger_price, is_short=True)
client.get_trigger_orders(symbol)
client.cancel_trigger_order(order_id, symbol)

# Leverage
client.set_leverage(symbol, leverage, open_type)

# Market data
client.get_ticker(symbol)          # Ticker info
client.get_contract_detail(symbol) # Contract specifications
client.round_price(symbol, price)  # Round theo priceUnit
```

### 7.2 OrderExecutor (`order_executor.py`)

**High-level executor** với logic trading.

```python
from order_executor import OrderExecutor, get_executor

# Get singleton instance
executor = get_executor()

# Connection test
success, msg = executor.test_connection()
success, msg = executor.test_auth()

# Account info
balance = executor.get_balance()
positions = executor.get_positions()

# Volume calculation
volume, error = executor.calculate_volume(
    symbol="BTC_USDT",
    usdt_size=10,          # $10 position
    entry_price=45000,
    leverage=10
)

# Open positions
order = executor.open_long(symbol, volume, leverage)
order = executor.open_short(symbol, volume, leverage)
order = executor.open_long_with_size(symbol, usdt_size=10, leverage=10)
order = executor.open_short_with_size(symbol, usdt_size=10, leverage=10)

# Close positions
order = executor.close_long(symbol, volume)
order = executor.close_short(symbol, volume)

# TP/SL
tpsl = executor.place_tp_sl(
    symbol="BTC_USDT",
    volume=100,
    take_profit=50000,
    stop_loss=40000,
    leverage=10,
    open_type=1,
    side="LONG"  # hoặc "SHORT"
)

# Execute full signal
order_result, tpsl_result = executor.execute_signal(
    symbol="BTC_USDT",
    entry_price=45000,
    stop_loss=44000,
    take_profit=48000,
    usdt_size=10,
    leverage=10,
    margin_type="isolated",
    side="SHORT"
)
```

### 7.3 MEXCFuturesTrader (`mexc_trader.py`)

**Legacy trader** sử dụng Official API.

```python
from mexc_trader import MEXCFuturesTrader

trader = MEXCFuturesTrader(api_key="...", api_secret="...")

# Account
info = trader.get_account_info()
positions = trader.get_open_positions()

# Trading
trader.open_long_position(symbol, quantity, leverage)
trader.close_position(symbol, quantity)
trader.set_leverage(symbol, leverage)

# TP/SL
trader.place_stop_loss(symbol, quantity, stop_price)
trader.place_take_profit(symbol, quantity, take_price)
trader.place_tp_sl_orders(symbol, quantity, stop_price, take_price)
```

### 7.4 MEXCClient (`mexc_client.py`)

**Legacy client** (để tương thích).

```python
from mexc_client import MEXCClient

client = MEXCClient(api_key="...", api_secret="...")

# Market Data
client.get_ticker(symbol)
client.get_klines(symbol, interval="Min5", limit=100)
client.get_all_tickers(market="futures")
client.get_top_gainers(market="futures", top_n=10)
client.get_top_volatility(market="futures", top_n=10)
client.get_contract_info(symbol)

# Trading
client.place_futures_market_order(symbol, side, vol, leverage)
client.place_trigger_order(symbol, side, vol, trigger_price)
client.cancel_trigger_order(symbol, order_id)
client.close_position(symbol)
client.get_futures_positions()
client.get_futures_account_info()
```

---

## 8. Ví dụ sử dụng

### 8.1 Mở lệnh Short với TP/SL

```python
from order_executor import get_executor

executor = get_executor()

# Mở lệnh SHORT $10 với 10x leverage
order = executor.open_short_with_size(
    symbol="BTC_USDT",
    usdt_size=10,
    leverage=10,
    open_type=1  # Isolated
)

if order.success:
    print(f"✅ Short opened! Order ID: {order.order_id}")
    print(f"   Volume: {order.volume} contracts")

    # Đặt TP/SL riêng
    tpsl = executor.place_tp_sl(
        symbol="BTC_USDT",
        volume=order.volume,
        take_profit=44000,  # TP dưới entry
        stop_loss=46000,    # SL trên entry
        leverage=10,
        open_type=1,
        side="SHORT"
    )

    if tpsl.success:
        print(f"✅ TP/SL placed!")
        print(f"   TP Order ID: {tpsl.tp_order_id}")
        print(f"   SL Order ID: {tpsl.sl_order_id}")
else:
    print(f"❌ Failed: {order.message}")
```

### 8.2 Execute Signal (Mở lệnh + TP/SL cùng lúc)

```python
from order_executor import get_executor

executor = get_executor()

# Execute signal SHORT
order_result, tpsl_result = executor.execute_signal(
    symbol="BTC_USDT",
    entry_price=45000,
    stop_loss=46000,      # SL cao hơn entry (SHORT)
    take_profit=43000,    # TP thấp hơn entry (SHORT)
    usdt_size=10,
    leverage=10,
    margin_type="isolated",
    side="SHORT"
)

if order_result.success:
    print(f"✅ SHORT opened at {order_result.price}")
    if tpsl_result.success:
        print(f"✅ TP/SL configured")
```

### 8.3 Đóng tất cả positions

```python
from mexc_secret_api import MexcSecretAPI

client = MexcSecretAPI(u_id="WEB...")
results = client.close_all()

for r in results:
    if r.success:
        print(f"✅ Closed: {r.order_id}")
    else:
        print(f"❌ Failed: {r.message}")
```

### 8.4 Lấy thông tin positions

```python
from order_executor import get_executor

executor = get_executor()
positions = executor.get_positions()

for pos in positions:
    print(f"{pos.symbol} {pos.side.upper()}")
    print(f"  Size: {pos.size}")
    print(f"  Entry: ${pos.entry_price:,.2f}")
    print(f"  Mark:  ${pos.mark_price:,.2f}")
    print(f"  PnL:   {pos.pnl_percent:+.2f}% (${pos.pnl:+.2f})")
    print(f"  Leverage: {pos.leverage}x")
    if pos.liq_price:
        print(f"  Liquidation: ${pos.liq_price:,.2f}")
```

---

## Cấu hình

### trading_config.json

```json
{
  "enabled": true,
  "api_key": "mx0vgl...", // Official API key
  "api_secret": "25a556...", // Official API secret
  "u_id": "WEB05fa6ab...", // Secret API u_id (từ browser cookie)
  "leverage": 10,
  "margin_type": "isolated", // "isolated" hoặc "cross"
  "position_size_usdt": 1, // Size mỗi position
  "max_positions": 3,
  "use_signal_tp_sl": true,
  "custom_tp_percent": 3,
  "custom_sl_percent": 1.2
}
```

### proxy_config.json

```json
{
  "enabled": true,
  "host": "103.133.110.140",
  "port": "12345",
  "username": "VN85758",
  "password": "..."
}
```

---

## Response Format

### Success Response

```json
{
  "success": true,
  "code": 0,
  "data": {...}
}
```

### Error Response

```json
{
  "success": false,
  "code": 1001,
  "message": "Error description"
}
```

---

## Error Codes phổ biến

| Code    | Description          |
| ------- | -------------------- |
| `1001`  | Invalid parameter    |
| `2001`  | Insufficient balance |
| `2002`  | Position not found   |
| `2003`  | Order not found      |
| `30001` | Symbol not exist     |
| `30004` | Vol too small        |
| `30005` | Vol too large        |
| `40001` | Signature error      |
| `40003` | Unauthorized         |

---

## Dependencies

```txt
curl_cffi>=0.5.0     # TLS fingerprint bypass
requests>=2.28.0     # HTTP client fallback
```

---

_Document created: 2024_
_Project: BotTradeShortV1-CustomPosition_
