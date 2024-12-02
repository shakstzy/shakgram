from telethon import TelegramClient, sync
from telethon.tl.types import InputPeerUser
from telethon.tl.functions.messages import CreateChatRequest, UpdateDialogFilterRequest
from telethon.tl.types import DialogFilter, InputPeerChannel, InputPeerUser, InputPeerChat
import os
import asyncio
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
import re  # Make sure to import the re module for regular expressions
import concurrent.futures
from datetime import datetime, timezone
import json
from docusign_esign import ApiClient, EnvelopesApi, EnvelopeDefinition
import base64
from docusign_esign.models.document import Document
from docusign_esign.models.signer import Signer
from docusign_esign.models.tabs import Tabs
from docusign_esign.models.sign_here import SignHere
from docusign_esign.models.recipients import Recipients
from docusign_esign.models.envelope_definition import EnvelopeDefinition
import time
import cv2
import numpy as np
from telethon.tl.types import InputFile
from io import BytesIO
from telethon import functions  # Add this import at the top
import random  # Add this import at the top

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

headers = {
    'Authorization': f'Bearer {attio_api_key}',
    'Content-Type': 'application/json'
}

async def send_message(telegram, message, folder=None):
    # Find the user by username
    user = await client.get_entity(telegram)
    print(f"First Name: {user.first_name}")
    print(f"Last Name: {user.last_name}")
    # Send the message
    await client.send_message(user, message)
# await send_message("@username", "Hello from the bot!")

async def has_face(photo):
    """Check if an image contains a face."""
    try:
        # Get image bytes
        image_data = await client.download_media(photo, bytes)
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Load face detection classifier
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        return len(faces) > 0
        
    except Exception as e:
        print(f"Error checking for faces: {str(e)}")
        return False

async def is_group_photo(photo):
    """Check if an image is likely a group photo (multiple faces)."""
    try:
        # Get image bytes
        image_data = await client.download_media(photo, bytes)
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Load face detection classifier
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        # Check if it's a group photo (2 or more faces)
        if len(faces) >= 2:
            # Calculate average face size
            face_areas = [w * h for (x, y, w, h) in faces]
            avg_face_area = sum(face_areas) / len(faces)
            image_area = img.shape[0] * img.shape[1]
            avg_face_ratio = avg_face_area / image_area
            
            # Faces should be:
            # 1. Not too small (each >2% of image)
            # 2. Not too large (each <40% of image)
            # 3. Similar sizes (within 50% of average)
            is_good_size = 0.02 < avg_face_ratio < 0.4
            similar_sizes = all(abs(area - avg_face_area) / avg_face_area < 0.5 for area in face_areas)
            
            return is_good_size and similar_sizes
            
        return False
        
    except Exception as e:
        print(f"Error checking for group photo: {str(e)}")
        return False

