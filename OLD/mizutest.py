from telethon import TelegramClient
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty
import os

# Replace with your API credentials
api_id = os.getenv('TELEGRAM_API_ID')
api_hash = os.getenv('TELEGRAM_API_HASH')

client = TelegramClient('session_name', api_id, api_hash)

async def find_chat_in_folder(folder_name, target_chat_name):
    # Step 1: Fetch all folders (filters)
    filters_result = await client(GetDialogFiltersRequest())
    
    # Step 2: Find the folder by name
    target_folder = None
    for folder in filters_result.filters:
        folder_title = getattr(folder, 'title', 'All Chats')
        if folder_title == folder_name:
            # Get the included peers from the folder
            included_peers = folder.include_peers
            break
    
    if not included_peers:
        print(f"No folder found with the name: {folder_name}")
        return

    # Step 3: Fetch chats from the folder
    print(f"Fetching chats in folder '{folder_name}'...")
    for peer in included_peers:
        dialog = await client.get_entity(peer)
        print(f"Chat: {dialog.title} (ID: {dialog.id})")
        if getattr(dialog, 'title', None) == target_chat_name:
            print(f"Found chat: {dialog.title} (ID: {dialog.id})")
            return dialog

    print(f"No chat found with the name: {target_chat_name}")

async def main():
    await client.start()
    
    # Define folder and chat names
    folder_name = "MIZU"
    target_chat_name = "Mizu <> VarysCapital"
    
    # Find the chat in the specified folder
    await find_chat_in_folder(folder_name, target_chat_name)

with client:
    client.loop.run_until_complete(main())
