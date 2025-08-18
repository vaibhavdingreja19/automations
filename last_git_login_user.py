import requests
import datetime

# -------- CONFIG --------
ORG = "JHDevOps"  # Your GitHub org
USERNAME = "hardcoded-username"  # Replace with the username you want to check
TOKEN = "ghp_yourPATtokenHere"   # Replace with your PAT token
# ------------------------

headers = {"Authorization": f"token {TOKEN}"}

def get_last_login(org, username):
    url = f"https://api.github.com/orgs/{org}/audit-log"
    params = {
        "phrase": f"actor:{username} action:login",  # filter login events
        "per_page": 1,
        "order": "desc"  # newest first
    }

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"Error: {response.status_code} {response.text}")
        return None

    events = response.json()
    if not events:
        print(f"No login events found for user {username}")
        return None

    last_event = events[0]
    timestamp = last_event.get("@timestamp")
    if timestamp:
        dt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt
    else:
        return None

if __name__ == "__main__":
    last_login = get_last_login(ORG, USERNAME)
    if last_login:
        print(f"Last login time for {USERNAME}: {last_login}")
    else:
        print(f"Could not retrieve last login for {USERNAME}")