async def send_group_message(usernames, message, group_title="New Group"):
    """Create a group chat and send welcome message."""
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
                welcome_msg = await client.send_message(group_entity, message)
                print("Initial message sent successfully")
                break
        
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
# Example usage:
# async def main():
#     # Company name for the document title
#     company_name = "Layer"
#     # List of email addresses to share the document with
#     emails = ["user@example.com", "team@example.com"]
#     
#     try:
#         doc_link = await copy_google_doc_template(company_name, emails)
#         if doc_link:
#             print(f"Document created successfully!")
#             print(f"Access it here: {doc_link}")
#         else:
#             print("Failed to create document")
#     except Exception as e:
#         print(f"Error creating document: {str(e)}")
#
# # Run the async function
# client.loop.run_until_complete(main())


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
# Example usage:
# async def main():
#     # Document ID from Google Docs URL
#     document_id = "1234567890abcdef"  # Get this from the document URL
#     # Company name to replace [operator] with
#     company_name = "Layer Protocol"
#     # Signatory name to replace [Signatory] with
#     signatory_name = "John Smith"
#     
#     try:
#         await replace_text_in_document(document_id, company_name, signatory_name)
#         print("Successfully replaced text in document")
#     except Exception as e:
#         print(f"Error replacing text: {str(e)}")
#
# # Run the async function
# client.loop.run_until_complete(main())


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
# Example usage:
# async def main():
#     # Document ID from Google Docs URL
#     document_id = "1234567890abcdef"  # Get this from the document URL
#     # List of email addresses to share with
#     emails = [
#         "team@example.com",
#         "user@example.com"
#     ]
#     
#     try:
#         await share_document(document_id, emails)
#         print("Document shared successfully!")
#     except Exception as e:
#         print(f"Error sharing document: {str(e)}")
#
# # Run the async function
# client.loop.run_until_complete(main())


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
# Example usage:
# async def main():
#     # Document ID from Google Docs URL
#     document_id = "1234567890abcdef"  # Get this from the document URL
#     # Email address of the new owner
#     new_owner_email = "newowner@example.com"
#     
#     try:
#         await transfer_ownership(document_id, new_owner_email)
#         print(f"Successfully transferred ownership to {new_owner_email}")
#     except Exception as e:
#         print(f"Error transferring ownership: {str(e)}")
#
# # Run the async function
# client.loop.run_until_complete(main())


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
# Example usage:
# async def main():
#     # Document ID from Google Docs URL
#     document_id = "1234567890abcdef"  # Get this from the document URL
#     company_name = "Acme Corp"  # Company name to replace [operator]
#     signatory_name = "John Smith"  # Signatory name to replace [Signatory]
#     
#     try:
#         await copy_and_share_document(document_id, company_name, signatory_name)
#         print("Document copied, renamed, shared and updated successfully")
#     except Exception as e:
#         print(f"Error copying and sharing document: {str(e)}")
#
# # Run the async function
# client.loop.run_until_complete(main())


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
# Example usage:
# headers = {'Authorization': f'Bearer {attio_api_key}'}
# lists = get_attio_lists(headers)
# if lists:
#     list_id = choose_list(lists)
#     print(f"Selected list ID: {list_id}")


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
# Example usage:
# headers = {'Authorization': f'Bearer {attio_api_key}'}
# lists = get_attio_lists(headers)
# if lists:
#     list_id = choose_list(lists)
#     entries = get_list_entries_with_companies(list_id, headers)
#     if entries:
#         print(f"\nFound {len(entries)} entries")
#         for entry in entries:
#             company_id = entry.get('parent_record_id')
#             company_name = get_company_name(company_id, headers)
#             print(f"Company: {company_name}")


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
# entries = get_list_entries_with_companies(list_id, headers)


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
# company_name = get_company_name(company_id, headers)


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
# stages = get_list_stages(list_id, headers)


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
# # List ID from Attio
# list_id = "lst_01HQ7V4KXYT5GXDMJ5QWVZ8X9Y"
# # Entry ID to update
# entry_id = "ent_01HQ7V4KXYT5GXDMJ5QWVZ8X9Y"
# # New stage name (e.g., "Email Sent", "Meeting Scheduled", etc.)
# new_stage = "Email Sent"
# 
# result = update_entry_stage(list_id, entry_id, new_stage, headers)
# if result:
#     print(f"Successfully updated stage to: {new_stage}")
# else:
#     print("Failed to update stage")


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
                name_list = values.get('name', [])
                name = name_list[0].get('value', '') if name_list else ''
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
# async def main():
#     # Can use username or chat ID
#     chat_identifier = "@username"  # or numeric chat ID like "123456789"
#     
#     try:
#         message_info = await get_last_telegram_message(chat_identifier)
#         if message_info:
#             print("\nLast Message Info:")
#             print(f"Time: {message_info['timestamp']}")
#             print(f"Hours elapsed: {message_info['hours_elapsed']:.2f}")
#             print(f"Sender: {message_info['sender']}")
#             print(f"Message: {message_info['message']}")
#         else:
#             print("No messages found")
#     except Exception as e:
#         print(f"Error getting last message: {str(e)}")

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
# Example usage:
# companies = get_list_entries_by_stage(headers, "Layer", "Email Sent")


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
# Example usage:
# Get list ID for "Layer" list
# list_id = get_list_id_by_name("Layer", headers)
# if list_id:
#     print(f"Found list ID: {list_id}")


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
            name_list = company.get('values', {}).get('name', [])
            name = name_list[0].get('value', '') if name_list else ''
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
# Example usage:
# notes = get_company_notes("Company Name", headers)

