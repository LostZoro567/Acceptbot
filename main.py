import asyncio
import logging
from pyrogram import Client
import motor.motor_asyncio
import os

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

# -----------------------
# Initialize bot and Mongo
# -----------------------
bot = Client("rebuild_active_users", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = mongo_client["telegram_bot"]
users_collection = db["users"]

# -----------------------
# Function to rebuild active users
# -----------------------
async def rebuild_active_users():
    async for user in users_collection.find():
        try:
            await bot.send_message(user["user_id"], "🔄 Rebuilding your active status...")
            await users_collection.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"started": True, "blocked": False}}
            )
            logger.info(f"✅ User {user['user_id']} marked as active")
        except Exception as e:
            await users_collection.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"started": False, "blocked": True}}
            )
            logger.warning(f"⚠️ User {user['user_id']} blocked/unreachable: {e}")
        await asyncio.sleep(0.5)

# -----------------------
# Main function
# -----------------------
async def main():
    await bot.start()
    logger.info("Bot started for rebuilding active users")
    await rebuild_active_users()
    await bot.stop()
    logger.info("Bot stopped. Rebuild complete.")

# -----------------------
# Run script using current loop
# -----------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
