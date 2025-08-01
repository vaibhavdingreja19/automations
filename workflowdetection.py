import requests
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# -------- CONFIG --------
GITHUB_TOKEN = "ghp_yourPAT"
ORG = "JHDevOps"
DAYS_ACTIVE = 365
OUTPUT_FILE = "github_actions_audit_fast.xlsx"
THREADS = 30
# ------------------------

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

GRAPHQL_URL = "https://api.github.com/graphql"
REST_URL = "https://api.github.com"

cutoff_date = datetime.utcnow() - timedelta(days=DAYS_ACTIVE)


def run_graphql_query(query, variables=None):
    response = requests.post(
        GRAPHQL_URL,
        headers=HEADERS,
        json={"query": query, "variables": variables or {}}
    )
    response.raise_for_status()
    return response.json()


def fetch_all_repos():
    repos = []
    has_next_page = True
    after_cursor = None

    print("📦 Fetching all repositories from org using GraphQL...")

    while has_next_page:
        query = """
        query ($org: String!, $cursor: String) {
          organization(login: $org) {
            repositories(first: 100, after: $cursor) {
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                name
                isPrivate
                isArchived
              }
            }
          }
        }
        """
        variables = {"org": ORG, "cursor": after_cursor}
        result = run_graphql_query(query, variables)
        repo_nodes = result["data"]["organization"]["repositories"]["nodes"]
        repos.extend([r["name"] for r in repo_nodes if not r["isArchived"]])
        page_info = result["data"]["organization"]["repositories"]["pageInfo"]
        has_next_page = page_info["hasNextPage"]
        after_cursor = page_info["endCursor"]

    print(f"✅ Total repositories fetched: {len(repos)}")
    return repos


def check_repo_actions(repo):
    # Step 1: Check if .github/workflows exists
    workflows_url = f"{REST_URL}/repos/{ORG}/{repo}/contents/.github/workflows"
    resp = requests.get(workflows_url, headers=HEADERS)
    if resp.status_code != 200:
        return None  # No workflows

    # Step 2: List workflows
    actions_api = f"{REST_URL}/repos/{ORG}/{repo}/actions/workflows"
    actions_resp = requests.get(actions_api, headers=HEADERS)
    if actions_resp.status_code != 200:
        return None

    workflows = actions_resp.json().get("workflows", [])
    active = []
    inactive = []

    for wf in workflows:
        wf_name = wf.get("name")
        wf_id = wf.get("id")
        run_url = f"{REST_URL}/repos/{ORG}/{repo}/actions/workflows/{wf_id}/runs?per_page=1"
        run_resp = requests.get(run_url, headers=HEADERS)
        if run_resp.status_code != 200:
            continue
        runs = run_resp.json().get("workflow_runs", [])
        if runs:
            last_run_time = runs[0].get("updated_at")
            dt = datetime.strptime(last_run_time, "%Y-%m-%dT%H:%M:%SZ")
            if dt >= cutoff_date:
                active.append({"repository": repo, "workflow": wf_name})
            else:
                inactive.append({"repository": repo, "workflow": wf_name})
        else:
            inactive.append({"repository": repo, "workflow": wf_name})

    return {
        "repo": repo,
        "active": active,
        "inactive": inactive
    }


def main():
    all_repos = fetch_all_repos()

    repos_with_actions = []
    active_workflows = []
    inactive_workflows = []

    print(f"\n🚀 Checking workflows using {THREADS} threads...")
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        future_to_repo = {executor.submit(check_repo_actions, repo): repo for repo in all_repos}
        for future in as_completed(future_to_repo):
            result = future.result()
            if result:
                repos_with_actions.append({"repository": result["repo"]})
                active_workflows.extend(result["active"])
                inactive_workflows.extend(result["inactive"])

    # Save to Excel
    with pd.ExcelWriter(OUTPUT_FILE) as writer:
        pd.DataFrame(repos_with_actions).to_excel(writer, sheet_name="Repos_Using_Actions", index=False)
        pd.DataFrame(active_workflows).to_excel(writer, sheet_name="Active_Workflows", index=False)
        pd.DataFrame(inactive_workflows).to_excel(writer, sheet_name="Inactive_Workflows", index=False)

    print(f"\n✅ Done! Output saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
