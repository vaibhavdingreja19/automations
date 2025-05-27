import requests
import pandas as pd
import os


ORG_NAME = "JHDevOps"
GITHUB_PAT = os.getenv()


headers = {
    "Authorization": f"token {GITHUB_PAT}",
    "Accept": "application/vnd.github+json"
}

def get_all_repos_with_estimates(org_name):
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/orgs/{org_name}/repos?per_page=100&page={page}&type=all"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"GitHub API error: {response.status_code}")
            break
        data = response.json()
        if not data:
            break
        for repo in data:
            default_branch_size_kb = repo.get("size", 0)
            estimated_full_size_kb = default_branch_size_kb * 3
            repos.append({
                "name": repo["name"],
                "default_branch_size_kb": default_branch_size_kb,
                "estimated_full_size_kb": estimated_full_size_kb,
                "estimated_full_size_mb": round(estimated_full_size_kb / 1024, 2)
            })
        page += 1
    return repos

def main():
    repos = get_all_repos_with_estimates(ORG_NAME)
    df = pd.DataFrame(repos)
    df.to_excel("estimated_repo_sizes.xlsx", index=False)
    print("Estimated repo sizes saved to 'estimated_repo_sizes.xlsx'.")

if __name__ == "__main__":
    main()
