from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.oauth2 import service_account

def copy_mou_template():
    # If using service account, load credentials (recommended for automation)
    SCOPES = ['https://www.googleapis.com/auth/drive']
    credentials = service_account.Credentials.from_service_account_file(
        'docusign.json',  # Replace with your service account file path
        scopes=SCOPES
    )

    # Build the Drive API service
    service = build('drive', 'v3', credentials=credentials)

    try:
        # Search for the template file with more detailed query and logging
        query = "name contains 'Operator Memorandum of Understanding Template'"
        print(f"Searching for files with query: {query}")
        
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        files = results.get('files', [])
        
        # Add debug information
        print(f"Found {len(files)} matching files:")
        for file in files:
            print(f"- {file['name']} (ID: {file['id']}")
        
        if not files:
            print("Template file not found. Please check:")
            print("1. The exact file name in your Google Drive")
            print("2. The service account has access to the file")
            return
            
        template_id = files[0]['id']
        
        # Create a copy with the new name
        file_metadata = {
            'name': 'Operator Memorandum of Understanding Template - WORKING COPY',
            'parents': ['1HkKLhAkDpfC3DQZQMLiriNKwrwubmwcg']  # Replace with your MOU templates folder ID
        }
        
        # Copy the file
        copied_file = service.files().copy(
            fileId=template_id,
            body=file_metadata
        ).execute()
        
        print(f"Created working copy with ID: {copied_file['id']}")
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    copy_mou_template()