import requests
import json
import os
from dotenv import load_dotenv

def get_telegram_handles(data, domain):
    telegrams = []
    for record in data.get('data', []):
        values = record.get('values', {})
        
        # Check email domains
        email_addresses = values.get('email_addresses', [])
        for email in email_addresses:
            if email.get('email_domain') == domain:
                # Get telegram if email domain matches
                telegram_entries = values.get('telegram', [])
                if telegram_entries:
                    telegram = telegram_entries[0].get('value')
                    if telegram:
                        telegrams.append(telegram)
                break
    return telegrams

# Load environment variables
load_dotenv()

# Get bearer token from env
ATTIO_API_KEY = os.getenv('ATTIO_API_KEY')
if not ATTIO_API_KEY:
    raise ValueError("ATTIO_API_KEY not found in environment variables")

# Get company name from user input
company_name = input("Enter company name: ").strip().lower()
domain = f"{company_name}.com"

print(f"\nLooking for email addresses with domain: {domain}")

url = "https://api.attio.com/v2/objects/people/records/query"
headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "authorization": f"Bearer {ATTIO_API_KEY}"
}

response = requests.post(url, headers=headers)
data = response.json()

# Get telegrams for the specified domain
telegrams = get_telegram_handles(data, domain)

# Print results
if telegrams:
    print(f"\nTelegram handles for {domain} employees:")
    for telegram in telegrams:
        print(f"@{telegram}")
else:
    print(f"\nNo individuals found with {domain} email domains")