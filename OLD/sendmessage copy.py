from telethon import TelegramClient, sync
from telethon.tl.types import InputPeerUser
import os

# Get API credentials from environment variables
api_id = os.getenv('TELEGRAM_API_ID')
api_hash = os.getenv('TELEGRAM_API_HASH')

if not api_id or not api_hash:
    raise ValueError("Please set TELEGRAM_API_ID and TELEGRAM_API_HASH environment variables")

# Create the client and connect
client = TelegramClient('session_name', api_id, api_hash)
client.start()

async def send_message(telegram,message, folder):
    # Find the user by username
    user = await client.get_entity(telegram)
    print(f"First Name: {user.first_name}")
    print(f"Last Name: {user.last_name}")
    # Send the message
    await client.send_message(user, message)

# Run the async function
client.loop.run_until_complete(send_message("aryashivakumar", "yo g"))
client.disconnect()