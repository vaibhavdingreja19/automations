import pandas as pd
import requests

# === CONFIGURATION ===
EXCEL_FILE = 'repos.xlsx'
ORG = 'JHDevOps'
GITHUB_TOKEN = 'your_pat_token_here'  # Replace with your actual PAT

# Hardcode the 2 team slugs (not names — use slug from GitHub URL like 'devops-team', 'qa-team')
ALLOWED_TEAMS = {'team-a', 'team-b'}  # <- Change this

headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

# === Load repo list from Excel (starting from row 2) ===
df = pd.read_excel(EXCEL_FILE, engine='openpyxl')
repos = df.iloc[1:, 0].dropna().tolist()  # Repo names assumed in column A

allowed_repos = []

def get_repo_teams(repo):
    url = f"https://api.github.com/repos/{ORG}/{repo}/teams"
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        return {team['slug'] for team in r.json()}
    return set()

def get_repo_collaborators(repo):
    url = f"https://api.github.com/repos/{ORG}/{repo}/collaborators"
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        return [collab['login'] for collab in r.json()]
    return []

for repo in repos:
    repo = repo.strip()
    print(f"Checking: {repo}")

    try:
        team_slugs = get_repo_teams(repo)
        collaborators = get_repo_collaborators(repo)

        # Check if teams are a subset of ALLOWED_TEAMS and no other collaborators exist
        if team_slugs.issubset(ALLOWED_TEAMS) and len(collaborators) == 0:
            allowed_repos.append(repo)
    except Exception as e:
        print(f"Error processing {repo}: {e}")

# === Output ===
print("\nRepos where ONLY team-a or team-b (or both) have access, and NO other collaborators:")
for r in allowed_repos:
    print(r)

# Optional: Save to Excel
pd.DataFrame(allowed_repos, columns=["Allowed Repos"]).to_excel("allowed_team_only_repos.xlsx", index=False)
