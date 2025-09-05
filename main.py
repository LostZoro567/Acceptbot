import os
import asyncio
from pyrogram import Client, filters, types
from pyrogram.errors import FloodWait
from pymongo import MongoClient

# ---------------- CONFIG ---------------- #
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Broadcast settings
BROADCAST_MODE = os.getenv("BROADCAST_MODE", "safe")  # "safe" or "fast"
BATCH_SIZE = 100         
DELAY_BETWEEN_MSGS = 0.5 

# Greeting settings
GREETING_PHOTO = os.getenv("GREETING_PHOTO", "https://example.com/welcome.jpg")
GREETING_TEXT = os.getenv("GREETING_TEXT", "Hello {name}, welcome to our channel 🎉")
BUTTON1_TEXT = os.getenv("BUTTON1_TEXT", "Visit Channel")
BUTTON1_URL = os.getenv("BUTTON1_URL", "https://t.me/YourChannel")
BUTTON2_TEXT = os.getenv("BUTTON2_TEXT", "Support")
BUTTON2_URL = os.getenv("BUTTON2_URL", "https://t.me/YourSupport")

# Telegram Bot Client
app = Client("autobot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# MongoDB Client
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["telegram_bot"]
users_collection = db["users"]

# ---------------- GREETING FUNCTION ---------------- #
async def send_greeting(client, user_id, mention):
    """Send greeting message with media + buttons"""
    buttons = []
    if BUTTON1_TEXT and BUTTON1_URL:
        buttons.append([types.InlineKeyboardButton(BUTTON1_TEXT, url=BUTTON1_URL)])
    if BUTTON2_TEXT and BUTTON2_URL:
        buttons.append([types.InlineKeyboardButton(BUTTON2_TEXT, url=BUTTON2_URL)])

    text = GREETING_TEXT.format(name=mention)

    await client.send_photo(
        chat_id=user_id,
        photo=GREETING_PHOTO,
        caption=text,
        reply_markup=types.InlineKeyboardMarkup(buttons) if buttons else None
    )

# ---------------- HANDLERS ---------------- #

# Auto-accept join requests
@app.on_chat_join_request()
async def auto_accept(client, request: types.ChatJoinRequest):
    try:
        await client.approve_chat_join_request(request.chat.id, request.from_user.id)

        if not users_collection.find_one({"user_id": request.from_user.id}):
            users_collection.insert_one({
                "user_id": request.from_user.id,
                "username": request.from_user.username
            })

        await send_greeting(client, request.from_user.id, request.from_user.mention)
    except Exception as e:
        print("Error in join request:", e)

# /start command
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    user_id = message.from_user.id
    if not users_collection.find_one({"user_id": user_id}):
        users_collection.insert_one({
            "user_id": user_id,
            "username": message.from_user.username
        })

    await send_greeting(client, user_id, message.from_user.mention)

# ---------------- BROADCAST HELPERS ---------------- #

async def broadcast_safe(client, reply_msg, all_users):
    sent_count, fail_count = 0, 0
    for user in all_users:
        try:
            await reply_msg.copy(user["user_id"])
            sent_count += 1
            await asyncio.sleep(DELAY_BETWEEN_MSGS)

        except FloodWait as e:
            await asyncio.sleep(e.value)
            continue

        except Exception as e:
            fail_count += 1
            if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                users_collection.delete_one({"user_id": user["user_id"]})
    return sent_count, fail_count


async def send_batch(client, reply_msg, users):
    sent, failed = 0, 0
    for user in users:
        try:
            await reply_msg.copy(user["user_id"])
            sent += 1
            await asyncio.sleep(DELAY_BETWEEN_MSGS)

        except FloodWait as e:
            await asyncio.sleep(e.value)
            continue

        except Exception as e:
            failed += 1
            if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                users_collection.delete_one({"user_id": user["user_id"]})

    return sent, failed


async def broadcast_fast(client, reply_msg, all_users):
    tasks = []
    for i in range(0, len(all_users), BATCH_SIZE):
        batch = all_users[i:i + BATCH_SIZE]
        tasks.append(send_batch(client, reply_msg, batch))

    results = await asyncio.gather(*tasks)
    total_sent = sum(r[0] for r in results)
    total_failed = sum(r[1] for r in results)
    return total_sent, total_failed

# ---------------- BROADCAST COMMAND ---------------- #
@app.on_message(filters.command("broadcast") & filters.reply)
async def broadcast_cmd(client, message):
    if message.from_user.id != ADMIN_ID:
        return await message.reply("❌ You are not authorized.")

    reply_msg = message.reply_to_message
    all_users = list(users_collection.find())

    if BROADCAST_MODE == "fast":
        sent, failed = await broadcast_fast(client, reply_msg, all_users)
    else:
        sent, failed = await broadcast_safe(client, reply_msg, all_users)

    await message.reply(
        f"📢 Broadcast completed ({BROADCAST_MODE} mode)!\n✅ Sent: {sent}\n❌ Failed: {failed}"
    )

# ---------------- RUN ---------------- #
app.run()