def get_companies_by_list_status(list_name, status, headers):
    """Get all companies in a specified list with a specific status.
    
    Args:
        list_name: Name of the list (e.g., "Layer")
        status: Status to filter by (e.g., "Email Sent")
        headers: API headers
    
    Returns:
        list: List of companies with their details
    """
    # First get list ID
    list_id = get_list_id_by_name(list_name, headers)
    if not list_id:
        print(f"Could not find list: {list_name}")
        return None
    
    # Get all entries from the list
    entries = get_list_entries_with_companies(list_id, headers)
    if not entries:
        print(f"No entries found in list: {list_name}")
        return None
    
    # Filter entries by status
    matching_companies = []
    for entry in entries:
        entry_values = entry.get('entry_values', {})
        current_status = entry_values.get('stage', [{}])[0].get('status', {}).get('title', '')
        
        if current_status.lower() == status.lower():  # Case insensitive comparison
            company_id = entry.get('parent_record_id')
            company_name = get_company_name(company_id, headers)
            
            matching_companies.append({
                'company_id': company_id,
                'company_name': company_name,
                'entry_id': entry['id']['entry_id'],
                'list_name': list_name,
                'status': current_status
            })
    
    # Print results
    if matching_companies:
        print(f"\nFound {len(matching_companies)} companies in '{list_name}' with status '{status}':")
        print("-" * 50)
        for company in matching_companies:
            print(f"Company: {company['company_name']}")
            print(f"Company ID: {company['company_id']}")
            print(f"Entry ID: {company['entry_id']}")
            print("-" * 50)
    else:
        print(f"\nNo companies found in '{list_name}' with status '{status}'")
    
    return matching_companies
# Get all companies in the "Layer" list with status "Email Sent"
# companies = get_companies_by_list_status("Layer", "Email Sent", headers)
# if companies:
#     for company in companies:
#         print(f"Company: {company['company_name']}")
#         print(f"Status: {company['status']}")
#         print(f"Entry ID: {company['entry_id']}")


def get_company_id_by_name(company_name, headers):
    """Get company ID from company name (case insensitive).
    
    Args:
        company_name (str): Name of the company to look up
        headers (dict): API headers
        
    Returns:
        str: Company ID if found, None otherwise
    """
    try:
        # Use existing fetch_all_companies helper
        companies = fetch_all_companies(headers)
        if not companies:
            print("Error fetching companies")
            return None
        
        # Find matching company (case insensitive)
        for company in companies:
            name_list = company.get('values', {}).get('name', [])
            name = name_list[0].get('value', '') if name_list else ''
            if name.lower() == company_name.lower():
                company_id = company['id']['record_id']
                print(f"\nFound company: {name}")
                print(f"ID: {company_id}")
                return company_id
        
        print(f"\nCompany '{company_name}' not found")
        return None
        
    except Exception as e:
        print(f"Error getting company ID: {str(e)}")
        return None
# company_id = get_company_id_by_name("DxPool", headers)


