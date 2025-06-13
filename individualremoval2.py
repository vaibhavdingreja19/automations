import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter, Retry
import threading
import os 

ORG_NAME = "JHDevOps"
PAT = os.getenv('GITHUB_PAT')
INPUT_FILE = "repo_access_report.xlsx"  
OUTPUT_FILE = "user_team_membership.xlsx"
MAX_WORKERS = 20


API_BASE = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json"}
AUTH = HTTPBasicAuth(PAT, "")

lock = threading.Lock()
user_team_map = []


def create_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)
    session.auth = AUTH
    return session

session = create_session()


def get_org_teams():
    url = f"{API_BASE}/orgs/{ORG_NAME}/teams?per_page=100"
    results = []
    while url:
        response = session.get(url)
        if response.status_code != 200:
            print(f"Failed to fetch teams: {response.status_code}")
            break
        results.extend(response.json())
        url = response.links.get('next', {}).get('url')
    return results


def is_user_in_team(team_slug, username):
    url = f"{API_BASE}/orgs/{ORG_NAME}/teams/{team_slug}/memberships/{username}"
    response = session.get(url)
    return response.status_code == 200


def process_user(username, teams):
    user_teams = []
    for team in teams:
        if is_user_in_team(team['slug'], username):
            user_teams.append(team['name'])
    with lock:
        user_team_map.append({
            "GitHub Username": username,
            "Teams in JHDevOps Org": ", ".join(user_teams) if user_teams else "-"
        })


def main():
    print("Reading Excel file")
    df = pd.read_excel(INPUT_FILE)
    usernames = set()

    
    for value in df["Individual Repo-Level Access (Non-admin)"].dropna():
        names = [name.strip() for name in str(value).split(",")]
        usernames.update(names)

    print(f"Unique users found: {len(usernames)}")
    teams = get_org_teams()
    print(f"Org teams found: {len(teams)}")

    print("Checking team memberships (parallel)")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_user, user, teams) for user in usernames]
        for future in as_completed(futures):
            future.result()

    print(" Writing output to Excel")
    result_df = pd.DataFrame(user_team_map)
    result_df.to_excel(OUTPUT_FILE, index=False)
    print(f"Done. Output saved to '{OUTPUT_FILE}'")

if __name__ == "__main__":
    main()
