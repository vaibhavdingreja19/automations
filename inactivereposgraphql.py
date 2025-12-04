import requests
import time
import pandas as pd
from datetime import datetime, timedelta
import os


TOKEN = ''
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
        response = requests.post(GRAPHQL_URL, json={"query": query, "variables": variables}, headers=headers)
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
        repos_data = result['data']['organization']['repositories']
        repos.extend([repo['name'] for repo in repos_data['nodes']])
        has_next_page = repos_data['pageInfo']['hasNextPage']
        end_cursor = repos_data['pageInfo']['endCursor']
    return repos


def check_repo_all_branches_old(repo_name):
    has_next_page = True
    end_cursor = None

    while has_next_page:
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
        variables = {"org": ORG_NAME, "repo": repo_name, "cursor": end_cursor}
        result = run_graphql_query(query, variables)
        refs = result['data']['repository']['refs']

        for branch in refs['nodes']:
            date_str = branch['target']['committedDate']
            commit_datetime = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
            if commit_datetime >= cutoff_date:
                return False  

        has_next_page = refs['pageInfo']['hasNextPage']
        end_cursor = refs['pageInfo']['endCursor']

    return True  


def main():
    all_repos = get_all_repos()
    print(f"Total repos found: {len(all_repos)}")
    inactive_repos = []

    for repo in all_repos:
        print(f"Checking {repo}...")
        try:
            if check_repo_all_branches_old(repo):
                inactive_repos.append(repo)
        except Exception as e:
            print(f"Error checking {repo}: {e}")

    df = pd.DataFrame(inactive_repos, columns=["Fully Inactive Repos (All Branches >8y old)"])
    df.to_excel("inactive_repos_graphql.xlsx", index=False)
    print("Done. Saved to 'inactive_repos_graphql.xlsx'")


if __name__ == "__main__":
    main()
