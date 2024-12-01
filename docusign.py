import requests
import json
import base64

def create_docusign_envelope(access_token, account_id, pdf_file_path, recipient_email, recipient_name):
    """Create a DocuSign envelope from a specified PDF file."""
    url = f"https://demo.docusign.net/restapi/v2.1/accounts/{account_id}/envelopes"
    
    # Prepare the envelope definition
    envelope_definition = {
        "emailSubject": "Please sign this document",
        "documents": [
            {
                "documentBase64": "",
                "name": "Document",
                "fileExtension": "pdf",
                "documentId": "1"
            }
        ],
        "recipients": {
            "signers": [
                {
                    "email": recipient_email,
                    "name": recipient_name,
                    "recipientId": "1",
                    "routingOrder": "1",
                    "tabs": {
                        "signHereTabs": [
                            {
                                "anchorString": "/sn1/",
                                "anchorYOffset": "10",
                                "anchorUnits": "pixels",
                                "anchorXOffset": "20"
                            }
                        ]
                    }
                }
            ]
        },
        "status": "sent"  # Set to "sent" to send immediately, "created" to save as a draft
    }

    # Read the PDF file and encode it in base64
    with open(pdf_file_path, "rb") as pdf_file:
        pdf_content = pdf_file.read()
        envelope_definition["documents"][0]["documentBase64"] = base64.b64encode(pdf_content).decode('utf-8')

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Send the request to create the envelope
    response = requests.post(url, headers=headers, data=json.dumps(envelope_definition))

    if response.status_code == 201:
        print("Envelope created successfully!")
        print("Envelope ID:", response.json().get("envelopeId"))
    else:
        print("Error creating envelope:", response.status_code, response.text)

# Example usage
if __name__ == "__main__":
    ACCESS_TOKEN = "0990a5d3-4d50-46f5-a60d-33daa6c9ad73"  # Replace with your access token
    ACCOUNT_ID = "0a043e0d-f9fa-4b20-aa42-f0c46d4029af"  # Replace with your account ID
    PDF_FILE_PATH = "test.pdf"  # Replace with the path to your PDF file
    RECIPIENT_EMAIL = "adithya@outerscope.xyz"  # Replace with the recipient's email
    RECIPIENT_NAME = "Adithya"  # Replace with the recipient's name

    create_docusign_envelope(ACCESS_TOKEN, ACCOUNT_ID, PDF_FILE_PATH, RECIPIENT_EMAIL, RECIPIENT_NAME)