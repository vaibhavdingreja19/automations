import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# === CONFIG ===
ORG_NAME = "JHDevOps"
PAT = ""  # Replace with your actual GitHub PAT
REPO_ACCESS_FILE = "repo_access_report.xlsx"
TEAM_MEMBERSHIP_FILE = "user_team_membership.xlsx"
OUTPUT_FILE = "final_user_audit.xlsx"
MAX_WORKERS = 20

# === HEADERS for GraphQL ===
GRAPHQL_URL = "https://api.github.com/graphql"
HEADERS = {
    "Authorization": f"Bearer {PAT}",
    "Content-Type": "application/json"
}

# === Fetch user emails via GraphQL (for org members only) ===
def fetch_all_user_metadata():
    users = {}
    has_next_page = True
    end_cursor = None

    while has_next_page:
        query = """
        query ($org: String!, $cursor: String) {
          organization(login: $org) {
            membersWithRole(first: 100, after: $cursor) {
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                login
                name
                email
              }
            }
          }
        }
        """
        variables = {"org": ORG_NAME, "cursor": end_cursor}
        response = requests.post(GRAPHQL_URL, headers=HEADERS, json={"query": query, "variables": variables})
        if response.status_code != 200:
            print("Failed to fetch from GitHub GraphQL API:", response.text)
            break

        data = response.json()
        members = data["data"]["organization"]["membersWithRole"]["nodes"]
        for member in members:
            users[member["login"]] = {
                "name": member["name"] or "-",
                "email": member["email"] or "-"
            }

        page_info = data["data"]["organization"]["membersWithRole"]["pageInfo"]
        has_next_page = page_info["hasNextPage"]
        end_cursor = page_info["endCursor"]

    return users

# === MAIN ===
def main():
    print("📥 Loading Excel files...")
    repo_df = pd.read_excel(REPO_ACCESS_FILE)
    team_df = pd.read_excel(TEAM_MEMBERSHIP_FILE)

    print("🧹 Exploding individual access to map user→repo...")
    user_repo_map = []
    for _, row in repo_df.iterrows():
        repo = row["Repository Name"]
        users = str(row["Individual Repo-Level Access (Non-admin)"]).split(",")
        for user in users:
            user = user.strip()
            if user:
                user_repo_map.append({"GitHub Username": user, "Repository": repo})

    user_repo_df = pd.DataFrame(user_repo_map)
    user_repo_grouped = user_repo_df.groupby("GitHub Username")["Repository"].apply(
        lambda x: ", ".join(sorted(set(x)))).reset_index()

    print("🔗 Merging team and repo data...")
    merged_df = pd.merge(team_df, user_repo_grouped, on="GitHub Username", how="outer")

    print("📡 Fetching emails via GraphQL...")
    user_metadata = fetch_all_user_metadata()

    print("💾 Preparing final output...")
    merged_df["Name"] = merged_df["GitHub Username"].map(lambda x: user_metadata.get(x, {}).get("name", "-"))
    merged_df["Email"] = merged_df["GitHub Username"].map(lambda x: user_metadata.get(x, {}).get("email", "-"))

    final_df = merged_df.rename(columns={
        "GitHub Username": "Username",
        "Teams in JHDevOps Org": "Teams",
        "Repository": "Individual Repo Access"
    })

    final_df = final_df[["Username", "Name", "Teams", "Individual Repo Access", "Email"]]

    final_df.to_excel(OUTPUT_FILE, index=False)
    print(f"✅ Done. Final enriched report saved to '{OUTPUT_FILE}'")

if __name__ == "__main__":
    main()
