import pandas as pd
import requests

# === CONFIGURATION ===
EXCEL_FILE = 'repos.xlsx'
ORG = 'JHDevOps'
GITHUB_TOKEN = 'your_pat_token_here'  # Replace this with your actual PAT

# === HEADERS ===
headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

# === Load repo list from Excel (start from row 2) ===
df = pd.read_excel(EXCEL_FILE, engine='openpyxl')
repos = df.iloc[1:, 0].dropna().tolist()  # Assuming repo names are in the first column

no_access_repos = []

def has_any_access(repo):
    # 1. Check outside collaborators
    collab_url = f"https://api.github.com/repos/{ORG}/{repo}/collaborators"
    r = requests.get(collab_url, headers=headers)
    if r.status_code == 200 and r.json():
        return True

    # 2. Check repo teams
    teams_url = f"https://api.github.com/repos/{ORG}/{repo}/teams"
    r = requests.get(teams_url, headers=headers)
    if r.status_code == 200 and r.json():
        return True

    # 3. Check direct collaborators
    perm_url = f"https://api.github.com/repos/{ORG}/{repo}/permissions"
    r = requests.get(perm_url, headers=headers)
    if r.status_code == 200 and r.json():
        return True

    return False

for repo in repos:
    print(f"Checking access for repo: {repo}")
    try:
        if not has_any_access(repo.strip()):
            no_access_repos.append(repo)
    except Exception as e:
        print(f"Error checking repo {repo}: {e}")

# === Output the final list ===
print("\nRepos with NO access:")
for r in no_access_repos:
    print(r)

# Optional: save to Excel
output_df = pd.DataFrame(no_access_repos, columns=["Repo With No Access"])
output_df.to_excel("repos_with_no_access.xlsx", index=False)
