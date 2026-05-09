"""Test các biến thể POST để vượt Access Denied 403."""
import json, os, time, requests

with open(os.path.join(os.path.dirname(__file__), "config.json"), encoding="utf-8") as f:
    cfg = json.load(f)["mexc"]

uid = cfg["uid"]
proxy = cfg.get("proxy")
proxies = {"http": proxy, "https": proxy} if proxy else None

base_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.mexc.com",
    "Referer": "https://www.mexc.com/",
    "Authorization": uid,
    "Content-Type": "application/json",
    "x-mxc-nonce": str(int(time.time() * 1000)),
    "Language": "English",
    "trochilus-trace-id": "0",
    "trochilus-uid": "",
    "sec-ch-ua": '"Chromium";v="124", "Not.A/Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}

# Lấy giá BTC trước
r = requests.get("https://contract.mexc.com/api/v1/contract/ticker?symbol=BTC_USDT",
                 proxies=proxies, timeout=10)
price = r.json()["data"]["lastPrice"]
print("BTC_USDT price:", price)

# Try multiple order endpoints
payload = {
    "symbol": "BTC_USDT",
    "side": 1,            # Open Long
    "openType": 1,        # isolated
    "type": "5",          # Market
    "vol": 1,
    "leverage": 10,
    "marketCeiling": False,
    "priceProtect": "0",
}

for path in [
    "/api/v1/private/order/create",
    "/api/v1/private/order/submit",
]:
    print(f"\n=== POST {path} ===")
    r = requests.post(f"https://futures.mexc.com{path}",
                      json=payload, headers=base_headers, proxies=proxies, timeout=15)
    print("Status:", r.status_code)
    print("Body  :", r.text[:400])
