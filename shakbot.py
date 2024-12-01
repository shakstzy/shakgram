from telethon import TelegramClient, sync
from telethon.tl.types import InputPeerUser
from telethon.tl.functions.messages import CreateChatRequest
import os
import asyncio
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
import re  # Make sure to import the re module for regular expressions
import concurrent.futures
from datetime import datetime, timezone
import json

# Get API credentials from environment variables
api_id = os.getenv('TELEGRAM_API_ID')
api_hash = os.getenv('TELEGRAM_API_HASH')
attio_api_key = os.getenv('ATTIO_API_KEY')

if not api_id or not api_hash:
    raise ValueError("Please set TELEGRAM_API_ID and TELEGRAM_API_HASH environment variables")

if not attio_api_key:
    raise ValueError("Please set ATTIO_API_KEY environment variable")

# Create the client and connect
client = TelegramClient('session_name', api_id, api_hash)
client.start()

# Google Drive API setup
SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/documents']
SERVICE_ACCOUNT_FILE = 'google.json'  # Update with your service account file path

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)
docs_service = build('docs', 'v1', credentials=credentials)

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

async def copy_google_doc_template(company_name, emails):
    """Copy a Google Doc template and return the link to the new document."""
    try:
        # Search for the template file
        query = "name contains 'Operator Memorandum of Understanding Template'"
        results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name, owners)').execute()
        files = results.get('files', [])

        if not files:
            print("Template file not found.")
            return None

        template_id = files[0]['id']
        original_owner_email = files[0]['owners'][0]['emailAddress']  # Get the original owner's email
        
        # Create a copy with the new name including the company name
        file_metadata = {
            'name': f'Operator Memorandum of Understanding Template - {company_name}',
            'mimeType': 'application/vnd.google-apps.document'
        }
        
        copied_file = drive_service.files().copy(fileId=template_id, body=file_metadata).execute()
        document_link = f"https://docs.google.com/document/d/{copied_file['id']}/edit"
        
        # Replace [operator] with the company name in the new document
        await replace_text_in_document(copied_file['id'], company_name)

        # Transfer ownership to the specified emails
        for email in emails:
            await transfer_ownership(copied_file['id'], email)

        return document_link

    except Exception as e:
        print(f"An error occurred while copying the Google Doc: {str(e)}")
        return None

async def replace_text_in_document(document_id, company_name, signatory_name):
    """Replace [operator] and [Signatory] in the document with the company name and signatory name, case-insensitively."""
    requests = []

    # Replace [operator] with company name
    requests.append({
        'replaceAllText': {
            'replaceText': company_name,
            'containsText': {
                'text': '[operator]',  # This will be used for matching
                'matchCase': False  # Set to False for case-insensitive matching
            }
        }
    })

    # Replace [Signatory] with signatory name
    requests.append({
        'replaceAllText': {
            'replaceText': signatory_name,
            'containsText': {
                'text': '[Signatory]',  # This will be used for matching
                'matchCase': False  # Set to False for case-insensitive matching
            }
        }
    })
    
    # Execute the batch update request
    result = docs_service.documents().batchUpdate(documentId=document_id, body={'requests': requests}).execute()
    print(f"Replaced [operator] with '{company_name}' and [Signatory] with '{signatory_name}' in document ID: {document_id}")

async def share_document(document_id, emails):
    """Share the document with the specified email addresses."""
    try:
        for email in emails:
            permission = {
                'type': 'user',
                'role': 'writer',  # or 'reader' depending on the access level you want to give
                'emailAddress': email
            }
            drive_service.permissions().create(
                fileId=document_id,
                body=permission,
                fields='id'
            ).execute()
            print(f"Document shared with {email}")
    except Exception as e:
        print(f"An error occurred while sharing the document: {str(e)}")

async def transfer_ownership(document_id, new_owner_email):
    """Transfer ownership of the document to the specified email address."""
    try:
        permission = {
            'type': 'user',
            'role': 'owner',
            'emailAddress': new_owner_email
        }
        drive_service.permissions().create(
            fileId=document_id,
            body=permission,
            transferOwnership=True,  # This is crucial for transferring ownership
            fields='id'
        ).execute()
        print(f"Ownership of document ID {document_id} transferred to {new_owner_email}")
    except Exception as e:
        print(f"An error occurred while transferring ownership: {str(e)}")

