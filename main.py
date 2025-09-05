import os
from pyrogram import Client, filters, types
from pymongo import MongoClient

# ---------------- CONFIG ---------------- #
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# Telegram Bot Client
app = Client("autobot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# MongoDB Client
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["telegram_bot"]
users_collection = db["users"]

# ---------------- HANDLERS ---------------- #

# 1. Auto-accept join requests
@app.on_chat_join_request()
async def auto_accept(client, request: types.ChatJoinRequest):
    try:
        # Approve request
        await client.approve_chat_join_request(request.chat.id, request.from_user.id)
        
        # Save user to DB
        if not users_collection.find_one({"user_id": request.from_user.id}):
            users_collection.insert_one({
                "user_id": request.from_user.id,
                "username": request.from_user.username
            })
        
        # Greeting message with media + buttons
        buttons = [
            [types.InlineKeyboardButton("Visit Channel", url="https://t.me/YourChannel")],
            [types.InlineKeyboardButton("Support", url="https://t.me/YourSupport")]
        ]
        await client.send_photo(
            chat_id=request.from_user.id,
            photo="https://example.com/welcome.jpg",  # Replace with your image URL/file_id
            caption=f"Hello {request.from_user.mention}, welcome to our channel 🎉",
            reply_markup=types.InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        print("Error in join request:", e)


# 2. Save user on /start
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    user_id = message.from_user.id
    if not users_collection.find_one({"user_id": user_id}):
        users_collection.insert_one({
            "user_id": user_id,
            "username": message.from_user.username
        })
    await message.reply("✅ You are now registered for updates!")


# 3. Broadcast command
@app.on_message(filters.command("broadcast") & filters.reply)
async def broadcast_cmd(client, message):
    if message.from_user.id != int(os.getenv("ADMIN_ID")):
        return await message.reply("❌ You are not authorized.")

    reply_msg = message.reply_to_message
    all_users = users_collection.find()

    sent_count, fail_count = 0, 0
    for user in all_users:
        try:
            await reply_msg.copy(user["user_id"])
            sent_count += 1
        except Exception:
            fail_count += 1
    
    await message.reply(f"📢 Broadcast finished!\n✅ Sent: {sent_count}\n❌ Failed: {fail_count}")


# ---------------- RUN ---------------- #
app.run()
