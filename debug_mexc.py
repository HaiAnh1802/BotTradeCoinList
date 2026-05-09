"""Debug raw response từ MEXC private endpoint."""
import json, os, time, hmac, hashlib, requests

with open(os.path.join(os.path.dirname(__file__), "config.json"), encoding="utf-8") as f:
    cfg = json.load(f)["mexc"]

API = "https://contract.mexc.com"
key = cfg["api_key"]
secret = cfg["api_secret"]
uid = cfg.get("uid", "")
proxy = cfg.get("proxy", "")

ts = str(int(time.time() * 1000))
sig = hmac.new(secret.encode(), (key + ts).encode(), hashlib.sha256).hexdigest()
headers = {
    "Content-Type": "application/json",
    "ApiKey": key,
    "Request-Time": ts,
    "Signature": sig,
}
if uid:
    headers["x-mxc-uid"] = uid

proxies = {"http": proxy, "https": proxy} if proxy else None

print("Headers:", json.dumps(headers, indent=2))
print("Proxy  :", proxy or "(none)")

r = requests.get(f"{API}/api/v1/private/account/assets",
                 headers=headers, proxies=proxies, timeout=15)
print("Status :", r.status_code)
print("Body   :", r.text[:500])