def get_company_telegram_handles_by_id(company_id, headers):
    """Get telegram handles for a company using its ID."""
    try:
        # Get company record
        url = f"https://api.attio.com/v2/objects/companies/records/{company_id}"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        company_data = response.json().get('data', {})
        
        # Get company name from values
        name_values = company_data.get('values', {}).get('name', [])
        company_name = name_values[0].get('value', 'Unknown') if name_values else 'Unknown'
        
        print(f"\nLooking up Telegram handles for {company_name} (ID: {company_id})")
        
        # Get team members from company record
        team_values = company_data.get('values', {}).get('team', [])
        team_member_ids = [member.get('target_record_id') for member in team_values if member.get('target_record_id')]
        
        telegram_handles = []
        for member_id in team_member_ids:
            # Get person record
            person_url = f"https://api.attio.com/v2/objects/people/records/{member_id}"
            person_response = requests.get(person_url, headers=headers)
            person_response.raise_for_status()
            person_data = person_response.json().get('data', {})
            person_values = person_data.get('values', {})
            
            # Get name
            name_list = person_values.get('name', [])
            name = name_list[0].get('value', '') if name_list else 'Unknown'
            
            # Get telegram handle
            telegram_list = person_values.get('telegram', [])
            telegram = telegram_list[0].get('value', '').lstrip('@') if telegram_list else None
            
            # Get email addresses
            email_list = person_values.get('email_addresses', [])
            email_domain = email_list[0].get('email_domain', '') if email_list else ''
            
            if telegram:
                telegram_handles.append({
                    'name': name,
                    'handle': telegram,
                    'email_domain': email_domain
                })
        
        return telegram_handles
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching telegram handles: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print("Response:", e.response.text)
        return None


def get_entry_attribute_value(list_id, entry_id, attribute_title, headers):
    """Get a specific attribute value for a list entry using the attribute title."""
    try:
        # First get all attributes for the list to find the slug
        attributes_url = f"https://api.attio.com/v2/lists/{list_id}/attributes"
        attributes_response = requests.get(attributes_url, headers=headers)
        attributes_response.raise_for_status()
        
        # Find the attribute with matching title (case insensitive)
        attributes = attributes_response.json().get('data', [])
        target_attribute = next(
            (attr for attr in attributes if attr.get('title', '').lower() == attribute_title.lower()),
            None
        )
        
        if not target_attribute:
            print(f"Attribute '{attribute_title}' not found")
            return None
            
        attribute_slug = target_attribute.get('api_slug')
        
        if not attribute_slug:
            print(f"No API slug found for attribute '{attribute_title}'")
            return None
        
        # Get the attribute value using the correct endpoint
        url = f"https://api.attio.com/v2/lists/{list_id}/entries/{entry_id}/attributes/{attribute_slug}/values"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # Get the value from the response
        values = response.json().get('data', [])
        
        if values:
            # Get the most recent value
            latest_value = values[0]
            return latest_value.get('value')
            
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"Error getting attribute value: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print("Response:", e.response.text)
        return None


