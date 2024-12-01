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
        users = []
        user_entities = []
        for username in usernames:
            user = await client.get_entity(username)
            users.append(user)
            user_entities.append(user)
            
        await client(CreateChatRequest(
            users=users,
            title=group_title
        ))
        
        await asyncio.sleep(2)
        
        # Find the group we just created
        group_entity = None
        async for dialog in client.iter_dialogs():
            if dialog.title == group_title:
                group_entity = dialog.entity
                # Send initial message
                await client.send_message(group_entity, message)
                print("Initial message sent successfully")
                break
        
        if group_entity:
            # For each user, find their first image and send it to the group
            for user in user_entities:
                print(f"Searching for images in chat with {user.first_name}")
                async for message in client.iter_messages(user, limit=100):  # Limit to last 100 messages
                    if message.photo:
                        print(f"Found image in chat with {user.first_name}")
                        await client.send_file(group_entity, message.photo)
                        break  # Stop after finding first image
                
        print("All operations completed successfully")
        
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