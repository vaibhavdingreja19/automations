import pandas as pd
import requests

# ==== CONFIGURATION ====
EXCEL_FILE = 'inactive_repos_graphql.xlsx'
ORG = 'JHDevOps'
GITHUB_TOKEN = 'ghp_...'  # insert your real token here

ALLOWED_TEAMS = {
    'jh_devops_pipeline_team_acl',
    'jh_devsecops_cdo_release_engineers_acl'
}

headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

# ==== Load Excel and normalize repo names ====
df = pd.read_excel(EXCEL_FILE, engine='openpyxl')
repos = [r.strip().lower() for r in df.iloc[1:, 0].dropna().tolist()]

# ==== Get full list of teams in org ====
def get_all_teams():
    teams = []
    page = 1
    while True:
        url = f"https://api.github.com/orgs/{ORG}/teams?page={page}&per_page=100"
        r = requests.get(url, headers=headers)
        if r.status_code != 200 or not r.json():
            break
        teams.extend(r.json())
        page += 1
    return teams

# ==== Build map of which teams have access to which repos ====
def get_team_repos(team_slug):
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/orgs/{ORG}/teams/{team_slug}/repos?page={page}&per_page=100"
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        repos.extend(repo['name'].lower() for repo in batch)
        page += 1
    return set(repos)

# ==== Build a repo -> teams map (only for repos in Excel) ====
team_repo_map = {}
all_teams = get_all_teams()

for team in all_teams:
    slug = team['slug'].lower()
    repos_with_team = get_team_repos(slug)
    for repo in repos:
        if repo in repos_with_team:
            team_repo_map.setdefault(repo, set()).add(slug)

# ==== Get collaborators for a repo ====
def get_collaborators(repo):
    url = f"https://api.github.com/repos/{ORG}/{repo}/collaborators?affiliation=all"
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        return [user['login'] for user in r.json()]
    return []

# ==== Final check ====
final_repos = []

for repo in repos:
    print(f"Checking: {repo}")
    collaborators = get_collaborators(repo)
    teams_with_access = team_repo_map.get(repo, set())

    if collaborators:
        continue  # skip if any collaborator exists

    if teams_with_access and teams_with_access.issubset(ALLOWED_TEAMS):
        final_repos.append(repo)

# ==== Output result ====
print("\n✅ Repos with ONLY allowed team access and no collaborators:")
for r in final_repos:
    print(r)

# Optional: Save to Excel
pd.DataFrame(final_repos, columns=["Repo"]).to_excel("repos_only_allowed_teams.xlsx", index=False)