async def create_mous():
    """Create MoUs for companies in Layer list with 'Email Sent' status."""
    try:
        # Get companies from Layer list with Email Sent status
        companies = get_companies_by_list_status("Layer", "Email Sent", headers)
        
        if not companies:
            print("No companies found with 'Email Sent' status")
            return
            
        print("\nProcessing companies for MoU creation:")
        print("-" * 70)
        
        for company in companies:
            print(f"\nProcessing {company['company_name']}:")
            
            # Check if document already exists
            existing_docs = drive_service.files().list(
                q=f"mimeType='application/vnd.google-apps.document' and name contains '{company['company_name']}'",
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            if existing_docs.get('files'):
                print(f"Document already exists for {company['company_name']}")
                print("Updating status to 'Docusign Created'...")
                
                # Update status using the correct list_id and entry_id
                list_id = get_list_id_by_name("Layer", headers)  # Get list ID
                result = update_entry_stage(
                    list_id,
                    company['entry_id'],
                    "Docusign Created",
                    headers
                )
                
                if result:
                    print("Status updated successfully!")
                    for doc in existing_docs.get('files', []):
                        print(f"Document: {doc['name']}")
                        print(f"Link: https://docs.google.com/document/d/{doc['id']}/edit")
                else:
                    print("Failed to update status")
                continue
            
            # Get spokesperson name
            list_id = get_list_id_by_name("Layer", headers)  # Get list ID
            spokesperson = get_entry_attribute_value(
                list_id,
                company['entry_id'],
                "Spokesperson Name",
                headers
            )
            
            if spokesperson:
                print(f"Spokesperson: {spokesperson}")
                
                try:
                    # Create MoU
                    doc_link = await copy_and_share_document(
                        "1iwZ3i6sD8bWwTml2WWdeWBL0y6Q1tiRNP03qhS1UL2s",  # Template ID
                        company['company_name'],
                        spokesperson
                    )
                    
                    if doc_link:
                        print("MoU created successfully!")
                        print(f"Document link: {doc_link}")
                        
                        # Update status to Docusign Created
                        result = update_entry_stage(
                            list_id,
                            company['entry_id'],
                            "Docusign Created",
                            headers
                        )
                        
                        if result:
                            print("Status updated successfully!")
                        else:
                            print("Failed to update status")
                    
                except Exception as e:
                    print(f"Error creating MoU: {str(e)}")
            else:
                print(f"Skipping {company['company_name']} - No spokesperson name found")
            
            print("-" * 70)
            
    except Exception as e:
        print(f"Error in create_mous: {str(e)}")
        print("Company data:", company if 'company' in locals() else "Not available")

# Run the async function
# client.loop.run_until_complete(create_mous())


def connect_to_docusign():
    """Connect to DocuSign API using JWT Grant authentication."""
    try:
        # Load DocuSign credentials from config file
        with open('docusign.json') as f:
            ds_config = json.load(f)
        
        # Initialize API client
        api_client = ApiClient()
        api_client.set_base_path(ds_config['base_path'])
        api_client.set_oauth_host_name(ds_config['auth_server'])
        
        try:
            # Get JWT token
            token = api_client.request_jwt_user_token(
                client_id=ds_config['client_id'],
                user_id=ds_config['impersonated_user_id'],
                oauth_host_name=ds_config['auth_server'],
                private_key_bytes=ds_config['private_key'].encode('utf-8'),
                expires_in=3600,
                scopes=["signature", "impersonation"]
            )
            
            # Get user info and account details
            user_info = api_client.get_user_info(token.access_token)
            accounts = user_info.get_accounts()
            account = accounts[0]  # Get first account
            
            # Update base path with account-specific endpoint
            base_path = f"{account.base_uri}/restapi"
            api_client.host = base_path
            
            # Set authorization header
            api_client.set_default_header(
                header_name="Authorization",
                header_value=f"Bearer {token.access_token}"
            )
            
            # Create envelope API instance
            envelope_api = EnvelopesApi(api_client)
            
            print("Successfully connected to DocuSign API")
            print(f"Account ID: {account.account_id}")
            print(f"Base Path: {base_path}")
            
            return api_client, envelope_api
            
        except Exception as e:
            if 'consent_required' in str(e):
                consent_url = (
                    f"https://{ds_config['auth_server']}/oauth/auth"
                    f"?response_type=code"
                    f"&scope=signature%20impersonation"
                    f"&client_id={ds_config['client_id']}"
                    f"&redirect_uri=https://developers.docusign.com/platform/auth/consent"
                )
                print("\nConsent required. Please visit this URL to grant consent:")
                print(consent_url)
            print(f"JWT authentication error: {str(e)}")
            return None, None
            
    except Exception as e:
        print(f"Error connecting to DocuSign: {str(e)}")
        return None, None



def send_document_for_signature(envelope_api, account_id, signer_email, signer_name, doc_path, doc_name=None):
    """Send a document for signature via DocuSign."""
    try:
        # Read the PDF file
        with open(doc_path, 'rb') as file:
            doc_bytes = file.read()
        
        # Create document object
        document = Document(
            document_base64=base64.b64encode(doc_bytes).decode('utf-8'),
            name=doc_name or 'Operator Memorandum of Understanding',  # Use doc_name if provided
            file_extension='pdf',
            document_id='1'
        )
        
        # Create signer object with anchor tab
        sign_here = SignHere(
            anchor_string='[Signatory]',
            anchor_units='pixels',
            anchor_y_offset='10',
            anchor_x_offset='20',
            tab_label='SignHereTab'
        )
        
        # Create tabs object
        tabs = Tabs(sign_here_tabs=[sign_here])
        
        # Create signer with tabs
        signer = Signer(
            email=signer_email,
            name=signer_name,
            recipient_id='1',
            routing_order='1',
            tabs=tabs
        )
        
        # Create recipients object
        recipients = Recipients(signers=[signer])
        
        # Create envelope definition
        envelope_definition = EnvelopeDefinition(
            email_subject='Please sign the Layer Operator Memorandum of Understanding',
            email_blurb='Please review and sign this document at your earliest convenience.',
            documents=[document],
            recipients=recipients,
            status='sent'
        )
        
        try:
            envelope_summary = envelope_api.create_envelope(
                account_id=account_id,
                envelope_definition=envelope_definition
            )
            
            print(f"\nDocument sent successfully!")
            print(f"Envelope ID: {envelope_summary.envelope_id}")
            return envelope_summary.envelope_id
            
        except ApiException as e:
            print(f"\nError creating envelope: {e}")
            print(f"Response body: {e.body}")
            return None
            
    except Exception as e:
        print(f"Error preparing document: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print("Response:", e.response.text)
        return None


def test_docusign_integration():
    """Run 20 successful test calls to DocuSign."""
    api_client, envelope_api = connect_to_docusign()
    
    if api_client and envelope_api:
        try:
            # Get account ID
            user_info = api_client.get_user_info(api_client.default_headers['Authorization'].split(' ')[1])
            account_id = user_info.get_accounts()[0].account_id
            
            print("\nRunning 20 test calls...")
            successful_calls = 0
            
            for i in range(20):
                try:
                    # Create unique document name for each test
                    doc_name = f"Test Document {i+1} - {datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    # Send test document
                    envelope_id = send_document_for_signature(
                        envelope_api=envelope_api,
                        account_id=account_id,
                        signer_email="adithya@lay3rlabs.io",
                        signer_name="Adithya Kumar",
                        doc_path="Operator Memorandum of Understanding - SenseiNode.pdf",
                        doc_name=doc_name  # Pass unique name
                    )
                    
                    if envelope_id:
                        successful_calls += 1
                        print(f"\nTest {i+1}/20 successful!")
                        print(f"Document: {doc_name}")
                        print(f"Envelope ID: {envelope_id}")
                    else:
                        print(f"\nTest {i+1}/20 failed")
                    
                    # Add delay between calls
                    time.sleep(2)  # Wait 2 seconds between calls
                        
                except Exception as e:
                    print(f"\nError in test {i+1}: {str(e)}")
                    
            print(f"\nCompleted {successful_calls}/20 successful calls")
            return successful_calls == 20
            
        except Exception as e:
            print(f"Error in test setup: {str(e)}")
            return False
    
    return False

# Run the tests
# success = test_docusign_integration()
# if success:
#     print("\nAll test calls successful! Ready for go-live.")
# else:
#     print("\nSome tests failed. Please review errors before go-live.")

async def check_existing_group_chat(company1_name, company2_name):
    """Check if a group chat already exists between two companies."""
    try:
        # Check both naming patterns
        pattern1 = f"{company1_name} <> {company2_name}"
        pattern2 = f"{company2_name} <> {company1_name}"
        
        print(f"\nChecking for existing group chats:")
        print(f"Pattern 1: {pattern1}")
        print(f"Pattern 2: {pattern2}")
        
        # Get all dialogs and filter for groups
        async for dialog in client.iter_dialogs():
            if dialog.is_group:
                if dialog.title == pattern1 or dialog.title == pattern2:
                    print(f"\nFound existing group: {dialog.title}")
                    return True, dialog.entity, dialog.title
        
        print("\nNo existing group chat found")
        return False, None, None
        
    except Exception as e:
        print(f"Error checking for existing group chat: {str(e)}")
        return False, None, None

async def create_company_group_chat(company1, company2, intro_message=None, is_id=False, headers=None):
    """Create a group chat between two companies' telegram users.
    
    Args:
        company1: First company name or ID
        company2: Second company name or ID
        intro_message: Custom introduction message (optional)
        is_id: Whether inputs are IDs (True) or names (False)
        headers: API headers for Attio
    """
    try:
        # Get company names (if IDs provided) or use names directly
        company1_name = get_company_name(company1, headers) if is_id else company1
        company2_name = get_company_name(company2, headers) if is_id else company2
        
        # Check for existing group chat first
        exists, existing_chat, pattern = await check_existing_group_chat(company1_name, company2_name)
        if exists:
            print(f"\nGroup chat already exists: {pattern}")
            print("Please use the existing group")
            return False
            
        # Only look up company IDs if we need to create a new group
        company1_id = company1 if is_id else get_company_id_by_name(company1, headers)
        company2_id = company2 if is_id else get_company_id_by_name(company2, headers)
        
        if not company1_id or not company2_id:
            print("Could not find one or both companies")
            return False
            
        # Get telegram handles for both companies
        handles1 = get_company_telegram_handles_by_id(company1_id, headers)
        handles2 = get_company_telegram_handles_by_id(company2_id, headers)
        
        if not handles1 and not handles2:
            print("No telegram handles found for either company")
            return False
            
        # Combine all telegram handles
        all_handles = []
        
        print(f"\nTelegram handles for {company1_name}:")
        for handle in handles1 or []:
            print(f"@{handle['handle']} ({handle['name']})")
            all_handles.append(f"@{handle['handle']}")
            
        print(f"\nTelegram handles for {company2_name}:")
        for handle in handles2 or []:
            print(f"@{handle['handle']} ({handle['name']})")
            all_handles.append(f"@{handle['handle']}")
            
        if not all_handles:
            print("No telegram handles to add to group")
            return False
            
        # Create group with new naming pattern
        group_name = f"{company1_name} <> {company2_name}"
        welcome_message = intro_message or f"Welcome to the group chat for {company1_name} and {company2_name}! 👋"
        
        print(f"\nCreating group chat: {group_name}")
        await send_group_message(all_handles, welcome_message, group_name)
        return True
        
    except Exception as e:
        print(f"Error creating group chat: {str(e)}")
        return False


# # Example usage:
# api_client, envelope_api = connect_to_docusign()
# if api_client and envelope_api:
#     print("Ready to create and send envelopes")

# # Send the SenseiNode MoU
# if api_client and envelope_api:
#     try:
#         # Get account ID from user info
#         user_info = api_client.get_user_info(api_client.default_headers['Authorization'].split(' ')[1])
#         account_id = user_info.get_accounts()[0].account_id
        
#         # Send document
#         envelope_id = send_document_for_signature(
#             envelope_api=envelope_api,
#             account_id=account_id,
#             signer_email="adithya@outerscope.xyz",
#             signer_name="Adithya Kumar",
#             doc_path="Operator Memorandum of Understanding - SenseiNode.pdf"
#         )
        
#         if envelope_id:
#             print("MoU sent for signature successfully!")
            
#     except Exception as e:
#         print(f"Error sending document: {str(e)}")

async def get_telegram_folders():
    """Helper function to get all Telegram folders."""
    try:
        result = await client(functions.messages.GetDialogFiltersRequest())
        folders = []
        
        for folder in result.filters:
            if isinstance(folder, DialogFilter):
                folders.append({
                    'title': folder.title,
                    'id': folder.id,
                    'filter': folder
                })
        return folders
    except Exception as e:
        print(f"Error getting folders: {str(e)}")
        return None

async def add_chat_to_folder(chat_identifier, folder_name):
    """Add a chat (group or individual) to a Telegram folder."""
    try:
        # Get the chat entity
        chat = await client.get_entity(chat_identifier)
        
        # Convert chat to InputPeer
        if hasattr(chat, 'channel_id'):
            input_peer = InputPeerChannel(chat.id, chat.access_hash)
            chat_title = chat.title
        elif hasattr(chat, 'chat_id'):
            input_peer = InputPeerChat(chat.id)
            chat_title = chat.title
        else:
            input_peer = InputPeerUser(chat.id, chat.access_hash)
            # For users, combine first and last name
            chat_title = f"{getattr(chat, 'first_name', '')} {getattr(chat, 'last_name', '')}".strip()

        # Get all folders
        folders = await get_telegram_folders()
        if not folders:
            print("No folders found")
            return False

        # Find the target folder
        target_folder = next((f for f in folders if f['title'].lower() == folder_name.lower()), None)
        if not target_folder:
            print(f"Folder '{folder_name}' not found")
            return False

        print(f"\nFound folder: {target_folder['title']} (ID: {target_folder['id']})")
        print(f"Adding chat: {chat_title}")
        
        # Get current folder settings and add the new chat
        current_filter = target_folder['filter']
        include_peers = list(current_filter.include_peers)
        
        # Add the new peer if it's not already in the list
        if input_peer not in include_peers:
            include_peers.append(input_peer)
        
        # Create updated filter
        updated_filter = DialogFilter(
            id=current_filter.id,
            title=current_filter.title,
            pinned_peers=current_filter.pinned_peers,
            include_peers=include_peers,
            exclude_peers=current_filter.exclude_peers
        )
        
        # Update the folder
        await client(UpdateDialogFilterRequest(
            id=updated_filter.id,
            filter=updated_filter
        ))
        
        print(f"Successfully added {chat_title} to folder {folder_name}")
        return True
        
    except Exception as e:
        print(f"Error adding chat to folder: {str(e)}")
        return False

async def remove_from_folder(chat_identifier, folder_name):
    """Remove a chat (group or individual) from a Telegram folder."""
    try:
        # Get the chat entity
        chat = await client.get_entity(chat_identifier)
        
        # Convert chat to InputPeer
        if hasattr(chat, 'channel_id'):
            input_peer = InputPeerChannel(chat.id, chat.access_hash)
            chat_title = chat.title
        elif hasattr(chat, 'chat_id'):
            input_peer = InputPeerChat(chat.id)
            chat_title = chat.title
        else:
            input_peer = InputPeerUser(chat.id, chat.access_hash)
            chat_title = f"{getattr(chat, 'first_name', '')} {getattr(chat, 'last_name', '')}".strip()

        # Get all folders
        folders = await get_telegram_folders()
        if not folders:
            print("No folders found")
            return False

        # Find the target folder
        target_folder = next((f for f in folders if f['title'].lower() == folder_name.lower()), None)
        if not target_folder:
            print(f"Folder '{folder_name}' not found")
            return False

        print(f"\nFound folder: {target_folder['title']} (ID: {target_folder['id']})")
        print(f"Removing chat: {chat_title}")
        
        # Get current folder settings and remove the chat
        current_filter = target_folder['filter']
        include_peers = list(current_filter.include_peers)
        
        # Remove the peer if it's in the list
        if input_peer in include_peers:
            include_peers.remove(input_peer)
            
            # Create updated filter
            updated_filter = DialogFilter(
                id=current_filter.id,
                title=current_filter.title,
                pinned_peers=current_filter.pinned_peers,
                include_peers=include_peers,
                exclude_peers=current_filter.exclude_peers
            )
            
            # Update the folder
            await client(UpdateDialogFilterRequest(
                id=updated_filter.id,
                filter=updated_filter
            ))
            
            print(f"Successfully removed {chat_title} from folder {folder_name}")
            return True
        else:
            print(f"Chat {chat_title} was not found in folder {folder_name}")
            return False
        
    except Exception as e:
        print(f"Error removing chat from folder: {str(e)}")
        return False

# add_chat_to_folder("NodeOps <> Layer", "Layer")

async def main():
    # Get all companies with gaming tag
    gaming_companies = fetch_all_companies(headers, filter_tag="Gaming")
    
    if gaming_companies:
        # Custom intro message
        intro = """Hey everyone! 👋

This is a group chat for gaming companies to discuss integration with Octane. We'll be discussing:
• Technical requirements
• Integration timeline
• Support and resources

Let's get started! 🎮"""
        
        # Create group chats between Octane and each gaming company
        for company in gaming_companies:
            success = await create_company_group_chat(
                "Octane",
                company['name'],
                intro_message=intro,
                headers=headers
            )
            if success:
                print(f"Created group chat with {company['name']}")
            else:
                print(f"Failed to create group chat with {company['name']}")
            
            # Random delay between 5-10 seconds
            delay = random.uniform(5, 10)
            await asyncio.sleep(delay)

# Run the async function
client.loop.run_until_complete(main())