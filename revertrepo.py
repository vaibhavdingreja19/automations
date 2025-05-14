import os
import shutil
import subprocess
import requests
from datetime import datetime

# === CONFIGURATION ===
GITHUB_PAT = ""
ORG_NAME = "JHDevOps"
OLD_REPO = "JH_REM_DEVOPS_AUTOMATION"
NEW_REPO = "rem_Devops_auto_version_1"
CUTOFF_DATE = "2024-12-12"  # Format: YYYY-MM-DD


# === CLONE OLD REPO ===
CLONE_URL = f"https://{GITHUB_PAT}@github.com/{ORG_NAME}/{OLD_REPO}.git"
WORKDIR = "temp_repo_snapshot"

if os.path.exists(WORKDIR):
    shutil.rmtree(WORKDIR)

# Clone repo
subprocess.run(["git", "clone", CLONE_URL, WORKDIR], check=True)
os.chdir(WORKDIR)

# === GET ALL REMOTE BRANCHES ===
branches_output = subprocess.check_output(["git", "ls-remote", "--heads", CLONE_URL]).decode().splitlines()
branches = [
    line.split("refs/heads/")[1]
    for line in branches_output
    if "refs/heads/" in line
]

# === RESET BRANCHES TO COMMITS BEFORE OR ON CUTOFF ===
valid_branches = []
for branch in branches:
    print(f"Processing branch: {branch}")
    subprocess.run(["git", "fetch", "origin", branch], check=True)
    subprocess.run(["git", "checkout", "-B", branch, f"origin/{branch}"], check=True)

    try:
        # Get latest commit before or on the cutoff date
        commit_hash = subprocess.check_output([
            "git", "rev-list", "-1", f'--before={CUTOFF_DATE}T23:59:59', branch
        ]).decode().strip()

        if commit_hash:
            subprocess.run(["git", "reset", "--hard", commit_hash], check=True)
            valid_branches.append(branch)
        else:
            print(f"Skipping branch '{branch}' — no commits before {CUTOFF_DATE}")

    except subprocess.CalledProcessError:
        print(f"Error processing branch {branch}, skipping...")

# === CREATE NEW REPO ON GITHUB ===
print(f"Creating new repo: {NEW_REPO}")
headers = {
    "Authorization": f"token {GITHUB_PAT}",
    "Accept": "application/vnd.github+json"
}
payload = {
    "name": NEW_REPO,
    "private": True
}
create_url = f"https://api.github.com/orgs/{ORG_NAME}/repos"
response = requests.post(create_url, headers=headers, json=payload)

if response.status_code not in [200, 201]:
    print(f"Failed to create repo: {response.status_code} — {response.text}")
    exit(1)

# === PUSH TO NEW REPO ===
NEW_URL = f"https://{GITHUB_PAT}@github.com/{ORG_NAME}/{NEW_REPO}.git"
subprocess.run(["git", "remote", "remove", "origin"], check=True)
subprocess.run(["git", "remote", "add", "origin", NEW_URL], check=True)

for branch in valid_branches:
    subprocess.run(["git", "checkout", branch], check=True)
    subprocess.run(["git", "push", "-u", "origin", branch], check=True)

print(f"\n✅ Done! Snapshot pushed to: https://github.com/{ORG_NAME}/{NEW_REPO}")



import os
import shutil
import subprocess
import requests
from datetime import datetime

# === CONFIGURATION ===
GITHUB_PAT = ""
ORG_NAME = "JHDevOps"
OLD_REPO = "JH_REM_DEVOPS_AUTOMATION"
NEW_REPO = "rem_Devops_auto_version_1"

# === SETUP ===
headers = {
    "Authorization": f"token {GITHUB_PAT}",
    "Accept": "application/vnd.github+json"
}

# === STEP 1: GET DEFAULT BRANCH FROM OLD REPO ===
old_repo_url = f"https://api.github.com/repos/{ORG_NAME}/{OLD_REPO}"
response = requests.get(old_repo_url, headers=headers)

if response.status_code != 200:
    print(f"Failed to fetch old repo: {response.status_code} — {response.text}")
    exit(1)

default_branch = response.json().get("default_branch")
print(f"Default branch in old repo: {default_branch}")

# === STEP 2: SET DEFAULT BRANCH IN NEW REPO ===
new_repo_url = f"https://api.github.com/repos/{ORG_NAME}/{NEW_REPO}"
payload = {
    "default_branch": default_branch
}
response = requests.patch(new_repo_url, headers=headers, json=payload)

if response.status_code not in [200, 201]:
    print(f"Failed to update new repo: {response.status_code} — {response.text}")
    exit(1)

print(f"✅ Default branch of '{NEW_REPO}' set to '{default_branch}'")
