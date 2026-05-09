import os
import re
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel, PeerChat

load_dotenv()

API_ID       = int(os.getenv("API_ID"))
API_HASH     = os.getenv("API_HASH")
PHONE        = os.getenv("PHONE")
SESSION_NAME = os.getenv("SESSION_NAME", "my_session")
TARGET_GROUPS = [g.strip() for g in os.getenv("TARGET_GROUPS", "").split(",") if g.strip()]

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


def extract_listing_coin(text: str) -> str | None:
    """Trích xuất tên coin từ tin nhắn listing.
    Hỗ trợ các dạng:
      - 'PROS  MarketCap:'
      - '(PROS)'
      - 'Listing: XXX/'
      - '$PROS'
    """
    # Ưu tiên: dòng có MarketCap -> lấy symbol trước nó
    m = re.search(r'\b([A-Z]{2,10})\s+MarketCap:', text)
    if m:
        return m.group(1)

    # Dạng (SYMBOL) trong ngoặc đơn
    m = re.search(r'\(([A-Z]{2,10})\)', text)
    if m:
        return m.group(1)

    # Dạng $SYMBOL
    m = re.search(r'\$([A-Z]{2,10})\b', text)
    if m:
        return m.group(1)

    # Dạng "Listing: SYMBOL/" hoặc "Listing: SYMBOL "
    m = re.search(r'[Ll]isting[:\s]+([A-Z]{2,10})[/\s]', text)
    if m:
        return m.group(1)

    return None


def format_message(event, chat_title: str) -> str:
    """Format tin nhắn ra console."""
    sender = event.sender
    sender_name = ""
    if sender:
        first = getattr(sender, "first_name", "") or ""
        last  = getattr(sender, "last_name", "")  or ""
        sender_name = f"{first} {last}".strip() or getattr(sender, "username", "Unknown")

    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    coin = extract_listing_coin(event.raw_text)
    coin_line = f"Coin listing: {coin}\n" if coin else ""
    return (
        f"\n{'='*60}\n"
        f"[{time_str}]\n"
        f"Nhóm : {chat_title}\n"
        f"Từ   : {sender_name}\n"
        f"{coin_line}"
        f"Nội dung:\n{event.raw_text}\n"
        f"{'='*60}"
    )


async def resolve_targets(targets: list[str]) -> list:
    """Chuyển username / link / chat_id thành entity."""
    # Lấy toàn bộ dialogs để Telethon cache entity
    print("Đang tải danh sách nhóm/kênh...")
    dialogs = await client.get_dialogs()

    entities = []
    for t in targets:
        t = t.strip()
        found = None

        # Nếu là số (chat_id) thì tìm trong dialogs
        try:
            target_id = int(t)
            for d in dialogs:
                did = d.entity.id
                # So sánh id gốc hoặc id dạng supergroup (-100xxx)
                if did == target_id or did == abs(target_id) or -did == target_id:
                    found = d.entity
                    break
        except ValueError:
            pass  # Không phải số -> thử get_entity theo username

        if found is None:
            try:
                found = await client.get_entity(t)
            except Exception as e:
                print(f"[LỖI] Không thể lấy entity '{t}': {e}")
                continue

        entities.append(found)
        print(f"[OK] Theo dõi nhóm: {getattr(found, 'title', t)}")

    return entities


async def main():
    await client.start(phone=PHONE)
    print("Đã đăng nhập thành công.\n")

    # Nếu TARGET_GROUPS rỗng -> lắng nghe TẤT CẢ nhóm/kênh
    if not TARGET_GROUPS:
        print("Không cấu hình TARGET_GROUPS -> lắng nghe tất cả tin nhắn...\n")

        @client.on(events.NewMessage)
        async def handler_all(event):
            try:
                chat = await event.get_chat()
                title = getattr(chat, "title", str(event.chat_id))
                print(format_message(event, title))
            except Exception as e:
                print(f"[LỖI xử lý tin nhắn]: {e}")

    else:
        entities = await resolve_targets(TARGET_GROUPS)
        if not entities:
            print("Không có nhóm hợp lệ. Thoát.")
            return

        chat_ids = [e.id for e in entities]
        title_map = {e.id: getattr(e, "title", str(e.id)) for e in entities}

        @client.on(events.NewMessage(chats=chat_ids))
        async def handler_specific(event):
            try:
                title = title_map.get(event.chat_id, str(event.chat_id))
                print(format_message(event, title))
            except Exception as e:
                print(f"[LỖI xử lý tin nhắn]: {e}")

    print("Đang lắng nghe tin nhắn realtime... (Ctrl+C để dừng)\n")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
