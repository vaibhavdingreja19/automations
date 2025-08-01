import requests
import datetime
import pandas as pd

# ------------- CONFIG -------------
GITHUB_TOKEN = "ghp_yourPATtoken"  # 🔐 Replace with your PAT token
ORG = "JHDevOps"
DAYS_INACTIVE = 365
OUTPUT_FILE = "inactive_members.xlsx"
# ----------------------------------

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

def get_org_members(org):
    members = []
    page = 1
    while True:
        url = f"https://api.github.com/orgs/{org}/members?per_page=100&page={page}"
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            print(f"Error fetching members: {resp.text}")
            break
        data = resp.json()
        if not data:
            break
        members.extend(data)
        page += 1
    return members

def get_last_public_activity(username):
    url = f"https://api.github.com/users/{username}/events/public"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return None
    events = resp.json()
    if events:
        return events[0]['created_at']
    return None

def main():
    print(f"🔍 Checking inactive members of {ORG}...")
    members = get_org_members(ORG)
    cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=DAYS_INACTIVE)

    inactive = []
    for member in members:
        username = member['login']
        print(f"Checking activity for: {username}")
        last_activity = get_last_public_activity(username)

        if last_activity:
            last_date = datetime.datetime.strptime(last_activity, "%Y-%m-%dT%H:%M:%SZ")
            if last_date < cutoff_date:
                inactive.append({"username": username, "last_activity": last_date})
        else:
            inactive.append({"username": username, "last_activity": "No public activity"})

    df = pd.DataFrame(inactive)
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"\n✅ Done. Inactive members saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
