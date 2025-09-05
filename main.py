import os
import asyncio
from pyrogram import Client, filters
from pymongo import MongoClient
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# ---------------- CONFIG ----------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

GREETING_TEXT = os.getenv("GREETING_TEXT", "👋 Hello {name}, welcome!")
GREETING_PHOTO = os.getenv("GREETING_PHOTO", None)  # File ID or URL

BUTTON1_TEXT = os.getenv("BUTTON1_TEXT", "Join Channel")
BUTTON1_URL = os.getenv("BUTTON1_URL", "https://t.me/example")
BUTTON2_TEXT = os.getenv("BUTTON2_TEXT", "Contact Support")
BUTTON2_URL = os.getenv("BUTTON2_URL", "https://t.me/example_support")

BROADCAST_MODE = os.getenv("BROADCAST_MODE", "safe")  # safe | fast
BATCH_SIZE = 100
DELAY_BETWEEN_MSGS = 0.5

# ---------------- INIT ----------------
app = Client("mybot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["telegram_bot"]
users_collection = db["users"]


# ---------------- HELPERS ----------------
async def send_greeting(client, user_id, name):
    buttons = [
        [InlineKeyboardButton(BUTTON1_TEXT, url=BUTTON1_URL)],
        [InlineKeyboardButton(BUTTON2_TEXT, url=BUTTON2_URL)]
    ]
    try:
        if GREETING_PHOTO:
            await client.send_photo(
                chat_id=user_id,
                photo=GREETING_PHOTO,
                caption=GREETING_TEXT.format(name=name),
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            await client.send_message(
                chat_id=user_id,
                text=GREETING_TEXT.format(name=name),
                reply_markup=InlineKeyboardMarkup(buttons)
            )
    except Exception as e:
        print(f"Error sending greeting: {e}")


# ---------------- HANDLERS ----------------
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    user_id = message.from_user.id
    name = message.from_user.first_name

    if not users_collection.find_one({"user_id": user_id}):
        users_collection.insert_one({"user_id": user_id})

    await send_greeting(client, user_id, name)


@app.on_message(filters.photo & filters.private)
async def get_file_id(client, message):
    """Helper: Send an image to bot to grab its file_id."""
    await message.reply(f"File ID: `{message.photo.file_id}`")


# ---------------- BROADCAST ----------------
async def broadcast_safe(client, reply_msg, all_users):
    sent, failed = 0, 0
    for user in all_users:
        try:
            await reply_msg.copy(user["user_id"])
            sent += 1
            await asyncio.sleep(DELAY_BETWEEN_MSGS)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            failed += 1
            users_collection.delete_one({"user_id": user["user_id"]})
    return sent, failed


async def send_batch(client, reply_msg, users):
    sent, failed = 0, 0
    for user in users:
        try:
            await reply_msg.copy(user["user_id"])
            sent += 1
            await asyncio.sleep(DELAY_BETWEEN_MSGS)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            failed += 1
            users_collection.delete_one({"user_id": user["user_id"]})
    return sent, failed


async def broadcast_fast(client, reply_msg, all_users):
    tasks = []
    for i in range(0, len(all_users), BATCH_SIZE):
        batch = all_users[i:i + BATCH_SIZE]
        tasks.append(send_batch(client, reply_msg, batch))

    results = await asyncio.gather(*tasks)
    sent = sum(r[0] for r in results)
    failed = sum(r[1] for r in results)
    return sent, failed


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

    await message.reply(f"📢 Broadcast done!\n✅ Sent: {sent}\n❌ Failed: {failed}")


# ---------------- RUN ----------------
print("✅ Bot started successfully (Render Worker)")
app.run()
