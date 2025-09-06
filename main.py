import os
import asyncio
import motor.motor_asyncio
from pyrogram import Client
from pyrogram.errors import PeerIdInvalid, UserIsBlocked
from aiohttp import web

# -----------------------
# Config from environment variables
# -----------------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
PORT = int(os.getenv("PORT", 10000))  # Render provides the PORT

# -----------------------
# Initialize bot and Mongo
# -----------------------
bot = Client("update_active_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
users_collection = mongo_client["telegram_bot"]["users"]

# -----------------------
# Update active users silently
# -----------------------
async def update_active_users():
    await bot.start()
    print("🚀 Bot started. Updating users...")

    total_users = await users_collection.count_documents({})
    print(f"📊 Total users in database: {total_users}")

    updated_active = 0
    updated_blocked = 0

    async for user in users_collection.find():
        try:
            # Silent check without sending messages
            await bot.get_chat(user["user_id"])
            await users_collection.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"started": True, "blocked": False}}
            )
            updated_active += 1
            print(f"✅ User {user['user_id']} marked as active")
        except (PeerIdInvalid, UserIsBlocked):
            await users_collection.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"started": False, "blocked": True}}
            )
            updated_blocked += 1
            print(f"❌ User {user['user_id']} is blocked or inactive")
        except Exception as e:
            print(f"⚠️ Error with user {user['user_id']}: {e}")
        await asyncio.sleep(0.2)  # prevent flood

    await bot.stop()
    print("✅ All users processed. Script finished!")
    print(f"📈 Active users updated: {updated_active}")
    print(f"📛 Blocked/inactive users updated: {updated_blocked}")

# -----------------------
# Minimal web server for Render
# -----------------------
async def handle(request):
    return web.Response(text="Bot is running ✅")

app = web.Application()
app.add_routes([web.get("/", handle)])

# -----------------------
# Main async function
# -----------------------
async def main():
    # Start bot update task
    asyncio.create_task(update_active_users())

    # Start web server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Web server running on port {PORT}")

    # Keep running
    await asyncio.Event().wait()

# -----------------------
# Run safely
# -----------------------
if __name__ == "__main__":
    asyncio.run(main())
