import asyncio
import motor.motor_asyncio
from pyrogram import Client
from pyrogram.errors import PeerIdInvalid, UserIsBlocked

# -----------------------
# Config - replace with your credentials
# -----------------------
API_ID = int("24286461")
API_HASH = "fe4f9e040dfefaeb8715e12d1e4da9de"
BOT_TOKEN = "8301270850:AAExk4uI0HWxprXwBL-Bj64C9Vber60BjL0"
MONGO_URI = "mongodb+srv://oneposterman_db_user:opm567opm@cluster0.47gszb3.mongodb.net/?retryWrites=true&w=majority"

# -----------------------
# Initialize bot and Mongo
# -----------------------
bot = Client("update_active_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
users_collection = mongo_client["telegram_bot"]["users"]

# -----------------------
# Silent update function
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
            # Try a lightweight API call to check if the user is reachable
            await bot.get_chat(user["user_id"])  # silent, no message sent
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
        await asyncio.sleep(0.2)  # small delay to prevent flood

    await bot.stop()
    print("✅ All users processed. Script finished!")
    print(f"📈 Active users updated: {updated_active}")
    print(f"📛 Blocked/inactive users updated: {updated_blocked}")

# -----------------------
# Run the async function
# -----------------------
if name == "main":
    asyncio.run(update_active_users())
