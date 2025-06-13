import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter, Retry
import threading
import os


ORG_NAME = "JHDevOps"
PAT = os.getenv('GITHUB_PAT') 


API_BASE = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json"}
AUTH = HTTPBasicAuth(PAT, "")
MAX_WORKERS = 30


lock = threading.Lock()
data_rows = []


def create_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)
    session.auth = AUTH
    return session

session = create_session()


def get_paginated(url):
    results = []
    while url:
        try:
            response = session.get(url, timeout=15)
            if response.status_code != 200:
                print(f"⚠️ Failed: {url} - {response.status_code}")
                break
            results.extend(response.json())
            url = response.links.get('next', {}).get('url')
        except Exception as e:
            print(f"Exception during request: {e}")
            break
    return results

def get_repos(org):
    return get_paginated(f"{API_BASE}/orgs/{org}/repos?per_page=100")

def get_org_admins(org):
    admins = get_paginated(f"{API_BASE}/orgs/{org}/members?role=admin")
    return {admin['login'] for admin in admins}

def get_repo_collaborators(repo_full_name, org_admins):
    url = f"{API_BASE}/repos/{repo_full_name}/collaborators?affiliation=direct"
    collabs = get_paginated(url)
    return [c['login'] for c in collabs if c['login'] not in org_admins]

def get_repo_teams(repo_full_name):
    url = f"{API_BASE}/repos/{repo_full_name}/teams"
    teams = get_paginated(url)
    return [team['name'] for team in teams]

def process_repo(repo, org_admins):
    full_name = repo['full_name']
    try:
        teams = get_repo_teams(full_name)
        users = get_repo_collaborators(full_name, org_admins)
        with lock:
            data_rows.append({
                "Repository Name": repo['name'],
                "Teams/Groups with Access": ", ".join(teams) if teams else "-",
                "Individual Repo-Level Access (Non-admin)": ", ".join(users) if users else "-"
            })
    except Exception as e:
        print(f"Error processing {full_name}: {e}")


def main():
    print(" Getting org admin")
    org_admins = get_org_admins(ORG_NAME)

    print("Getting repository list")
    repos = get_repos(ORG_NAME)

    #print(f"Starting concurrent processing with {MAX_WORKERS} workers")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_repo, repo, org_admins) for repo in repos]
        for future in as_completed(futures):
            future.result()

    
    df = pd.DataFrame(data_rows)
    df.to_excel("repo_access_report.xlsx", index=False)
    print("Report saved as 'repo_access_report.xlsx'")

if __name__ == "__main__":
    main()
