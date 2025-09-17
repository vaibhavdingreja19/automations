#!/usr/bin/env python3
import base64
import os
import sys
from typing import Optional, Tuple, List
import requests

# -------------------- CONFIG --------------------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "REPLACE_WITH_YOUR_PAT")  # or set env var
ORG = "JHDevOps"

REPOS = [
    "JH-Central-Reg-UI",
    "JH-Central-Reg-Backend",
    "CRVerifyIdentityUI",
    "CRManulifeCustomerAPI",
    "CRManulifeAgentAPI",
    "JH-Central-Reg-CreateInvitationLink",
    "JH-Central-Reg-ProviderRegistration",
    "JH-Central-Reg-ProviderUI",
    "JH-Central-Reg-DLVerification",
    "JH-CLAM-VERIFY-UI",
    "JH-Central-Reg-IdentityVerification",
    "JH-Central-JHIAM",
]

# Branch name variants to try (case-insensitive match)
BRANCH_CANDIDATES = ["Develop", "develop", "DEVELOP"]

# Code Owners you want to enforce
CODEOWNERS_USERS = ["@chhodvi", "@gannara", "@venkati"]

# PR review requirements
REQUIRED_APPROVING_REVIEWS = 1      # set 2 or 3 if you want more than one approval
DISMISS_STALE_REVIEWS = True
ENFORCE_ADMINS = True               # protect admins as well

# -------------------- CONSTANTS --------------------
API = "https://api.github.com"
HDRS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "Content-Type": "application/json",
}

# -------------------- HELPERS --------------------
def gh_get(url, **kwargs):
    r = requests.get(url, headers=HDRS, **kwargs)
    return r

def gh_put(url, json=None, **kwargs):
    r = requests.put(url, headers=HDRS, json=json, **kwargs)
    return r

def gh_post(url, json=None, **kwargs):
    r = requests.post(url, headers=HDRS, json=json, **kwargs)
    return r

def gh_put_contents(owner:str, repo:str, path:str, content_bytes:bytes, message:str, branch:str, sha:Optional[str]=None):
    """Create or update a file via the Contents API."""
    url = f"{API}/repos/{owner}/{repo}/contents/{path}"
    body = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
        "branch": branch,
        "committer": {
            "name": "Automation Bot",
            "email": "automation@example.com"
        }
    }
    if sha:
        body["sha"] = sha
    resp = requests.put(url, headers=HDRS, json=body)
    return resp

def find_branch_case_insensitive(owner:str, repo:str, desired_names:List[str]) -> Optional[str]:
    """Return the actual branch name in the repo matching any desired_names (case-insensitive)."""
    # Use the branches API with pagination (just in case)
    page = 1
    desired_lower = [d.lower() for d in desired_names]
    while True:
        url = f"{API}/repos/{owner}/{repo}/branches?per_page=100&page={page}"
        r = gh_get(url)
        if r.status_code != 200:
            print(f"  ⚠️  Unable to list branches for {repo}: {r.status_code} {r.text}")
            return None
        items = r.json()
        if not items:
            break
        for b in items:
            name = b.get("name","")
            if name.lower() in desired_lower:
                return name
        page += 1
    return None

def get_existing_content_sha(owner:str, repo:str, path:str, branch:str) -> Tuple[Optional[str], Optional[str]]:
    """Return (sha, download_url) for existing file if present on given branch."""
    url = f"{API}/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    r = gh_get(url)
    if r.status_code == 200:
        j = r.json()
        return j.get("sha"), j.get("download_url")
    return None, None

def protect_branch(owner:str, repo:str, branch:str) -> bool:
    url = f"{API}/repos/{owner}/{repo}/branches/{branch}/protection"
    payload = {
        "required_status_checks": None,  # leave checks unmanaged by this script
        "enforce_admins": ENFORCE_ADMINS,
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": DISMISS_STALE_REVIEWS,
            "require_code_owner_reviews": True,              # <-- key for mandatory code owners
            "required_approving_review_count": REQUIRED_APPROVING_REVIEWS,
            "require_last_push_approval": False
        },
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_linear_history": False,
        "block_creations": False,
        "required_conversation_resolution": True
    }
    r = gh_put(url, json=payload)
    if r.status_code in (200, 201):
        print(f"  ✅ Branch protection set on {repo}:{branch}")
        return True
    else:
        print(f"  ❌ Failed to set protection on {repo}:{branch} -> {r.status_code} {r.text}")
        return False

def ensure_codeowners(owner:str, repo:str, branch:str, users:List[str]) -> bool:
    path = ".github/CODEOWNERS"   # recommended location
    content = (f"# Managed by automation\n"
               f"# All files require reviews from these Code Owners\n"
               f"* {' '.join(users)}\n")
    sha, existing_url = get_existing_content_sha(owner, repo, path, branch)
    if sha:
        resp = gh_put_contents(owner, repo, path, content.encode("utf-8"),
                               message="chore: update CODEOWNERS for mandatory reviewers",
                               branch=branch, sha=sha)
        if resp.status_code in (200, 201):
            print(f"  🔁 Updated CODEOWNERS on {repo}:{branch}")
            return True
        else:
            print(f"  ❌ Failed updating CODEOWNERS on {repo}:{branch} -> {resp.status_code} {resp.text}")
            return False
    else:
        # create new
        resp = gh_put_contents(owner, repo, path, content.encode("utf-8"),
                               message="chore: add CODEOWNERS for mandatory reviewers",
                               branch=branch)
        if resp.status_code in (200, 201):
            print(f"  🆕 Created CODEOWNERS on {repo}:{branch}")
            return True
        else:
            # If the branch is protected against direct pushes, you may need to open a PR.
            print(f"  ❌ Failed creating CODEOWNERS on {repo}:{branch} -> {resp.status_code} {resp.text}")
            return False

# -------------------- MAIN --------------------
def main():
    if not GITHUB_TOKEN or GITHUB_TOKEN == "REPLACE_WITH_YOUR_PAT":
        print("ERROR: Set GITHUB_TOKEN env var or edit the script to include your PAT.")
        sys.exit(1)

    for repo in REPOS:
        print(f"\n=== {ORG}/{repo} ===")
        branch = find_branch_case_insensitive(ORG, repo, BRANCH_CANDIDATES)
        if not branch:
            print("  ⚠️  Could not find Develop/develop/DEVELOP branch. Skipping.")
            continue

        # 1) Ensure CODEOWNERS exists/updated on the target branch
        ensure_codeowners(ORG, repo, branch, CODEOWNERS_USERS)

        # 2) Apply branch protection requiring Code Owner reviews
        protect_branch(ORG, repo, branch)

    print("\nDone.")

if __name__ == "__main__":
    main()
