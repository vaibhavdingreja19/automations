import os
import subprocess
import shutil
import requests
import tempfile
from dateutil import parser as dateparser

GITHUB_API = "https://api.github.com"

def run(cmd, cwd=None):
    print(f"Running: {cmd}")
    subprocess.run(cmd, cwd=cwd, shell=True, check=True)

def get_branches(repo_path):
    result = subprocess.check_output("git branch -r", shell=True, cwd=repo_path)
    branches = result.decode().strip().split("\n")
    clean = [b.strip().replace("origin/", "") for b in branches if "->" not in b]
    return list(set(clean))

def get_commit_before_date(repo_path, branch, target_date):
    try:
        # Try to find a commit before the given date
        cmd = f"git rev-list -n 1 --before=\"{target_date}\" origin/{branch}"
        commit = subprocess.check_output(cmd, shell=True, cwd=repo_path).decode().strip()
        if not commit:
            # Fallback: first commit of the branch
            cmd = f"git rev-list --max-parents=0 origin/{branch}"
            commit = subprocess.check_output(cmd, shell=True, cwd=repo_path).decode().strip()
            print(f"!! No commit before {target_date} on '{branch}', using first commit: {commit}")
        return commit
    except subprocess.CalledProcessError:
        print(f"!! Skipping branch '{branch}' — could not resolve commit or branch is broken")
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

    # Step 1: Clone the original repo (mirror to get full refs)
    run(f"git clone --mirror https://{token}@github.com/{org}/{old_repo}.git")
    mirror_path = os.path.join(temp_dir, f"{old_repo}.git")

    # Step 2: Clone the mirror repo into working directory
    run(f"git clone {mirror_path} {new_repo}")
    repo_path = os.path.join(temp_dir, new_repo)
    os.chdir(repo_path)

    # Step 3: Fetch all branches
    run("git fetch --all", cwd=repo_path)

    branches = get_branches(repo_path)
    print(f"[+] Found remote branches: {branches}")

    created_branches = []
    skipped_branches = []

    # Step 4: For each branch, checkout to commit at or before date
    for branch in branches:
        commit = get_commit_before_date(repo_path, branch, target_date)
        if not commit:
            skipped_branches.append(branch)
            continue
        try:
            run(f"git checkout -b {branch} {commit}", cwd=repo_path)
            created_branches.append(branch)
        except subprocess.CalledProcessError:
            print(f"!! Failed to checkout {branch} at {commit}")
            skipped_branches.append(branch)

    # Step 5: Remove old remote and add new one
    run("git remote remove origin", cwd=repo_path)
    new_url = create_github_repo(org, new_repo, token)
    run(f"git remote add origin {new_url}", cwd=repo_path)

    # Step 6: Push all successfully created branches
    for branch in created_branches:
        try:
            run(f"git push -u origin {branch}", cwd=repo_path)
        except subprocess.CalledProcessError:
            print(f"!! Failed to push branch {branch}")

    print("\n=== FINAL REPORT ===")
    print(f"[✓] Pushed branches: {created_branches}")
    print(f"[!] Skipped branches: {skipped_branches}")
    print(f"[+] Repo created: https://github.com/{org}/{new_repo}")

    shutil.rmtree(temp_dir)

# === CONFIGURATION ===
if __name__ == "__main__":
    OLD_REPO = "JH_REM_DEVOPS_AUTOMATION"  # Your source repo name
    NEW_REPO = "JH_REM_AUTO_TEST_REVERT"   # New repo to create
    DATE = "2025-04-10"                    # Date to revert branches to
    ORG = "JHDevOps"                       # Your GitHub org
    PAT = "your_personal_access_token_here"  # Replace with your PAT

    main(OLD_REPO, NEW_REPO, DATE, ORG, PAT)
