import os
import subprocess
import shutil
import requests
import tempfile
from datetime import datetime
from dateutil import parser as dateparser

GITHUB_API = "https://api.github.com"

def run(cmd, cwd=None):
    print(f"Running: {cmd}")
    subprocess.run(cmd, cwd=cwd, shell=True, check=True)

def get_branches(repo_path):
    result = subprocess.check_output("git for-each-ref --format='%(refname:short)' refs/remotes/origin", shell=True, cwd=repo_path)
    branches = result.decode().strip().split("\n")
    return [b.strip().replace("origin/", "") for b in branches if "HEAD" not in b]

def get_commit_before_date(repo_path, branch, target_date):
    cmd = f"git rev-list -n 1 --before=\"{target_date}\" origin/{branch}"
    commit = subprocess.check_output(cmd, shell=True, cwd=repo_path).decode().strip()
    return commit

def create_github_repo(org, repo_name, token):
    url = f"{GITHUB_API}/orgs/{org}/repos"
    headers = {"Authorization": f"token {token}"}
    data = {"name": repo_name, "private": True}
    response = requests.post(url, json=data, headers=headers)
    response.raise_for_status()
    print(f"Created repo: {repo_name}")
    return response.json()["clone_url"].replace("https://", f"https://{token}@")

def main(old_repo, new_repo, date_str, org, token):
    target_date = dateparser.parse(date_str).isoformat()
    temp_dir = tempfile.mkdtemp()
    os.chdir(temp_dir)

    # Clone original repo
    run(f"git clone --mirror https://{token}@github.com/{org}/{old_repo}.git")
    mirror_path = os.path.join(temp_dir, f"{old_repo}.git")

    # Clone all branches into working repo
    run(f"git clone {mirror_path} {new_repo}")
    repo_path = os.path.join(temp_dir, new_repo)
    os.chdir(repo_path)

    # Get branches and checkout historical state
    branches = get_branches(repo_path)
    print(f"Found branches: {branches}")

    for branch in branches:
        commit = get_commit_before_date(repo_path, branch, target_date)
        if not commit:
            print(f"No commit found for {branch} before {target_date}")
            continue
        run(f"git checkout -b {branch} {commit}")

    # Remove origin and create new repo
    run("git remote remove origin")
    new_url = create_github_repo(org, new_repo, token)
    run(f"git remote add origin {new_url}")

    # Push all branches
    for branch in branches:
        run(f"git push -u origin {branch}")

    print("Done. Repo pushed to GitHub.")

    shutil.rmtree(temp_dir)

# === USAGE ===
# Replace these values with your own before running
if __name__ == "__main__":
    OLD_REPO = "your-old-repo-name"
    NEW_REPO = "your-new-repo-name"
    DATE = "2025-04-24"  # Example: last Thursday
    ORG = "JHDevOps"
    PAT = "your_personal_access_token_here"

    main(OLD_REPO, NEW_REPO, DATE, ORG, PAT)
