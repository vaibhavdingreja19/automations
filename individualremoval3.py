import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from requests.adapters import HTTPAdapter, Retry
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

ORG_NAME = "JHDevOps"
PAT = os.getenv('GITHUB_PAT')
REPO_ACCESS_FILE = "repo_access_report.xlsx"
TEAM_MEMBERSHIP_FILE = "user_team_membership.xlsx"
OUTPUT_FILE = "final_user_audit.xlsx"
MAX_WORKERS = 20


API_BASE = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json"}
AUTH = HTTPBasicAuth(PAT, "")


def create_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)
    session.auth = AUTH
    return session

session = create_session()


def get_user_email(username):
    try:
        url = f"{API_BASE}/users/{username}"
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("email", None)
    except Exception as e:
        print(f"Error fetching email for {username}: {e}")
    return None


def fetch_emails(usernames):
    user_email_map = {}

    def worker(username):
        email = get_user_email(username)
        user_email_map[username] = email or "-"

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(worker, user) for user in usernames]
        for future in as_completed(futures):
            future.result()
    return user_email_map


def main():
    print("Loading input Excel files")
    repo_df = pd.read_excel(REPO_ACCESS_FILE)
    team_df = pd.read_excel(TEAM_MEMBERSHIP_FILE)

    print("Exploring usernames from repo access...")
    user_repo_map = []

    for _, row in repo_df.iterrows():
        repo = row["Repository Name"]
        users = str(row["Individual Repo-Level Access (Non-admin)"]).split(",")
        for user in users:
            user = user.strip()
            if user:
                user_repo_map.append({"GitHub Username": user, "Repository": repo})

    user_repo_df = pd.DataFrame(user_repo_map)
    user_repo_grouped = user_repo_df.groupby("GitHub Username")["Repository"].apply(lambda x: ", ".join(sorted(set(x)))).reset_index()

    print("Merging team and repo info")
    merged_df = pd.merge(team_df, user_repo_grouped, on="GitHub Username", how="outer")

    print("Fetching emails for users")
    usernames = merged_df["GitHub Username"].dropna().unique()
    email_map = fetch_emails(usernames)

    merged_df["GitHub Email"] = merged_df["GitHub Username"].map(email_map)

    print("Writing final output")
    merged_df = merged_df.rename(columns={
        "GitHub Username": "Username",
        "Teams in JHDevOps Org": "Teams",
        "Repository": "Individual Repo Access",
        "GitHub Email": "Email"
    })
    merged_df.to_excel(OUTPUT_FILE, index=False)
    print(f"Done Final report saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
