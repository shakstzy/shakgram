import requests

url = "https://api.attio.com/v2/objects/companies/records/query"

payload = { "filter": { "name": "Outerscope" } }
headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "authorization": "Bearer f81879061c848ca2c3a66a9c4d67c467a68a42b49f311c97b3bcdcb93a5da2cc"
}

response = requests.post(url, json=payload, headers=headers)

print(response.text)