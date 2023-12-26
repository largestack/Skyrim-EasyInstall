import websockets
import asyncio
import json
import uuid
import webbrowser
import requests

# Replace 'your_application_slug' with the actual application slug provided by Nexus Mods
application_slug = 'your_application_slug'

async def get_api_key():
    async with websockets.connect("wss://sso.nexusmods.com") as websocket:
        # Retrieve or generate uuid and token
        # This should be replaced with actual sessionStorage retrieval in a browser context
        uuid_val = str(uuid.uuid4())
        token = None

        # Send the request to the SSO server
        data = {
            "id": uuid_val,
            "token": token,
            "protocol": 2
        }
        await websocket.send(json.dumps(data))

        # Wait for response from the SSO server
        response = await websocket.recv()
        response_data = json.loads(response)

        # Open the browser for user authorization
        auth_url = f"https://www.nexusmods.com/sso?id={uuid_val}&application={application_slug}"
        webbrowser.open(auth_url)

        # Wait for the API key
        api_key_response = await websocket.recv()
        api_key_data = json.loads(api_key_response)
        return api_key_data.get('data', {}).get('api_key')

def get_mod_download_link(api_key, game_domain_name, mod_id, file_id):
    url = f"https://api.nexusmods.com/v1/games/{game_domain_name}/mods/{mod_id}/files/{file_id}/download_link.json"
    headers = {'apikey': api_key}
    response = requests.get(url, headers=headers)
    return response.json()

async def main():
    api_key = await get_api_key()
    if api_key:
        # Replace these with the actual game_domain_name, mod_id, and file_id
        game_domain_name = 'skyrim'
        mod_id = '12345'
        file_id = '67890'
        download_link = get_mod_download_link(api_key, game_domain_name, mod_id, file_id)
        print(download_link)
    else:
        print("Failed to retrieve API key")

asyncio.run(main())
