import os
import asyncio
import datetime
import logging
import signal

from pyrogram import Client, filters
from pyrogram.types import ChatJoinRequest, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
import motor.motor_asyncio
from aiohttp import web

# -----------------------
# Logging setup
# -----------------------
logging.basicConfig(
    format='[%(asctime)s] %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -----------------------
# Config
# -----------------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMINS_ENV = os.getenv("ADMINS", "")
ADMINS = list(map(int, filter(None, ADMINS_ENV.split(","))))
PORT = int(os.getenv("PORT", 10000))
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBotUsername")

# -----------------------
# Initialize bot and Mongo
# -----------------------
bot = Client("auto_approve_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = mongo_client["telegram_bot"]
users_collection = db["users"]

# -----------------------
# Save user helper
# -----------------------
async def save_user(user_id: int, language=None):
    try:
        existing = await users_collection.find_one({"user_id": user_id})
        if not existing:
            await users_collection.insert_one({
                "user_id": user_id,
                "joined_at": datetime.datetime.utcnow(),
                "started": True,   # user is saved only if they actually pressed /start
                "blocked": False,
                "language": language
            })
            logger.info(f"Saved new active user {user_id}")
        else:
            await users_collection.update_one(
                {"user_id": user_id},
                {"$set": {"started": True, "blocked": False}}
            )
            logger.info(f"Updated existing user {user_id} as active")
    except Exception as e:
        logger.error(f"Error saving user {user_id}: {e}")

# -----------------------
# /start command
# -----------------------
@bot.on_message(filters.private & filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    payload = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None

    try:
        # Save user ONLY when they press /start
        await save_user(user_id, message.from_user.language_code)

        # Send welcome photo + buttons
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Updates Channel", url="https://t.me/+LFjrsp8T7bg5ZjU1")],
            [InlineKeyboardButton("💬 Community Group", url="https://heylink.me/Re.SauceSpace/")]
        ])

        await client.send_photo(
            chat_id=user_id,
            photo="https://graph.org/file/a632ff5bfea88c2e3bc4e-fc860032d437a5d866.jpg",
            reply_markup=buttons
        )

        logger.info(f"Full DM sent to {user_id} after pressing start")

    except Exception as e:
        logger.error(f"Error sending full DM to {user_id}: {e}")
        
# -----------------------
# Auto-approve join requests
# -----------------------
@bot.on_chat_join_request()
async def on_join_request(client, chat_join_request: ChatJoinRequest):
    try:
        # Approve the join request
        await chat_join_request.approve()
        user = chat_join_request.from_user

        # Send Start Bot button in DM (will only save when user actually presses it)
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶ Start Bot", url=f"https://t.me/Jennyrerobot?start=auto_approved")]
        ])

        try:
            await client.send_photo(
                chat_id=user.id,
                photo="https://graph.org/file/5c159e3cb5694e24aefe2-34301124b07248c91f.jpg",
                reply_markup=buttons
            )
            logger.info(f"Start button sent to user {user.id}")
        except Exception:
            logger.warning(f"Cannot DM user {user.id} yet; they must press Start manually.")

    except Exception as e:
        logger.error(f"Error approving user {user.id}: {e}")

# -----------------------
# Broadcast command (admins only)
# -----------------------
@bot.on_message(filters.command("broadcast") & filters.user(ADMINS))
async def broadcast(client, message):
    if not message.reply_to_message:
        await message.reply("⚠️ Reply to a message to broadcast it")
        return

    sent = 0
    failed = 0

    async for user in users_collection.find({"started": True, "blocked": False}):
        try:
            await message.reply_to_message.copy(user["user_id"])
            sent += 1
            await asyncio.sleep(0.5)
        except FloodWait as e:
            logger.warning(f"FloodWait {e.x}s for user {user['user_id']}")
            await asyncio.sleep(e.x)
        except Exception:
            failed += 1
            await users_collection.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"blocked": True}}
            )

    await message.reply(f"📢 Broadcast complete!\n✅ Sent: {sent}\n❌ Failed: {failed}")
    logger.info(f"Broadcast finished: sent={sent}, failed={failed}")

# -----------------------
# Cleanup command (admins only)
# -----------------------
@bot.on_message(filters.command("cleanup") & filters.user(ADMINS))
async def cleanup(client, message):
    try:
        result = await users_collection.delete_many({"blocked": True})
        await message.reply(f"🧹 Cleanup complete!\n🗑️ Removed {result.deleted_count} blocked users")
        logger.info(f"Cleanup removed {result.deleted_count} blocked users")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        await message.reply("⚠️ Cleanup failed.")

# -----------------------
# Minimal HTTP server for Render
# -----------------------
async def handle(request):
    return web.Response(text="Bot running!")

app_web = web.Application()
app_web.add_routes([web.get("/", handle)])

# -----------------------
# Main async function
# -----------------------
async def main():
    await bot.start()
    logger.info("Bot started")

    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"HTTP server running on port {PORT}")

    await asyncio.Event().wait()  # Keep running

# -----------------------
# Run loop safely
# -----------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.stop()))
    loop.run_until_complete(main())
    loop.run_forever()
