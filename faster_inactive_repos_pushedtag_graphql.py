# -*- coding: utf-8 -*-
"""
Inactive repo finder (non-archived) + last commit author (default branch)
PLUS GitHub repo "last pushed" timestamp (pushed_at) as an extra Excel column.

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

TOKEN = ''  # <<< put your PAT here (keep it private)
ORG_NAME = "JHDevOps"
YEARS_THRESHOLD = int(os.getenv("YEARS", "8"))  # optional: env-based years
GRAPHQL_URL = "https://api.github.com/graphql"
REST_API_ROOT = "https://api.github.com"

# how many concurrent repo checks in Pass 1
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
    Archived repos are skipped.
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
            print("Error: Could not fetch repositories (check ORG_NAME and token scopes).")
            break

        for repo in repos_data["nodes"]:
            if not repo["isArchived"]:
                repos.append(repo["name"])

        has_next_page = repos_data["pageInfo"]["hasNextPage"]
        end_cursor = repos_data["pageInfo"]["endCursor"]

    return repos


def check_repo_all_branches_old(repo_name):
    """
    Return True if ALL branches in this repo
    only have commits older than cutoff_date.
    If ANY branch has a commit >= cutoff_date => active => False
    """
    has_next_page = True
    end_cursor = None

    query = """
    query($org: String!, $repo: String!, $cursor: String) {
      repository(owner: $org, name: $repo) {
        refs(refPrefix: "refs/heads/", first: 100, after: $cursor) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            name
            target {
              ... on Commit {
                committedDate
              }
            }
          }
        }
      }
    }
    """

    while has_next_page:
        variables = {"org": ORG_NAME, "repo": repo_name, "cursor": end_cursor}
        result = run_graphql_query(query, variables)

        repo_data = result.get("data", {}).get("repository")
        if not repo_data:
            # repo might be missing / no access
            break

        refs = repo_data.get("refs")
        if not refs:
            break

        for branch in refs["nodes"]:
            commit = branch.get("target")
            if not commit:
                continue

            date_str = commit.get("committedDate")
            if not date_str:
                continue

            commit_datetime = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")

            # If ANY branch has a commit >= cutoff, repo is considered active
            if commit_datetime >= cutoff_date:
                return False

        has_next_page = refs["pageInfo"]["hasNextPage"]
        end_cursor = refs["pageInfo"]["endCursor"]

    # Never found a recent commit → fully inactive
    return True


def get_last_commit_default_branch(repo_name):
    """
    Use REST API to grab:
      - last commit author email + username on default branch
      - repo "last pushed" timestamp from GitHub: pushed_at (code activity)

    Returns (email, username, pushed_at)
    """
    repo_url = f"{REST_API_ROOT}/repos/{ORG_NAME}/{repo_name}"
    r_repo = requests.get(repo_url, headers=headers_rest, timeout=60)

    if r_repo.status_code != 200:
        print(f"  REST: Error getting repo info for {repo_name}: {r_repo.status_code}")
        return None, None, None

    repo_data = r_repo.json()
    default_branch = repo_data.get("default_branch")

    # GitHub code-activity timestamp (last push anywhere in repo)
    pushed_at = repo_data.get("pushed_at")  # ISO8601 string

    if not default_branch:
        return None, None, pushed_at

    commits_url = f"{REST_API_ROOT}/repos/{ORG_NAME}/{repo_name}/commits"
    params = {"sha": default_branch, "per_page": 1}
    r_commits = requests.get(commits_url, headers=headers_rest, params=params, timeout=60)

    if r_commits.status_code != 200:
        print(f"  REST: Error getting commits for {repo_name}: {r_commits.status_code}")
        return None, None, pushed_at

    commits = r_commits.json()
    if not commits:
        return None, None, pushed_at

    commit = commits[0]
    commit_author = commit.get("commit", {}).get("author", {})
    email = commit_author.get("email")

    user = commit.get("author")  # top-level GitHub user object
    username = user.get("login") if user else None

    return email, username, pushed_at


def main():
    if not TOKEN.strip():
        raise ValueError("TOKEN is empty. Paste your GitHub PAT into TOKEN first.")

    all_repos = get_all_repos()
    print(f"Total NON-archived repos found: {len(all_repos)}")

    # PASS 1: detection of inactive repos, in parallel
    inactive_repos = []

    print(f"\nStarting PASS 1 with up to {MAX_WORKERS} workers...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_repo = {
            executor.submit(check_repo_all_branches_old, repo): repo
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
                    print(f"[PASS 1] Active: {repo}")
            except Exception as e:
                print(f"[PASS 1] Error checking {repo}: {e}")

    print(f"\nTotal inactive NON-archived repos (all branches > {YEARS_THRESHOLD}y old): {len(inactive_repos)}")

    # PASS 2: for each inactive repo, get last commit info (default branch) + pushed_at
    records = []

    for idx, repo in enumerate(inactive_repos, start=1):
        print(f"[PASS 2] ({idx}/{len(inactive_repos)}) Getting last commit info for {repo}...")
        try:
            email, username, pushed_at = get_last_commit_default_branch(repo)
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
