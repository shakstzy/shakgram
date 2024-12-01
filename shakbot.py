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

def fetch_companies_by_tag(tag_name, headers):
    """Fetch companies that have the specified tag as one of their tags."""
    url = "https://api.attio.com/v2/objects/companies/records/query"
    
    payload = {
        "filter": {
            "project_tag_5": {
                "$elemMatch": {
                    "option.title": tag_name
                }
            }
        },
        "include_values": ["name", "project_tag_5"]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        companies = response.json().get('data', [])
        
        print(f"\nFound {len(companies)} companies with tag '{tag_name}':")
        for company in companies:
            name = 'Unknown'
            name_values = company.get('values', {}).get('name', [])
            if name_values and len(name_values) > 0:
                name = name_values[0].get('value', 'Unknown')
            
            tags = [tag['option']['title'] for tag in company.get('values', {}).get('project_tag_5', [])]
            
            print(f"\nCompany: {name}")
            print(f"ID: {company['id']['record_id']}")
            print(f"Tags: {', '.join(tags)}")
            print("-" * 30)
        
        return companies
        
    except requests.exceptions.RequestException as e:
        print(f"Error: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print("Response:", e.response.text)
        return None

def fetch_all_companies(headers):
    """Fetch all companies using proper pagination."""
    url = "https://api.attio.com/v2/objects/companies/records/query"
    
    all_companies = []
    offset = 0  # Start from 500
    limit = 500  # Maximum limit per request
    
    try:
        while True:
            payload = {
                "include_values": ["name"],
                "limit": limit,
                "offset": offset
            }
            
            try:
                response = requests.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                
                companies_batch = data.get('data', [])
                batch_size = len(companies_batch)
                
                if batch_size == 0:  # No more results
                    print(f"\nNo more companies found at offset {offset}")
                    break
                
                all_companies.extend(companies_batch)
                print(f"\nFetched batch of {batch_size} companies (total fetched: {len(all_companies)})")
                
                # Print companies from this batch
                for company in companies_batch:
                    values = company.get('values', {})
                    name_list = values.get('name', [])
                    name = name_list[0].get('value', 'Unknown') if name_list else 'Unknown'
                    print(f"- {name}")
                
                if batch_size < limit:  # Last page
                    print("\nReached last page of results")
                    break
                
                offset += batch_size  # Increment offset by actual batch size
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 400:  # Offset too large
                    print(f"\nReached end of results (offset {offset} too large)")
                    break
                raise  # Re-raise other HTTP errors
        
        print(f"\nTotal companies fetched after offset 500: {len(all_companies)}")
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
list_id = "00f50bb3-70d6-40f2-9165-712acdc33c24"
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
# companies = fetch_companies_by_tag("Tooling", headers)
fetch_all_companies(headers)

client.disconnect()