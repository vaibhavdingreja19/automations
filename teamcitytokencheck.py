import requests

TEAMCITY_URL = "http://your-teamcity-server-url"  # e.g., http://localhost:8111
PAT_TOKEN = "your_personal_access_token_here"

# Basic auth with PAT
headers = {
    "Authorization": f"Bearer {PAT_TOKEN}",
    "Accept": "application/json"
}

# Endpoints we want to test for permissions
endpoints = {
    "User Info": "/app/rest/users/current",
    "Projects": "/app/rest/projects",
    "Plugins": "/app/rest/server/plugins",
    "Build Types": "/app/rest/buildTypes",
    "Agents": "/app/rest/agents",
    "Server Info": "/app/rest/server",
}

def check_permissions():
    print("Checking PAT permissions...\n")
    for name, endpoint in endpoints.items():
        try:
            url = TEAMCITY_URL.rstrip("/") + endpoint
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                print(f"[✅] Access granted: {name}")
            elif response.status_code == 403:
                print(f"[❌] Access denied: {name} (403 Forbidden)")
            elif response.status_code == 401:
                print(f"[❌] Unauthorized: {name} (401 Unauthorized)")
            else:
                print(f"[⚠️] Unexpected response: {name} ({response.status_code})")
        except Exception as e:
            print(f"[❌] Error accessing {name}: {e}")

if __name__ == "__main__":
    check_permissions()
