"""Debug WEB token MEXC - thử các cách auth khác nhau."""
import json, os, time, requests

with open(os.path.join(os.path.dirname(__file__), "config.json"), encoding="utf-8") as f:
    cfg = json.load(f)["mexc"]

uid = cfg.get("uid", "")
proxy = cfg.get("proxy", "")
proxies = {"http": proxy, "https": proxy} if proxy else None

# Endpoint web futures
URL = "https://futures.mexc.com/api/v1/private/account/assets"

# Cách 1: Authorization header
print("=== Cách 1: Authorization ===")
r = requests.get(URL, headers={"Authorization": uid}, proxies=proxies, timeout=15)
print("Status:", r.status_code, "Body:", r.text[:300])

# Cách 2: Cookie u_id
print("\n=== Cách 2: Cookie u_id ===")
r = requests.get(URL, cookies={"u_id": uid}, proxies=proxies, timeout=15)
print("Status:", r.status_code, "Body:", r.text[:300])

# Cách 3: Cookie uc_token
print("\n=== Cách 3: Cookie uc_token ===")
r = requests.get(URL, cookies={"uc_token": uid}, proxies=proxies, timeout=15)
print("Status:", r.status_code, "Body:", r.text[:300])

# Cách 4: Authorization + browser headers
print("\n=== Cách 4: Authorization + UA ===")
r = requests.get(URL, headers={
    "Authorization": uid,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0",
    "Accept": "application/json",
    "Origin": "https://www.mexc.com",
    "Referer": "https://www.mexc.com/",
    "Language": "English",
}, proxies=proxies, timeout=15)
print("Status:", r.status_code, "Body:", r.text[:300])
