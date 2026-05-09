# MEXC Futures Auto-Trade Bot

## Mô tả

Bot tự động đọc tín hiệu niêm yết coin mới từ Telegram, kiểm tra có trên MEXC Futures không, tự động vào lệnh LONG với TP/SL, quản lý vị thế và cung cấp giao diện web quản trị.

## Tính năng

- Đọc tin nhắn realtime từ các group Telegram (Telethon)
- Tự động nhận diện coin mới niêm yết, khớp tên coin linh hoạt
- Kiểm tra coin có trên MEXC Futures không (API web, bypass Akamai)
- Tự động vào lệnh LONG với cấu hình đòn bẩy, TP, SL
- Theo dõi vị thế, tự động hủy lệnh TP/SL còn lại khi đóng vị thế
- Giao diện web Flask quản lý, xem log, đóng lệnh thủ công
- Lưu lịch sử, cấu hình, trạng thái vào file

## Cài đặt

1. Clone repo:
   ```sh
   git clone https://github.com/HaiAnh1802/BotTradeCoinList.git
   cd BotTradeCoinList
   ```
2. Cài Python 3.10+ và các thư viện:
   ```sh
   pip install -r requirements.txt
   ```
3. Điền thông tin cấu hình vào `config.json` (API key MEXC, Telegram...)
4. Chạy bot:
   ```sh
   python app.py
   ```
5. Truy cập giao diện web: [http://127.0.0.1:5000](http://127.0.0.1:5000)

## File cấu hình mẫu (`config.json`)

```json
{
  "telegram": {
    "api_id": 123456,
    "api_hash": "...",
    "phone": "+84...",
    "session_name": "my_session",
    "target_groups": ["-4767544482"]
  },
  "mexc": {
    "api_key": "...",
    "api_secret": "...",
    "uid": "...",
    "proxy": "http://user:pass@host:port",
    "leverage": 10,
    "margin_type": "isolated",
    "position_size_usdt": 5,
    "tp_percent": 5,
    "sl_percent": 2
  },
  "trading": {
    "enabled": true,
    "auto_long_on_signal": true
  }
}
```

## Lưu ý

- Cần proxy residential để gọi API MEXC web (bypass Akamai)
- Không dùng tài khoản chính để tránh rủi ro
- Chỉ hỗ trợ lệnh LONG, TP/SL theo %
- Không chịu trách nhiệm với mọi rủi ro giao dịch

## License

MIT
