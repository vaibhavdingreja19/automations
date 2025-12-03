import os
import time
import requests
import pandas as pd
from datetime import datetime

# ============ CONFIG =================

# Prefer taking PAT from environment (safer)
TOKEN = os.getenv("GITHUB_PAT")

# Or hard-code it (just DON'T commit this to Git):
# TOKEN = "ghp_your_token_here"

ORG_NAME = "JHDevOps"
GRAPHQL_URL = "https://api.github.com/graphql"

# Hard-coded cutoff date: DD/MM/YYYY
CUTOFF_DATE_STR = "01/01/2017"   # 1 Jan 2017

# =====================================


def github_headers():
    return {
        "Authorization": f"bearer {TOKEN}",
        "Content-Type": "application/json",
    }


def run_graphql_query(query, variables=None):
    """Run a GraphQL query with simple retry/backoff for 502, etc."""
    while True:
        r = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=github_headers(),
        )

        if r.status_code == 200:
            data = r.json()
            # If GraphQL returns logical errors, surface them
            if "errors" in data:
                print("GraphQL errors:", data["errors"])
            return data

        elif r.status_code == 502:
            print("502 from GitHub, retrying in 5 seconds...")
            time.sleep(5)

        else:
            print(f"HTTP Error {r.status_code}: {r.text}")
            time.sleep(10)


def get_all_repos_with_updated_at(cutoff_dt):
    """
    Get all repos in the org whose updatedAt is older than cutoff_dt.
    Returns a list of dicts: { 'name': ..., 'updatedAt': ... }
    """
    inactive_repos = []
    has_next_page = True
    end_cursor = None

    query = """
    query($org: String!, $cursor: String) {
      organization(login: $org) {
        repositories(
          first: 100,
          after: $cursor,
          orderBy: {field: UPDATED_AT, direction: ASC}
        ) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            name
            updatedAt
          }
        }
      }
    }
    """

    while has_next_page:
        variables = {"org": ORG_NAME, "cursor": end_cursor}
        result = run_graphql_query(query, variables)

        org = result.get("data", {}).get("organization")
        if not org:
            print("No organization data returned. Check ORG_NAME / token permissions.")
            break

        repos_data = org["repositories"]
        nodes = repos_data["nodes"]

        for repo in nodes:
            name = repo["name"]
            updated_at_str = repo["updatedAt"]

            if updated_at_str:
                updated_at = datetime.strptime(updated_at_str, "%Y-%m-%dT%H:%M:%SZ")
            else:
                # Extremely rare; treat as very old
                updated_at = datetime.min

            if updated_at < cutoff_dt:
                inactive_repos.append(
                    {
                        "name": name,
                        "updatedAt": updated_at_str,
                    }
                )

        has_next_page = repos_data["pageInfo"]["hasNextPage"]
        end_cursor = repos_data["pageInfo"]["endCursor"]

        print(f"Fetched page of repos; inactive count so far: {len(inactive_repos)}")

    return inactive_repos


def get_repo_teams(repo_name):
    """
    Get teams (ACLs) that have access to a single repo.
    Returns a list of team names.
    """
    teams = []
    has_next_page = True
    end_cursor = None

    query = """
    query($org: String!, $repo: String!, $cursor: String) {
      repository(owner: $org, name: $repo) {
        teams(first: 100, after: $cursor) {
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

    while has_next_page:
        variables = {"org": ORG_NAME, "repo": repo_name, "cursor": end_cursor}
        result = run_graphql_query(query, variables)

        repo = result.get("data", {}).get("repository")
        if not repo:
            # Repo might be missing / renamed / no access
            print(f"Warning: No repository data returned for {repo_name}")
            break

        teams_data = repo["teams"]
        nodes = teams_data["nodes"]

        for team in nodes:
            team_name = team["name"]
            teams.append(team_name)

        has_next_page = teams_data["pageInfo"]["hasNextPage"]
        end_cursor = teams_data["pageInfo"]["endCursor"]

    return teams


# =============== MAIN =================
if __name__ == "__main__":

    if not TOKEN:
        raise SystemExit("ERROR: GITHUB_PAT environment variable is not set and TOKEN is empty.")

    # Parse cutoff date
    cutoff_dt = datetime.strptime(CUTOFF_DATE_STR, "%d/%m/%Y")
    print(f"Cutoff date (using updatedAt): {cutoff_dt}")

    print("Step 1: Collecting repos older than cutoff based on updatedAt...")
    inactive_repo_infos = get_all_repos_with_updated_at(cutoff_dt)
    print(f"Total repos considered inactive (by updatedAt): {len(inactive_repo_infos)}")

    records = []

    print("Step 2: Fetching team ACLs for each inactive repo...")
    for idx, repo_info in enumerate(inactive_repo_infos, start=1):
        repo_name = repo_info["name"]
        updated_at_str = repo_info["updatedAt"]

        print(f"[{idx}/{len(inactive_repo_infos)}] Getting teams for repo: {repo_name}...")
        repo_teams = get_repo_teams(repo_name)

        # Join team names with '; ' for Excel
        teams_joined = "; ".join(repo_teams) if repo_teams else ""

        records.append(
            {
                "Repository": repo_name,
                "Teams": teams_joined,       # ACLs / Teams only
                "UpdatedAt": updated_at_str,
            }
        )

    # Step 3: Export to Excel
    df = pd.DataFrame(records)
    output_file = "inactive_repos_by_updatedAt.xlsx"
    df.to_excel(output_file, index=False)

    print(f"\nDone. Saved to '{output_file}'")
