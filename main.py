import os 
import asyncio
import datetime
import logging
import signal
from collections import defaultdict
import random

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
async def save_user(user_id: int, language=None):
    try:
        if not await users_collection.find_one({"user_id": user_id}):
            await users_collection.insert_one({
                "user_id": user_id,
                "joined_at": datetime.datetime.utcnow(),
                "started": False,
                "blocked": False,
                "language": language
            })
            logger.info(f"Saved user {user_id}")
    except Exception as e:
        logger.error(f"Error saving user {user_id}: {e}")

# -----------------------
# /start command
# -----------------------
@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    try:
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("Insta viral videos 🔥", url="https://heylink.me/Re.SauceSpace/")],
            [InlineKeyboardButton("Japanese corn 💦", url="https://t.me/+LFjrsp8T7bg5ZjU1")]
        ])
        
        await client.send_photo(
            chat_id=user_id,
            photo="https://graph.org/file/a632ff5bfea88c2e3bc4e-fc860032d437a5d866.jpg",
            caption=f"👋 Hi {message.from_user.mention}!\nWelcome! Enjoy the latest videos 🎬",
            reply_markup=buttons
        )
        logger.info(f"Full DM sent to {user_id} after /start")

        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"started": True, "blocked": False}},
            upsert=True
        )

    except Exception as e:
        logger.error(f"Error sending full DM to {user_id}: {e}")

# -----------------------
# Handle "🚀 Start Bot" button
# -----------------------
@bot.on_callback_query(filters.regex("start_bot"))
async def handle_start_button(client, callback_query):
    user_id = callback_query.from_user.id
    try:
        # Acknowledge button click
        await callback_query.answer("🚀 Starting bot...")

        # Call the /start logic (send media + buttons)
        fake_message = callback_query.message
        fake_message.from_user = callback_query.from_user
        await start(client, fake_message)

        # Mark user as active
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"started": True, "blocked": False}},
            upsert=True
        )
        logger.info(f"User {user_id} activated via button")

    except Exception as e:
        logger.error(f"Error handling start button for {user_id}: {e}")

# -----------------------
# Auto-approve join requests
# -----------------------
@bot.on_chat_join_request()
async def auto_approve(client: Client, request: ChatJoinRequest):
    user = request.from_user
    try:
        await request.approve()
        logger.info(f"Approved join request: {user.id}")
        await save_user(user.id, user.language_code)

        # Send greeting with button to start bot
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("Watch HD+ Videos 💦", callback_data="start_bot")]
        ])
        await client.send_photo(
            chat_id=user.id,
            photo="https://graph.org/file/5c159e3cb5694e24aefe2-34301124b07248c91f.jpg",
            reply_markup=buttons
        )
        logger.info(f"Greeting DM sent to {user.id}")
        
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

    async for user in users_collection.find({"started": True}):  # ✅ Only active users
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

    await stats_collection.update_one(
        {"_id": "broadcasts"},
        {"$inc": {"count": 1}, "$set": {"last": datetime.datetime.utcnow()}},
        upsert=True
    )
    await message.reply(f"📢 Broadcast complete!\n✅ Sent: {sent}\n❌ Failed: {failed}")
    logger.info(f"Broadcast finished: sent={sent}, failed={failed}")

# -----------------------
# Stats command (admins only)
# -----------------------
@bot.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats(client, message):
    try:
        total = await users_collection.count_documents({})
        active = await users_collection.count_documents({"started": True})
        non_active = total - active
        blocked = await users_collection.count_documents({"blocked": True})

        await stats_collection.update_one(
            {"_id": "latest_stats"},
            {"$set": {
                "total": total,
                "active": active,
                "non_active": non_active,
                "blocked": blocked,
                "updated_at": datetime.datetime.utcnow()
            }},
            upsert=True
        )

        stats_text = (
            f"📊 **Current Bot Stats**\n\n"
            f"👥 Total Users: {total}\n"
            f"✅ Active Users: {active}\n"
            f"❌ Non-Active Users: {non_active}\n"
            f"🚫 Blocked Users: {blocked}"
        )

        await message.reply(stats_text)
        logger.info(f"/stats used by {message.from_user.id}")

    except Exception as e:
        logger.error(f"Error in /stats: {e}")
        await message.reply("⚠️ Could not fetch stats.")

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
        runner = web.AppRunner(app_web)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        logger.info(f"HTTP server running on port {PORT}")
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
