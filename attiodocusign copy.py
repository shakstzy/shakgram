import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get bearer token from env
ATTIO_API_KEY = os.getenv('ATTIO_API_KEY')
if not ATTIO_API_KEY:
    raise ValueError("ATTIO_API_KEY not found in environment variables")

headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "authorization": f"Bearer {ATTIO_API_KEY}"
}

def get_list_entries(headers, list_id):
    """Fetch entries from a specific Attio list"""
    url = f"https://api.attio.com/v2/lists/{list_id}/entries/query"
    response = requests.post(url, headers=headers)
    if response.status_code == 200:
        print("\nSuccessfully retrieved list entries")
        return response.json()
    else:
        print(f"Error fetching list entries: {response.status_code}")
        print(f"Response: {response.text}")
        return None

def get_attio_lists(headers):
    """Fetch all lists from Attio"""
    url = "https://api.attio.com/v2/lists"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        lists = response.json().get('data', [])
        print("\nAvailable Attio lists:")
        for idx, lst in enumerate(lists, 1):
            list_id = lst['id']['list_id']
            print(f"{idx}. {lst.get('name', 'Unnamed')} (List ID: {list_id})")
        
        while True:
            try:
                choice = int(input("\nEnter the number of the list you want to work with: "))
                if 1 <= choice <= len(lists):
                    selected_list = lists[choice - 1]
                    selected_list_id = selected_list['id']['list_id']
                    print(f"\nSelected: {selected_list['name']}")
                    print(f"List ID: {selected_list_id}")
                    
                    # Get entries for the selected list
                    list_entries = get_list_entries(headers, selected_list_id)
                    
                    # Print entry IDs for the selected list
                    if list_entries:
                        print("Entry IDs for the selected list:")
                        for entry in list_entries.get('data', []):
                            entry_id = entry['id']
                            print(f"- Entry ID: {entry_id} (Title: {entry.get('title', 'No Title')})")
                    
                    return list_entries
                else:
                    print("Invalid selection. Please choose a number from the list.")
            except ValueError:
                print("Please enter a valid number.")
    else:
        print(f"Error fetching lists: {response.status_code}")
        return None

def get_company_name(company_id, headers):
    """Fetch the company name using the company ID"""
    url = f"https://api.attio.com/v2/objects/companies/records/{company_id}"
    print(f"Requesting company data for ID: {company_id}")  # Debugging line
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        company_data = response.json()
        # Extract the company name from the response
        name_values = company_data.get('data', {}).get('values', {}).get('name', [])
        if name_values:
            return name_values[0].get('value', 'Company name not found')
        else:
            return 'Company name not found'
    else:
        print(f"Error fetching company record for ID {company_id}: {response.status_code} - {response.text}")
        return 'Error fetching company name'

def display_prospecting_entries(entries, headers):
    """Filter and display entries in Prospecting stage with company names"""
    matching_entries = []
    
    for entry in entries.get('data', []):
        # Get the current status
        stage_values = entry.get('entry_values', {}).get('stage', [])
        if stage_values:
            current_status = stage_values[0].get('status', {}).get('title')
            if current_status == "Email Sent":
                matching_entries.append(entry)
    
    if matching_entries:
        print(f"\nFound {len(matching_entries)} entries in Prospecting stage:")
        for entry in matching_entries:
            # Use parent_record_id to get the company ID
            company_id = entry.get('parent_record_id', 'Company ID not specified')
            print(f"Using Company ID: {company_id}")  # Debugging line
            
            # Fetch the company name using the company ID
            company_name = get_company_name(company_id, headers)
            
            print(f"Company ID: {company_id}")  # Display the company ID
            print(f"Company Name: {company_name}")
            print(f"Created at: {entry['created_at']}")
            
            # Show layer_tag if exists
            layer_tags = entry.get('entry_values', {}).get('layer_tag', [])
            if layer_tags:
                tags = [tag.get('option', {}).get('title') for tag in layer_tags]
                print(f"Layer tags: {', '.join(tags)}")
            
            # Show email_sent values
            email_sent = entry.get('entry_values', {}).get('email_sent', [])
            if email_sent:
                email_values = [email.get('value', 'No value') for email in email_sent]
                print(f"Email sent: {', '.join(email_values)}")
            else:
                print(f"Email sent: No values")
            
            # Show spokesperson name
            spokesperson = entry.get('entry_values', {}).get('spokesperson_name', [])
            if spokesperson:
                print(f"Spokesperson: {spokesperson[0].get('value', 'Not specified')}")
            else:
                print(f"Spokesperson: Not specified")
                
            print("---")
            
            # Update the status to "Docusign Created"
            update_entry_status(entry['id'], headers, "Docusign Created")
    else:
        print("\nNo entries found in Prospecting stage")

# First, get all available lists
list_entries = get_attio_lists(headers)
if list_entries:
    print("\nList Entries:")
    print(json.dumps(list_entries, indent=2))
    display_prospecting_entries(list_entries, headers)