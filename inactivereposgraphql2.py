import requests
import time
import pandas as pd
from datetime import datetime, timedelta
import os


TOKEN = ''   # <<< put your PAT here
ORG_NAME = "JHDevOps"
YEARS_THRESHOLD = 8
REPOS_PER_PAGE = 50
BRANCHES_PER_PAGE = 100
GRAPHQL_URL = "https://api.github.com/graphql"

headers = {
    "Authorization": f"bearer {TOKEN}",
    "Content-Type": "application/json"
}

cutoff_date = datetime.utcnow() - timedelta(days=YEARS_THRESHOLD * 365)


def run_graphql_query(query, variables=None):
    while True:
        response = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=headers
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
    Return True if ALL branches in this repo are older than cutoff_date.
    (Same logic as your original code, only checking committedDate.)
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

            # If any branch has a commit >= cutoff, repo is active
            if commit_datetime >= cutoff_date:
                return False

        has_next_page = refs["pageInfo"]["hasNextPage"]
        end_cursor = refs["pageInfo"]["endCursor"]

    # If we never found a recent commit, consider repo fully inactive
    return True


def get_latest_commit_info(repo_name):
    """
    For a given repo, scan all branches and return the MOST RECENT commit info:
    - latest_date   (datetime or None)
    - latest_email  (author email)
    - latest_login  (GitHub username / login)
    This is called ONLY for repos already known to be inactive.
    """
    latest_date = None
    latest_email = None
    latest_login = None

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
                author {
                  email
                  user {
                    login
                  }
                }
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

            if latest_date is None or commit_datetime > latest_date:
                latest_date = commit_datetime
                author = commit.get("author") or {}
                latest_email = author.get("email")
                user = author.get("user") or {}
                latest_login = user.get("login")

        has_next_page = refs["pageInfo"]["hasNextPage"]
        end_cursor = refs["pageInfo"]["endCursor"]

    return {
        "latest_date": latest_date,
        "latest_email": latest_email,
        "latest_login": latest_login,
    }


def main():
    all_repos = get_all_repos()
    print(f"Total repos found: {len(all_repos)}")

    # PASS 1: identify inactive repos (same as original behaviour)
    inactive_repos = []

    for repo in all_repos:
        print(f"[PASS 1] Checking {repo}...")
        try:
            if check_repo_all_branches_old(repo):
                inactive_repos.append(repo)
        except Exception as e:
            print(f"Error checking {repo}: {e}")

    print(f"\nTotal inactive repos (all branches > {YEARS_THRESHOLD}y old): {len(inactive_repos)}")

    # PASS 2: for inactive repos, get last commit email + username
    records = []

    for idx, repo in enumerate(inactive_repos, start=1):
        print(f"[PASS 2] ({idx}/{len(inactive_repos)}) Getting last commit info for {repo}...")
        try:
            info = get_latest_commit_info(repo)
            records.append({
                "Repository": repo,
                "Last Commit Email": info["latest_email"],
                "Last Commit Username": info["latest_login"],
            })
        except Exception as e:
            print(f"Error getting commit info for {repo}: {e}")
            records.append({
                "Repository": repo,
                "Last Commit Email": None,
                "Last Commit Username": None,
            })

    # Export to Excel
    df = pd.DataFrame(records, columns=[
        "Repository",
        "Last Commit Email",
        "Last Commit Username"
    ])
    df.to_excel("inactive_repos_graphql.xlsx", index=False)
    print("\nDone. Saved to 'inactive_repos_graphql.xlsx'")


if __name__ == "__main__":
    main()
