import requests
import time
import pandas as pd
from datetime import datetime, timedelta
import os
from concurrent.futures import ThreadPoolExecutor, as_completed


TOKEN = ''  # <<< put your PAT here
ORG_NAME = "JHDevOps"
YEARS_THRESHOLD = int(os.getenv("YEARS", "8"))  # optional: env-based years
REPOS_PER_PAGE = 50
BRANCHES_PER_PAGE = 100
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
    """
    Return ONLY non-archived repos for the org.
    Includes public + private + internal (whatever the token can access).
    Archived repos are skipped.
    """
    repos = []
    url = f"{REST_API_ROOT}/orgs/{ORG_NAME}/repos"
    params = {"per_page": 100, "type": "all"}  # type=all includes internal/private/public as accessible

    while url:
        r = requests.get(url, headers=headers_rest, params=params)

        if r.status_code != 200:
            print(f"REST: Error listing org repos: {r.status_code} - {r.text}")
            time.sleep(10)
            continue

        data = r.json()
        for repo in data:
            if not repo.get("archived", False):
                repos.append(repo["name"])

        # Pagination via Link header
        next_url = None
        link = r.headers.get("Link", "")
        if link:
            parts = [p.strip() for p in link.split(",")]
            for p in parts:
                if 'rel="next"' in p:
                    next_url = p[p.find("<") + 1 : p.find(">")]
                    break

        url = next_url
        params = None  # next_url already contains the query params

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
    Returns (email, username) or (None, None).
    """
    repo_url = f"{REST_API_ROOT}/repos/{ORG_NAME}/{repo_name}"
    r_repo = requests.get(repo_url, headers=headers_rest)

    if r_repo.status_code != 200:
        print(f"  REST: Error getting repo info for {repo_name}: {r_repo.status_code}")
        return None, None

    repo_data = r_repo.json()
    default_branch = repo_data.get("default_branch")
    if not default_branch:
        return None, None

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
    print(f"Total NON-archived repos found: {len(all_repos)}")

    # PASS 1: original detection of inactive repos, but in parallel
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
