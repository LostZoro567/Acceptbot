import os
import asyncio
import datetime
from pyrogram import Client, filters
from pyrogram.types import ChatJoinRequest, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
import motor.motor_asyncio
from aiohttp import web

# =======================
# 🔹 CONFIG from env variables
# =======================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMINS_ENV = os.getenv("ADMINS", "")
ADMINS = list(map(int, filter(None, ADMINS_ENV.split(","))))

# =======================
# Initialize Bot
app = Client("auto_accept_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Initialize MongoDB
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = mongo_client["telegram_bot"]
users_collection = db["users"]
stats_collection = db["stats"]

# =======================
# Save user to DB
async def save_user(user_id: int):
    if not await users_collection.find_one({"user_id": user_id}):
        await users_collection.insert_one({"user_id": user_id, "joined_at": datetime.datetime.utcnow()})

# =======================
# /start command
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply(
        "🤖 Hello! I am your Auto-Approve Bot.\n\n"
        "I approve join requests automatically and send welcome DMs.\n"
        "Admins can use /broadcast and /stats commands."
    )

# /help command
@app.on_message(filters.command("help") & filters.private)
async def help_cmd(client, message):
    await message.reply(
        "📖 **Commands:**\n\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n\n"
        "**Admin Commands:**\n"
        "/broadcast (reply to a message) - Send message to all saved users\n"
        "/stats - Show user & broadcast stats"
    )

# =======================
# Auto-approve join requests
@app.on_chat_join_request()
async def auto_approve(client: Client, request: ChatJoinRequest):
    user = request.from_user
    chat = request.chat
    try:
        await request.approve()
        await save_user(user.id)

        # Custom DM welcome
        welcome_text = (
            f"👋 Hi {user.mention}!\n\n"
            f"Welcome to **{chat.title}** 🎉\n"
            f"We’re glad to have you here 🚀"
        )

        buttons = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📢 Updates Channel", url="https://t.me/YourChannel")],
                [InlineKeyboardButton("💬 Community Group", url="https://t.me/YourGroup")],
            ]
        )

        await client.send_photo(
            chat_id=user.id,
            photo="https://telegra.ph/file/6db44f3a1d53c46b8b9f5.jpg",
            caption=welcome_text,
            reply_markup=buttons
        )

        print(f"✅ Approved {user.first_name} and saved to MongoDB.")

    except Exception as e:
        print(f"⚠️ Error: {e}")

# =======================
# Broadcast command
@app.on_message(filters.command("broadcast") & filters.user(ADMINS))
async def broadcast(client, message):
    if not message.reply_to_message:
        await message.reply("⚠️ Please reply to a message to broadcast it.")
        return

    sent_count = 0
    failed_count = 0

    async for user in users_collection.find():
        try:
            await message.reply_to_message.copy(user["user_id"])
            sent_count += 1
            await asyncio.sleep(0.5)
        except FloodWait as e:
            print(f"⚠️ FloodWait: Sleeping {e.x} seconds")
            await asyncio.sleep(e.x)
        except:
            failed_count += 1
            await users_collection.delete_one({"user_id": user["user_id"]})

    # Increase broadcast counter
    await stats_collection.update_one(
        {"_id": "broadcasts"},
        {"$inc": {"count": 1}},
        upsert=True
    )

    await message.reply(f"📢 Broadcast finished!\n✅ Sent: {sent_count}\n❌ Failed: {failed_count}")

# =======================
# Stats command
@app.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats(client, message):
    total_users = await users_collection.count_documents({})
    today = datetime.datetime.utcnow().date()
    last_7_days = today - datetime.timedelta(days=7)

    users_today = await users_collection.count_documents({
        "joined_at": {"$gte": datetime.datetime.combine(today, datetime.time.min)}
    })
    users_week = await users_collection.count_documents({
        "joined_at": {"$gte": datetime.datetime.combine(last_7_days, datetime.time.min)}
    })
    broadcasts = await stats_collection.find_one({"_id": "broadcasts"})
    total_broadcasts = broadcasts["count"] if broadcasts else 0

    await message.reply(
        f"📊 **Bot Statistics**\n\n"
        f"👥 Total Users: **{total_users}**\n"
        f"📅 Joined Today: **{users_today}**\n"
        f"📆 Joined Last 7 Days: **{users_week}**\n"
        f"📢 Broadcasts Sent: **{total_broadcasts}**"
    )

# =======================
# Minimal HTTP server for Render
async def handle(request):
    return web.Response(text="Bot is running!")

app_web = web.Application()
app_web.add_routes([web.get("/", handle)])

# =======================
# Main function (async for Render)
async def main():
    await app.start()
    print("🤖 Bot started in Web-Service Mode (Render)...")
    # Run HTTP server in background
    asyncio.create_task(web._run_app(app_web, host="0.0.0.0", port=int(os.environ.get("PORT", 10000))))
    # Keep the bot alive
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
