import requests
import time
import pandas as pd
from datetime import datetime, timedelta
import os


TOKEN = ''  # <<< put your PAT here
ORG_NAME = "JHDevOps"
YEARS_THRESHOLD = 8
REPOS_PER_PAGE = 50
BRANCHES_PER_PAGE = 100
GRAPHQL_URL = "https://api.github.com/graphql"
REST_API_ROOT = "https://api.github.com"

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
            headers=headers_graphql
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
              }
            }
          }
        }
        """
        variables = {"org": ORG_NAME, "cursor": end_cursor}
        result = run_graphql_query(query, variables)
        repos_data = result["data"]["organization"]["repositories"]
        repos.extend([repo["name"] for repo in repos_data["nodes"]])
        has_next_page = repos_data["pageInfo"]["hasNextPage"]
        end_cursor = repos_data["pageInfo"]["endCursor"]

    return repos


def check_repo_all_branches_old(repo_name):
    """
    ORIGINAL logic: return True if ALL branches in this repo
    only have commits older than cutoff_date.
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

        refs = repo_data["refs"]

        for branch in refs["nodes"]:
            commit = branch["target"]
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
    Use REST API to grab the last commit on the default branch.
    This is MUCH cheaper than re-walking all branches.

    Returns (email, username) or (None, None).
    """
    # First, get repo info to learn default branch
    repo_url = f"{REST_API_ROOT}/repos/{ORG_NAME}/{repo_name}"
    r_repo = requests.get(repo_url, headers=headers_rest)

    if r_repo.status_code != 200:
        print(f"  REST: Error getting repo info for {repo_name}: {r_repo.status_code}")
        return None, None

    repo_data = r_repo.json()
    default_branch = repo_data.get("default_branch")
    if not default_branch:
        return None, None

    # Now get the last commit on that default branch
    commits_url = f"{REST_API_ROOT}/repos/{ORG_NAME}/{repo_name}/commits"
    params = {"sha": default_branch, "per_page": 1}
    r_commits = requests.get(commits_url, headers=headers_rest, params=params)

    if r_commits.status_code != 200:
        print(f"  REST: Error getting commits for {repo_name}: {r_commits.status_code}")
        return None, None

    commits = r_commits.json()
    if not commits:
        return None, None

    commit = commits[0]
    commit_author = commit.get("commit", {}).get("author", {})
    email = commit_author.get("email")

    user = commit.get("author")  # top-level GitHub user object
    username = user.get("login") if user else None

    return email, username


def main():
    all_repos = get_all_repos()
    print(f"Total repos found: {len(all_repos)}")

    # PASS 1: original fast detection of inactive repos
    inactive_repos = []

    for repo in all_repos:
        print(f"[PASS 1] Checking {repo}...")
        try:
            if check_repo_all_branches_old(repo):
                inactive_repos.append(repo)
        except Exception as e:
            print(f"Error checking {repo}: {e}")

    print(f"\nTotal inactive repos (all branches > {YEARS_THRESHOLD}y old): {len(inactive_repos)}")

    # PASS 2: for each inactive repo, get last commit info (default branch)
    records = []

    for idx, repo in enumerate(inactive_repos, start=1):
        print(f"[PASS 2] ({idx}/{len(inactive_repos)}) Getting last commit info for {repo}...")
        try:
            email, username = get_last_commit_default_branch(repo)
            records.append({
                "Repository": repo,
                "Last Commit Email": email,
                "Last Commit Username": username,
            })
        except Exception as e:
            print(f"Error getting commit info for {repo}: {e}")
            records.append({
                "Repository": repo,
                "Last Commit Email": None,
                "Last Commit Username": None,
            })

    df = pd.DataFrame(records, columns=[
        "Repository",
        "Last Commit Email",
        "Last Commit Username"
    ])
    df.to_excel("inactive_repos_graphql.xlsx", index=False)
    print("\nDone. Saved to 'inactive_repos_graphql.xlsx'")


if __name__ == "__main__":
    main()
