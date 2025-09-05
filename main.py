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

# -----------------------
# Initialize bot and Mongo
# -----------------------
bot = Client("auto_approve_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = mongo_client["telegram_bot"]
users_collection = db["users"]
stats_collection = db["stats"]

# -----------------------
# Save user helper
# -----------------------
async def save_user(user_id: int):
    try:
        if not await users_collection.find_one({"user_id": user_id}):
            await users_collection.insert_one({"user_id": user_id, "joined_at": datetime.datetime.utcnow()})
            logger.info(f"Saved user {user_id}")
    except Exception as e:
        logger.error(f"Error saving user {user_id}: {e}")

# -----------------------
# /start command
# -----------------------
@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    try:
        await message.reply(
            "🤖 Hello! I am your Auto-Approve Bot.\n"
            "I approve join requests automatically and send welcome DMs.\n"
            "Admins can use /broadcast and /stats commands."
        )
        logger.info(f"/start used by {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error in /start: {e}")

# -----------------------
# /help command
# -----------------------
@bot.on_message(filters.command("help") & filters.private)
async def help_cmd(client, message):
    try:
        await message.reply(
            "📖 Commands:\n"
            "/start - Start bot\n"
            "/help - Show help\n"
            "Admin commands:\n"
            "/broadcast (reply to a message) - Send to all users\n"
            "/stats - Show bot statistics"
        )
        logger.info(f"/help used by {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error in /help: {e}")

# -----------------------
# Auto-approve join requests
# -----------------------
@bot.on_chat_join_request()
async def auto_approve(client: Client, request: ChatJoinRequest):
    user = request.from_user
    chat = request.chat
    try:
        await request.approve()
        logger.info(f"Approved join request: {user.id}")
        await save_user(user.id)

        # DM welcome
        text = f"👋 Hi {user.mention}!\nWelcome to **{chat.title}** 🎉"
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Updates Channel", url="https://t.me/YourChannel")],
            [InlineKeyboardButton("💬 Community Group", url="https://t.me/YourGroup")]
        ])
        await client.send_photo(
            chat_id=user.id,
            photo="https://telegra.ph/file/6db44f3a1d53c46b8b9f5.jpg",
            caption=text,
            reply_markup=buttons
        )
        logger.info(f"Sent DM welcome to {user.id}")

    except Exception as e:
        logger.error(f"Error approving user {user.id}: {e}")

# -----------------------
# Broadcast command
# -----------------------
@bot.on_message(filters.command("broadcast") & filters.user(ADMINS))
async def broadcast(client, message):
    if not message.reply_to_message:
        await message.reply("⚠️ Reply to a message to broadcast it")
        return
    sent = 0
    failed = 0
    async for user in users_collection.find():
        try:
            await message.reply_to_message.copy(user["user_id"])
            sent += 1
            await asyncio.sleep(0.5)
        except FloodWait as e:
            logger.warning(f"FloodWait {e.x}s for user {user['user_id']}")
            await asyncio.sleep(e.x)
        except Exception as e:
            logger.error(f"Broadcast failed for {user['user_id']}: {e}")
            failed += 1
    await stats_collection.update_one({"_id": "broadcasts"}, {"$inc": {"count": 1}}, upsert=True)
    await message.reply(f"📢 Broadcast complete! ✅{sent} ❌{failed}")
    logger.info(f"Broadcast finished: sent={sent}, failed={failed}")

# -----------------------
# Stats command
# -----------------------
@bot.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats(client, message):
    try:
        total = await users_collection.count_documents({})
        today = datetime.datetime.utcnow().date()
        users_today = await users_collection.count_documents({"joined_at": {"$gte": datetime.datetime.combine(today, datetime.time.min)}})
        broadcasts = await stats_collection.find_one({"_id": "broadcasts"})
        total_broadcasts = broadcasts["count"] if broadcasts else 0
        await message.reply(f"👥 Users: {total}\n📅 Today: {users_today}\n📢 Broadcasts: {total_broadcasts}")
        logger.info(f"/stats used by {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error in /stats: {e}")

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
    try:
        await bot.start()
        logger.info("Bot started")
        # HTTP server
        runner = web.AppRunner(app_web)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        logger.info(f"HTTP server running on port {PORT}")
        # Keep alive
        await asyncio.Event().wait()
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
    finally:
        await bot.stop()
        await runner.cleanup()
        logger.info("Bot stopped cleanly")

# -----------------------
# Run loop safely
# -----------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.stop()))
    loop.run_until_complete(main())
    loop.run_forever()
