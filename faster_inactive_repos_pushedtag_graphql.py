# -*- coding: utf-8 -*-
"""
Inactive repo finder (non-archived) based on GitHub repo 'pushed_at' (code activity),
PLUS last commit author (default branch) and pushed_at exported to Excel.

Requirements:
    pip install requests pandas openpyxl
Run in Spyder.
"""

import requests
import time
import pandas as pd
from datetime import datetime, timedelta
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

TOKEN = ''  # <<< put your PAT here
ORG_NAME = "JHDevOps"
YEARS_THRESHOLD = int(os.getenv("YEARS", "7"))  # default 7 if not provided
GRAPHQL_URL = "https://api.github.com/graphql"
REST_API_ROOT = "https://api.github.com"
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "5"))

headers_graphql = {
    "Authorization": f"bearer {TOKEN}",
    "Content-Type": "application/json"
}

headers_rest = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json"
}

cutoff_date = datetime.utcnow() - timedelta(days=YEARS_THRESHOLD * 365)


def run_graphql_query(query, variables=None):
    while True:
        response = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=headers_graphql,
            timeout=60
        )
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 502:
            print("502 error, retrying after 5 seconds...")
            time.sleep(5)
        else:
            print(f"Error {response.status_code}: {response.text}")
            time.sleep(10)


def get_all_repos():
    """
    Return ONLY non-archived repos for the org.
    """
    repos = []
    has_next_page = True
    end_cursor = None

    while has_next_page:
        query = """
        query($org: String!, $cursor: String) {
          organization(login: $org) {
            repositories(first: 50, after: $cursor) {
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                name
                isArchived
              }
            }
          }
        }
        """
        variables = {"org": ORG_NAME, "cursor": end_cursor}
        result = run_graphql_query(query, variables)

        repos_data = result.get("data", {}).get("organization", {}).get("repositories")
        if not repos_data:
            print("Error: Could not fetch repositories (check ORG_NAME and token scopes/SSO).")
            break

        for repo in repos_data["nodes"]:
            if not repo.get("isArchived", False):
                repos.append(repo["name"])

        has_next_page = repos_data["pageInfo"]["hasNextPage"]
        end_cursor = repos_data["pageInfo"]["endCursor"]

    return repos


def get_repo_pushed_at(repo_name):
    """
    Fetch repo pushed_at via REST. Returns datetime or None.
    """
    repo_url = f"{REST_API_ROOT}/repos/{ORG_NAME}/{repo_name}"
    r = requests.get(repo_url, headers=headers_rest, timeout=60)
    if r.status_code != 200:
        print(f"  REST: Error getting repo info for {repo_name}: {r.status_code} {r.text[:200]}")
        return None

    pushed_at_str = r.json().get("pushed_at")
    if not pushed_at_str:
        return None

    # Example: "2025-12-16T10:22:33Z"
    return datetime.strptime(pushed_at_str, "%Y-%m-%dT%H:%M:%SZ")


def is_repo_inactive_by_pushed_at(repo_name):
    """
    Repo is inactive if pushed_at is older than cutoff_date.
    If pushed_at can't be fetched, treat as UNKNOWN -> mark active (False) to avoid false positives.
    """
    pushed_dt = get_repo_pushed_at(repo_name)
    if pushed_dt is None:
        print(f"  WARN: Could not read pushed_at for {repo_name} -> treating as ACTIVE/UNKNOWN")
        return False

    return pushed_dt < cutoff_date


def get_last_commit_default_branch_and_pushed_at(repo_name):
    """
    Use REST API to grab:
      - last commit author email + username on default branch
      - repo pushed_at (code activity timestamp)

    Returns (email, username, pushed_at_str)
    """
    repo_url = f"{REST_API_ROOT}/repos/{ORG_NAME}/{repo_name}"
    r_repo = requests.get(repo_url, headers=headers_rest, timeout=60)

    if r_repo.status_code != 200:
        print(f"  REST: Error getting repo info for {repo_name}: {r_repo.status_code}")
        return None, None, None

    repo_data = r_repo.json()
    default_branch = repo_data.get("default_branch")
    pushed_at_str = repo_data.get("pushed_at")

    if not default_branch:
        return None, None, pushed_at_str

    commits_url = f"{REST_API_ROOT}/repos/{ORG_NAME}/{repo_name}/commits"
    params = {"sha": default_branch, "per_page": 1}
    r_commits = requests.get(commits_url, headers=headers_rest, params=params, timeout=60)

    if r_commits.status_code != 200:
        print(f"  REST: Error getting commits for {repo_name}: {r_commits.status_code}")
        return None, None, pushed_at_str

    commits = r_commits.json()
    if not commits:
        return None, None, pushed_at_str

    commit = commits[0]
    commit_author = commit.get("commit", {}).get("author", {})
    email = commit_author.get("email")

    user = commit.get("author")
    username = user.get("login") if user else None

    return email, username, pushed_at_str


def main():
    if not TOKEN.strip():
        raise ValueError("TOKEN is empty. Paste your GitHub PAT into TOKEN first.")

    all_repos = get_all_repos()
    print(f"Total NON-archived repos found: {len(all_repos)}")
    print(f"Cutoff (UTC): {cutoff_date}  |  Threshold: {YEARS_THRESHOLD} years\n")

    inactive_repos = []

    print(f"Starting PASS 1 (pushed_at based) with up to {MAX_WORKERS} workers...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_repo = {
            executor.submit(is_repo_inactive_by_pushed_at, repo): repo
            for repo in all_repos
        }

        for future in as_completed(future_to_repo):
            repo = future_to_repo[future]
            try:
                is_inactive = future.result()
                if is_inactive:
                    inactive_repos.append(repo)
                    print(f"[PASS 1] Inactive: {repo}")
                else:
                    print(f"[PASS 1] Active:   {repo}")
            except Exception as e:
                print(f"[PASS 1] Error checking {repo}: {e}")

    print(f"\nTotal inactive NON-archived repos (pushed_at > {YEARS_THRESHOLD}y old): {len(inactive_repos)}")

    # PASS 2: for each inactive repo, get last commit info (default branch) + pushed_at
    records = []

    for idx, repo in enumerate(inactive_repos, start=1):
        print(f"[PASS 2] ({idx}/{len(inactive_repos)}) Getting last commit info for {repo}...")
        try:
            email, username, pushed_at = get_last_commit_default_branch_and_pushed_at(repo)
            records.append({
                "Repository": repo,
                "Last Commit Email": email,
                "Last Commit Username": username,
                "Repo Last Pushed (pushed_at)": pushed_at,
            })
        except Exception as e:
            print(f"Error getting commit info for {repo}: {e}")
            records.append({
                "Repository": repo,
                "Last Commit Email": None,
                "Last Commit Username": None,
                "Repo Last Pushed (pushed_at)": None,
            })

    df = pd.DataFrame(records, columns=[
        "Repository",
        "Last Commit Email",
        "Last Commit Username",
        "Repo Last Pushed (pushed_at)"
    ])

    df.to_excel("inactive_repos_graphql.xlsx", index=False)
    print("\nDone. Saved to 'inactive_repos_graphql.xlsx'")


if __name__ == "__main__":
    main()