async def copy_and_share_document(document_id, company_name, signatory_name):
    """Copy a Google Document, rename it, share it with the same users, and replace [operator] and [Signatory] with the company name and signatory name."""
    try:
        # Retrieve the original document
        original_doc = drive_service.files().get(fileId=document_id, fields='id, name, parents, permissions').execute()
        
        # Get the folder ID (assuming it has only one parent)
        folder_id = original_doc.get('parents', [None])[0]
        
        # Create a copy of the document with the new name
        copied_file_metadata = {
            'name': f"Operator Memorandum of Understanding - {company_name}",
            'parents': [folder_id],  # Place the copy in the same folder
            'mimeType': 'application/vnd.google-apps.document'
        }
        
        copied_file = drive_service.files().copy(fileId=document_id, body=copied_file_metadata).execute()
        copied_document_id = copied_file['id']
        print(f"Document copied and renamed successfully: https://docs.google.com/document/d/{copied_document_id}/edit")

        # Share the copied document with the same users
        for permission in original_doc.get('permissions', []):
            if permission['role'] in ['writer', 'reader']:  # Only share with writers and readers
                new_permission = {
                    'type': permission['type'],
                    'role': permission['role'],
                    'emailAddress': permission.get('emailAddress')  # Get the email address if available
                }
                drive_service.permissions().create(
                    fileId=copied_document_id,
                    body=new_permission,
                    fields='id'
                ).execute()
                print(f"Shared document with {new_permission['emailAddress']} as {new_permission['role']}")

        # Replace [operator] and [Signatory] in the new document
        await replace_text_in_document(copied_document_id, company_name, signatory_name)

    except Exception as e:
        print(f"An error occurred while copying and sharing the document: {str(e)}")

def get_attio_lists(headers):
    """Fetch all lists from Attio and return them."""
    url = "https://api.attio.com/v2/lists"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        lists = response.json().get('data', [])
        print("\nAvailable Attio lists:")
        for idx, lst in enumerate(lists, 1):
            list_id = lst['id']['list_id']
            print(f"{idx}. {lst.get('name', 'Unnamed')} (List ID: {list_id})")
        return lists
    else:
        print(f"Error fetching lists: {response.status_code}")
        return None

def choose_list(lists):
    """Allow the user to choose a list by ID."""
    while True:
        try:
            choice = int(input("\nEnter the number of the list you want to work with: "))
            if 1 <= choice <= len(lists):
                selected_list = lists[choice - 1]
                selected_list_id = selected_list['id']['list_id']
                print(f"\nSelected List: {selected_list['name']}")
                print(f"List ID: {selected_list_id}")
                return selected_list_id
            else:
                print("Invalid selection. Please choose a number from the list.")
        except ValueError:
            print("Please enter a valid number.")

def get_company_name(company_id, headers):
    """Fetch a single company's name by ID."""
    url = f"https://api.attio.com/v2/objects/companies/records/{company_id}"
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        company_data = response.json().get('data', {})
        return company_data.get('values', {}).get('name', [{}])[0].get('value', 'Unknown')
    except:
        return 'Unknown'

