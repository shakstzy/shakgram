from telethon import TelegramClient, sync
from telethon.tl.types import User
import os
from dotenv import load_dotenv
from telethon.tl.functions.messages import GetDialogFiltersRequest

# Load environment variables
load_dotenv()

# Your Telegram API credentials
# Get these from https://my.telegram.org/
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

async def send_message(message):
    # Find the user by username
    client = TelegramClient('user_session.session', API_ID, API_HASH)
    user = await client.get_entity('lifeofshak')
    print(f"First Name: {user.first_name}")
    print(f"Last Name: {user.last_name}")
    # Send the message
    await client.send_message(user, message)

async def get_names_from_folder(folder_name):
    print("Starting client connection...")
    client = TelegramClient('user_session.session', API_ID, API_HASH)
    await client.start()
    
    try:
        print("\nFetching folder list...")
        # Get folder list first
        folder_list = await client(GetDialogFiltersRequest())
        print(f"Folder list type: {type(folder_list)}")
        print(f"Folder list content: {folder_list}")
        folders = folder_list
        print(f"Found {len(folders.filters)} folders")
        
        # Find DEVSTUDIO folder
        devstudio_folder = None
        for folder in folders:  # Use the converted list
            print(f"Folder: {folder.title if hasattr(folder, 'title') else 'Untitled'}")
            if hasattr(folder, 'title') and folder.title == "DEVSTUDIO":
                devstudio_folder = folder
                break
        
        if not devstudio_folder:
            print("DEVSTUDIO folder not found!")
            return []
            
        print(f"\nFound DEVSTUDIO folder, getting chats...")
        # Now get chats from this specific folder
        dialogs = await client.get_dialogs(folder=devstudio_folder.id)
        contacts = []
        
        for dialog in dialogs:
            if isinstance(dialog.entity, User):
                contacts.append(dialog.entity)
        
        print(f"Found {len(contacts)} contacts in DEVSTUDIO folder")
        
        # Extract names from contacts
        names = []
        for contact in contacts:
            full_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
            if full_name:
                names.append(full_name)
                print(f"Added contact: {full_name}")
        
        return names
    finally:
        print("Disconnecting client...")
        await client.disconnect()

# Run the script
if __name__ == "__main__":
    import asyncio
    names = asyncio.run(get_names_from_folder(None))
    
    # Print results
    if names:
        print("\nNames found in contacts:")
        for i, name in enumerate(names, 1):
            print(f"{i}. {name}")
        print(f"\nTotal names found: {len(names)}")
