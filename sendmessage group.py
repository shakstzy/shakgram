from telethon import TelegramClient, sync
from telethon.tl.types import InputPeerUser
from telethon.tl.functions.messages import CreateChatRequest
from telethon.tl.functions.messages import AddChatUserRequest
import os
import asyncio

# Get API credentials from environment variables
api_id = os.getenv('TELEGRAM_API_ID')
api_hash = os.getenv('TELEGRAM_API_HASH')

if not api_id or not api_hash:
    raise ValueError("Please set TELEGRAM_API_ID and TELEGRAM_API_HASH environment variables")

# Create the client and connect
client = TelegramClient('session_name', api_id, api_hash)
client.start()

async def send_message(telegram, message, folder=None):
    # Find the user by username
    user = await client.get_entity(telegram)
    print(f"First Name: {user.first_name}")
    print(f"Last Name: {user.last_name}")
    # Send the message
    await client.send_message(user, message)

async def send_group_message(usernames, message, group_title="New Group"):
    try:
        # Create a new group chat
        print(f"Creating group: {group_title}")
        # Convert usernames to user entities first
        users = []
        for username in usernames:
            user = await client.get_entity(username)
            users.append(user)
            
        await client(CreateChatRequest(
            users=users,
            title=group_title
        ))
        
        # Add a small delay to ensure the group is created
        await asyncio.sleep(2)
        
        # Get all dialogs and find the one with matching title
        async for dialog in client.iter_dialogs():
            if dialog.title == group_title:
                # Send the message to the group
                await client.send_message(dialog.entity, message)
                print("Message sent successfully")
                break
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        import traceback
        traceback.print_exc()

# Run the async function
usernames = ["aryashivakumar", "outerscoped"]
client.loop.run_until_complete(send_group_message(
    usernames,
    "this is python talking",
    "TestGroup"
))
client.disconnect()