def get_list_entries_with_companies(list_id, headers):
    """Fetch all entries and look up company names in parallel."""
    list_url = f"https://api.attio.com/v2/lists/{list_id}/entries/query"
    
    try:
        all_entries = []
        cursor = None
        
        # Fetch all entries using pagination
        while True:
            payload = {"pagination": {"limit": 100}}
            if cursor:
                payload["pagination"]["cursor"] = cursor
            
            response = requests.post(list_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            entries = data.get('data', [])
            if not entries:
                break
                
            all_entries.extend(entries)
            cursor = data.get('pagination', {}).get('next_cursor')
            if not cursor:
                break
        
        print(f"\nFound {len(all_entries)} entries:")
        
        # Create a thread pool for parallel requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {}
            
            # Start all requests in parallel
            for entry in all_entries:
                company_id = entry.get('parent_record_id')
                if company_id:
                    futures[executor.submit(get_company_name, company_id, headers)] = entry
            
            # Process results as they complete
            for future in concurrent.futures.as_completed(futures):
                entry = futures[future]
                company_name = future.result()
                company_id = entry.get('parent_record_id')
                entry_values = entry.get('entry_values', {})
                stage = entry_values.get('stage', [{}])[0].get('status', {}).get('title', 'No Status') if entry_values.get('stage') else 'No Status'
                
                print(f"Entry ID: {entry['id']['entry_id']}")
                print(f"Status: {stage}")
                print(f"Company ID: {company_id}")
                print(f"Company Name: {company_name}")
                print("-" * 30)
        
        return all_entries
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {str(e)}")
        return None

def get_list_stages(list_id, headers):
    """Fetch all stages for a list."""
    # First get the attribute ID
    url = f"https://api.attio.com/v2/lists/{list_id}/attributes"
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        attributes = response.json().get('data', [])
        stage_attribute = next((attr for attr in attributes if attr.get('title') == 'Stage'), None)
        
        if not stage_attribute:
            print("\nERROR: No Stage attribute found")
            return None
            
        # Get the attribute ID and slug
        attribute_id = stage_attribute.get('id', {}).get('attribute_id')
        attribute_slug = stage_attribute.get('api_slug', 'stage')
        
        # Get the statuses using the correct endpoint
        statuses_url = f"https://api.attio.com/v2/lists/{list_id}/attributes/{attribute_slug}/statuses"
        statuses_response = requests.get(statuses_url, headers=headers)
        statuses_response.raise_for_status()
        
        statuses_data = statuses_response.json().get('data', [])
        
        print("\nAvailable stages:")
        stages = {}
        for status in statuses_data:
            title = status.get('title', '')
            status_id = status.get('id', {}).get('status_id')
            if title and status_id:
                stages[title.lower()] = status_id
                print(f"- {title}")
                print(f"  ID: {status_id}")
        
        if not stages:
            print("No stages found")
            print("\nRaw Statuses Response:")
            print(statuses_response.json())
            
        return stages
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching list stages: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print("Response:", e.response.text)
        return None

def update_entry_stage(list_id, entry_id, new_stage_name, headers):
    """Update the stage of a list entry using stage name."""
    url = f"https://api.attio.com/v2/lists/{list_id}/entries/{entry_id}"
    
    # Updated payload structure based on API docs
    payload = {
        "data": {  # Added data wrapper
            "entry_values": {
                "stage": [{
                    "status": new_stage_name
                }]
            }
        }
    }
    
    try:
        response = requests.patch(url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"Successfully updated stage for entry {entry_id} to '{new_stage_name}'")
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error updating entry stage: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print("Response:", e.response.text)
        return None

def fetch_all_companies(headers, filter_tag=None):
    """Fetch all companies and optionally filter by tag."""
    url = "https://api.attio.com/v2/objects/companies/records/query"
    
    all_companies = []
    filtered_companies = []
    offset = 0
    limit = 500
    
    try:
        while True:
            payload = {
                "include_values": ["name", "project_tag_5"],
                "limit": limit,
                "offset": offset
            }
            
            try:
                response = requests.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                
                companies_batch = data.get('data', [])
                if not companies_batch:
                    break
                
                all_companies.extend(companies_batch)
                offset += len(companies_batch)
                
                if len(companies_batch) < limit:
                    break
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 400:
                    break
                raise
        
        # Process all companies at once
        if filter_tag:
            for company in all_companies:
                values = company.get('values', {})
                name = values.get('name', [{}])[0].get('value', 'Unknown') if values.get('name') else 'Unknown'
                record_id = company['id']['record_id']
                tags = [tag['option']['title'] for tag in values.get('project_tag_5', [])]
                
                if filter_tag in tags:
                    filtered_companies.append({
                        'name': name,
                        'id': record_id,
                        'tags': tags
                    })
            
            # Print results in one go
            total_found = len(filtered_companies)
            print(f"\nCompanies with tag '{filter_tag}':")
            print("-" * 80)  # Wider separator for better readability
            for company in filtered_companies:
                print(f"Record ID: {company['id']}")
                print(f"Company: {company['name']}")
                print(f"Tags: {', '.join(company['tags'])}")
                print("-" * 80)
            print(f"\nTotal companies found with tag '{filter_tag}': {total_found}")
            
            return filtered_companies
            
        return all_companies
        
    except requests.exceptions.RequestException as e:
        print(f"Error: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print("Response:", e.response.text)
        return None

headers = {
    'Authorization': f'Bearer {attio_api_key}',
    'Content-Type': 'application/json'
}

# Example usage:
# list_id = "00f50bb3-70d6-40f2-9165-712acdc33c24"
# entries = get_list_entries_with_companies(list_id, headers)

# update_entry_stage(
#     "00f50bb3-70d6-40f2-9165-712acdc33c24",  # list_id
#     "fd569bb3-5bbb-5710-8bb0-46af4160f680",  # entry_id
#     "Follow Up",  # stage name
#     headers
# )

# stages = get_list_stages(list_id, headers)

# tag_name = "Node Operator"  # Specify the tag name you want to filter by
# companies = fetch_companies_by_tag(tag_name, headers)

# Usage:
# Fetch all companies
# companies = fetch_all_companies(headers)

# Or fetch companies with specific tag
# companies = fetch_all_companies(headers, filter_tag="AI")

def get_last_telegram_message(chat_identifier):
    """Helper function to get last message info from a Telegram chat."""
    async def _get_message_info(chat_identifier):
        try:
            # Use the existing authorized client
            chat = await client.get_entity(chat_identifier)
            messages = await client.get_messages(chat, limit=1)
            
            if messages and len(messages) > 0:
                last_message = messages[0]
                timestamp = last_message.date
                
                now = datetime.now(timezone.utc)
                time_diff = now - timestamp
                hours_elapsed = time_diff.total_seconds() / 3600
                
                sender = await last_message.get_sender()
                sender_name = f"{getattr(sender, 'first_name', '')} {getattr(sender, 'last_name', '')}".strip()
                if not sender_name and hasattr(sender, 'title'):
                    sender_name = sender.title
                
                message_text = last_message.message if hasattr(last_message, 'message') else "No text content"
                
                return {
                    'timestamp': timestamp,
                    'hours_elapsed': hours_elapsed,
                    'sender': sender_name,
                    'message': message_text
                }
            return None
            
        except Exception as e:
            print(f"Error getting message info: {str(e)}")
            return None

    # Use the existing event loop
    try:
        result = client.loop.run_until_complete(_get_message_info(chat_identifier))
        
        if result:
            print(f"\nLast Message Info:")
            print("-" * 50)
            print(f"Time: {result['timestamp']}")
            print(f"Hours elapsed: {result['hours_elapsed']:.2f}")
            print(f"Sender: {result['sender']}")
            print(f"Message: {result['message']}")
            print("-" * 50)
            
        return result
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

# Example usage
# message_info = get_last_telegram_message("Adi <> Chainsight")

def get_list_entries_by_stage(headers, list_name, stage_name):
    """Get all entries from a specified list with a specific stage status."""
    
    # Get all lists and find the specified list
    lists = get_attio_lists(headers)
    if not lists:
        return None
        
    # Case insensitive match for list name
    target_list = next((lst for lst in lists if lst.get('name', '').lower() == list_name.lower()), None)
    if not target_list:
        print(f"\nList '{list_name}' not found")
        return None
        
    list_id = target_list['id']['list_id']
    
    # Get all entries from the list
    entries = get_list_entries_with_companies(list_id, headers)
    if not entries:
        return None
        
    # Filter entries by stage status and extract company info
    matching_companies = []
    
    for entry in entries:
        entry_values = entry.get('entry_values', {})
        current_stage = entry_values.get('stage', [{}])[0].get('status', {}).get('title', '')
        
        if current_stage == stage_name:
            company_id = entry.get('parent_record_id')
            company_name = get_company_name(company_id, headers)
            matching_companies.append({
                'id': company_id,
                'name': company_name,
                'entry_id': entry['id']['entry_id'],
                'list_name': list_name,
                'stage': stage_name
            })
    
    print(f"\nCompanies in '{list_name}' with stage '{stage_name}':")
    print("-" * 50)
    for company in matching_companies:
        print(f"Company: {company['name']}")
        print(f"Company ID: {company['id']}")
        print(f"Entry ID: {company['entry_id']}")
        print(f"List: {company['list_name']}")
        print(f"Stage: {company['stage']}")
        print("-" * 50)
    
    return matching_companies

def get_company_telegram_handles(company_name, headers):
    """Get telegram handles for employees of a company."""
    url = "https://api.attio.com/v2/objects/people/records/query"
    domain = f"{company_name.strip().lower()}.com"
    
    try:
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        telegram_info = []
        for record in data.get('data', []):
            values = record.get('values', {})
            
            # Check if person has email with matching domain
            email_addresses = values.get('email_addresses', [])
            has_company_email = any(
                email.get('email_domain') == domain 
                for email in email_addresses
            )
            
            if has_company_email:
                telegram_entries = values.get('telegram', [])
                if telegram_entries:
                    telegram = telegram_entries[0].get('value')
                    if telegram:
                        # Get name from personal-name field
                        name_entries = values.get('name', [])
                        full_name = 'Unknown'
                        if name_entries:
                            name_data = name_entries[0]
                            first_name = name_data.get('first_name', '')
                            last_name = name_data.get('last_name', '')
                            # Use full_name if available, otherwise combine first and last
                            full_name = name_data.get('full_name') or f"{first_name} {last_name}".strip()
                        
                        telegram_info.append({
                            'handle': telegram,
                            'name': full_name,
                            'email_domain': domain
                        })
        
        if telegram_info:
            print(f"\nFound {len(telegram_info)} telegram handles for {domain} employees:")
            for info in telegram_info:
                print(f"Name: {info['name']}")
                print(f"Telegram: @{info['handle']}")
                print("-" * 50)
        else:
            print(f"\nNo telegram handles found for {domain} employees")
            
        return telegram_info
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching telegram handles: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print("Response:", e.response.text)
        return None

def get_company_telegrams(companies, headers):
    """Get telegram handles for a list of companies."""
    all_telegram_handles = []
    
    print("\nFetching telegram handles for companies...")
    for company in companies:
        print(f"\nLooking up telegram handles for {company['name']}:")
        telegram_handles = get_company_telegram_handles(company['name'], headers)
        if telegram_handles:
            all_telegram_handles.extend([{
                'company_name': company['name'],
                'company_id': company['id'],
                'telegram_handle': handle['handle'],
                'person_name': handle['name']
            } for handle in telegram_handles])
    
    if all_telegram_handles:
        print("\nAll Telegram Handles Found:")
        print("-" * 50)
        for handle in all_telegram_handles:
            print(f"Company: {handle['company_name']}")
            print(f"Person: {handle['person_name']}")
            print(f"Telegram: @{handle['telegram_handle']}")
            print("-" * 50)
    
    return all_telegram_handles

# Usage example:
# Get companies from list
# companies = get_list_entries_by_stage(headers, "Layer", "Email Sent")
# print(companies)
# # Then get their telegram handles if needed
# if companies:
#     telegram_handles = get_company_telegrams(companies, headers)

def get_list_id_by_name(list_name, headers):
    """Get list ID from list name (case insensitive)."""
    lists = get_attio_lists(headers)
    if not lists:
        print("Error fetching lists")
        return None
        
    target_list = next((lst for lst in lists if lst.get('name', '').lower() == list_name.lower()), None)
    if not target_list:
        print(f"\nList '{list_name}' not found")
        return None
        
    return target_list['id']['list_id']

def get_list_stages_by_name(list_name, headers):
    """Get all stages for a list using list name."""
    list_id = get_list_id_by_name(list_name, headers)
    if not list_id:
        return None
        
    stages = get_list_stages(list_id, headers)
    if stages:
        print(f"\nStages in {list_name} list:")
        for stage_name, stage_id in stages.items():
            print(f"Stage: {stage_name}")
            print(f"ID: {stage_id}")
            print("-" * 30)
    
    return stages

# Usage example:
# layer_stages = get_list_stages_by_name("Layer", headers)

def get_company_notes(company_name, headers):
    """Get all notes associated with a company."""
    # First get company ID
    company_id = None
    
    # Get all companies and find matching one
    url = "https://api.attio.com/v2/objects/companies/records/query"
    try:
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        companies = response.json().get('data', [])
        
        # Find company by name (case insensitive)
        for company in companies:
            name = company.get('values', {}).get('name', [{}])[0].get('value', '')
            if name.lower() == company_name.lower():
                company_id = company['id']['record_id']
                break
        
        if not company_id:
            print(f"\nCompany '{company_name}' not found")
            return None
        
        # Get notes for this company
        notes_url = "https://api.attio.com/v2/notes"
        response = requests.get(notes_url, headers=headers)
        response.raise_for_status()
        all_notes = response.json().get('data', [])
        
        # Filter notes for this company
        company_notes = []
        for note in all_notes:
            if note.get('parent_object') == 'companies' and note.get('parent_record_id') == company_id:
                company_notes.append({
                    'title': note.get('title', 'Untitled'),
                    'content': note.get('content_plaintext', ''),
                    'created_at': note.get('created_at'),
                    'note_id': note['id']['note_id']
                })
        
        if company_notes:
            print(f"\nNotes for {company_name}:")
            print("-" * 50)
            for note in company_notes:
                print(f"Title: {note['title']}")
                print(f"Created: {note['created_at']}")
                print(f"Content:\n{note['content']}")
                print("-" * 50)
        else:
            print(f"\nNo notes found for {company_name}")
            
        return company_notes
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching notes: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print("Response:", e.response.text)
        return None

# Usage example:
notes = get_company_notes("Layer", headers)
