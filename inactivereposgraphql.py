import os
import time
import requests
import pandas as pd
from datetime import datetime


# ------------ CONFIG -----------------
TOKEN = os.getenv("GITHUB_PAT")   # or put your PAT directly below
# TOKEN = "YOUR_PAT_HERE"         # <<< if you want to hard code it

ORG_NAME = "JHDevOps"
GRAPHQL_URL = "https://api.github.com/graphql"

# <<< HARD CODED PARAMETER >>>
CUTOFF_DATE_STR = "01/09/2017"    # DD/MM/YYYY
# ------------------------------------


def github_headers():
    return {
        "Authorization": f"bearer {TOKEN}",
        "Content-Type": "application/json",
    }


def run_graphql_query(query, variables=None):
    while True:
        r = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=github_headers(),
        )

        if r.status_code == 200:
            return r.json()
        elif r.status_code == 502:
            print("502 from GitHub, retrying in 5 secs...")
            time.sleep(5)
        else:
            print(f"Error {r.status_code}: {r.text}")
            time.sleep(10)


def get_inactive_repos(cutoff_dt):
    inactive = []
    has_next_page = True
    end_cursor = None

    query = """
    query($org: String!, $cursor: String) {
      organization(login: $org) {
        repositories(
          first: 100,
          after: $cursor,
          orderBy: {field: PUSHED_AT, direction: ASC}
        ) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            name
            isArchived
            pushedAt
            updatedAt
          }
        }
      }
    }
    """

    while has_next_page:
        variables = {"org": ORG_NAME, "cursor": end_cursor}
        result = run_graphql_query(query, variables)
        repos_data = result["data"]["organization"]["repositories"]

        for repo in repos_data["nodes"]:
            name = repo["name"]
            pushed_at_str = repo["pushedAt"]
            updated_at_str = repo["updatedAt"]
            archived = repo["isArchived"]

            # Some repos may not have pushedAt (never pushed)
            if pushed_at_str:
                pushed_at = datetime.strptime(pushed_at_str, "%Y-%m-%dT%H:%M:%SZ")
            else:
                pushed_at = datetime.min

            if pushed_at < cutoff_dt:
                inactive.append(
                    {
                        "Repository": name,
                        "Archived": archived,
                        "Last Push (pushedAt)": pushed_at_str,
                        "Last Updated (updatedAt)": updated_at_str,
                    }
                )

        has_next_page = repos_data["pageInfo"]["hasNextPage"]
        end_cursor = repos_data["pageInfo"]["endCursor"]

    return inactive


# ============ MAIN ===============
if __name__ == "__main__":

    # Convert hard-coded date string to datetime
    cutoff_dt = datetime.strptime(CUTOFF_DATE_STR, "%d/%m/%Y")
    print(f"Cutoff Date: {cutoff_dt}")

    if not TOKEN:
        raise SystemExit("ERROR: GITHUB_PAT environment variable is not set.")

    print("Fetching repositories...")
    inactive_repos = get_inactive_repos(cutoff_dt)
    print(f"Total inactive repos found: {len(inactive_repos)}")

    # Export to Excel
    output_file = "inactive_repos_graphql.xlsx"
    pd.DataFrame(inactive_repos).to_excel(output_file, index=False)

    print(f"Done. Saved to '{output_file}'")
