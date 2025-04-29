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
    result = subprocess.check_output(
        "git branch -r", shell=True, cwd=repo_path
    )
    branches = result.decode().strip().split("\n")
    clean = [b.strip().replace("origin/", "") for b in branches if "->" not in b]
    return list(set(clean))

def get_commit_before_date(repo_path, branch, target_date):
    try:
        cmd = f"git rev-list -n 1 --before=\"{target_date}\" {branch}"
        commit = subprocess.check_output(cmd, shell=True, cwd=repo_path).decode().strip()
        return commit
    except subprocess.CalledProcessError:
        print(f"!! Skipping branch '{branch}' — no commit before {target_date}")
        return None

def create_github_repo(org, repo_name, token):
    url = f"{GITHUB_API}/orgs/{org}/repos"
    headers = {"Authorization": f"token {token}"}
    data = {"name": repo_name, "private": True}
    response = requests.post(url, json=data, headers=headers)
    response.raise_for_status()
    print(f"[+] Created new repo: {repo_name}")
    return response.json()["clone_url"].replace("https://", f"https://{token}@")

def main(old_repo, new_repo, date_str, org, token):
    target_date = dateparser.parse(date_str).isoformat()
    temp_dir = tempfile.mkdtemp()
    os.chdir(temp_dir)

    # Clone original repo (mirror to get all refs)
    run(f"git clone --mirror https://{token}@github.com/{org}/{old_repo}.git")
    mirror_path = os.path.join(temp_dir, f"{old_repo}.git")

    # Create working repo from mirror
    run(f"git clone {mirror_path} {new_repo}")
    repo_path = os.path.join(temp_dir, new_repo)
    os.chdir(repo_path)

    # Fetch all remote branches
    run("git fetch --all", cwd=repo_path)

    branches = get_branches(repo_path)
    print(f"[+] Found branches: {branches}")

    for branch in branches:
        commit = get_commit_before_date(repo_path, branch, target_date)
        if not commit:
            continue
        try:
            run(f"git checkout -b {branch} {commit}", cwd=repo_path)
        except subprocess.CalledProcessError:
            print(f"!! Error checking out branch {branch} at commit {commit}")
            continue

    # Remove old origin, create new repo
    run("git remote remove origin", cwd=repo_path)
    new_url = create_github_repo(org, new_repo, token)
    run(f"git remote add origin {new_url}", cwd=repo_path)

    # Push all checked-out branches
    for branch in branches:
        if os.path.exists(os.path.join(repo_path, ".git", "refs", "heads", branch)):
            try:
                run(f"git push -u origin {branch}", cwd=repo_path)
            except subprocess.CalledProcessError:
                print(f"!! Failed to push branch {branch}")

    print("\n[✓] Done. New repo is live on GitHub.")
    shutil.rmtree(temp_dir)

# ============ CONFIGURATION ============
# Replace these values before running
if __name__ == "__main__":
    OLD_REPO = "JH_REM_DEVOPS_AUTOMATION"
    NEW_REPO = "JH_REM_AUTO_TEST_REVERT"
    DATE = "2025-04-10"  # Example: revert to state on April 10, 2025
    ORG = "JHDevOps"
    PAT = "your_personal_access_token_here"

    main(OLD_REPO, NEW_REPO, DATE, ORG, PAT)
