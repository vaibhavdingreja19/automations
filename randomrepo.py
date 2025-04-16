import requests
import random
import pandas as pd

# Replace this with your actual GitHub PAT
GITHUB_TOKEN = "your_personal_access_token_here"
ORG_NAME = "JHDevOps"
EXCEL_FILE = "github_repos.xlsx"
COLUMN_NAME = "Repo-Name"

# GitHub API endpoint
url = f"https://api.github.com/orgs/{ORG_NAME}/repos?per_page=100"

# Set headers with authentication
headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

# Fetch repositories
response = requests.get(url, headers=headers)
if response.status_code != 200:
    raise Exception(f"GitHub API error: {response.status_code}, {response.text}")

repos = response.json()
if len(repos) < 5:
    raise Exception("Not enough repositories to choose 5 randomly.")

# Pick 5 random repos
random_repos = random.sample(repos, 5)
repo_names = [repo["name"] for repo in random_repos]

# Create Excel file
df = pd.DataFrame(repo_names, columns=[COLUMN_NAME])
df.to_excel(EXCEL_FILE, index=False)

print(f"Saved 5 random repo names to {EXCEL_FILE}")
