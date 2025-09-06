import os
import asyncio
import motor.motor_asyncio
from pyrogram import Client
from pyrogram.errors import FloodWait, PeerIdInvalid, UserIsBlocked
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
db = mongo_client["telegram_bot"]
users_collection = db["users"]

# -----------------------
# Refresh active users
# -----------------------
async def update_active_users():
    await bot.start()
    print("🚀 Bot started. Resetting active user flags...")

    # Reset all users to not started
    await users_collection.update_many({}, {"$set": {"started": False}})
    print("🗑️ Cleared all active flags. Now rechecking users...")

    total_users = await users_collection.count_documents({})
    updated_active = 0
    failed = 0
    checked = 0

    async for user in users_collection.find():
        try:
            # Sanity check: skip/remove invalid records
            if not isinstance(user, dict) or "user_id" not in user:
                print(f"🗑️ Removing invalid record: {user}")
                await users_collection.delete_one({"_id": user["_id"]})
                continue

            user_id = user["user_id"]

            # Try lightweight "typing" action to check if bot can DM
            await bot.send_chat_action(user_id, "typing")

            # Mark as active
            await users_collection.update_one(
                {"user_id": user_id},
                {"$set": {"started": True}}
            )
            updated_active += 1

        except (PeerIdInvalid, UserIsBlocked):
            failed += 1
            # User blocked or invalid, skip safely
        except FloodWait as e:
            print(f"⏳ FloodWait {e.x}s")
            await asyncio.sleep(e.x)
        except AttributeError as e:
            failed += 1
            uid = user.get("user_id", "unknown") if isinstance(user, dict) else "invalid"
            print(f"🗑️ Skipping broken user {uid}: AttributeError ({str(e)})")
            # Permanently remove broken user from DB
            await users_collection.delete_one({"user_id": uid})
        except Exception as e:
            failed += 1
            uid = user.get("user_id", "unknown") if isinstance(user, dict) else "invalid"
            print(f"⚠️ Error with user {uid}: {str(e)}")

        checked += 1

        # Progress log every 50 users
        if checked % 50 == 0 or checked == total_users:
            percent = round((checked / total_users) * 100, 2) if total_users > 0 else 0
            print(f"📊 Progress: {checked}/{total_users} users checked ({percent}%)")

        await asyncio.sleep(0.2)  # prevent flood

    await bot.stop()
    print("✅ User refresh complete!")
    print(f"👥 Total users in DB: {total_users}")
    print(f"📈 Active users: {updated_active}")
    print(f"🚫 Inactive/broken users: {failed}")

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
