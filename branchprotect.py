#!/usr/bin/env python3
import json, requests

# ========= HARD-CODED CONFIG =========
TOKEN = "ghp_xxxxx..."                 # PAT with admin:repo_hook or repo admin rights
ORG   = "JHDevOps"

# Map repos -> list of branches to protect
REPO_BRANCHES = {
    "repo-one": ["develop", "release/1.0"],
    "repo-two": ["develop"],
    # "JHDigitalEngineering_c-iam-xyz": ["develop", "release/2.0"],
}

# Mandatory reviewers you named (also granted bypass)
BYPASS_USERS = ["gannara", "syedabd105", "mateuem", "scrivth"]

# Branch protection knobs
REQUIRED_APPROVALS = 1                 # change to 2+ if you want more approvals
ENFORCE_ADMINS     = False             # True = apply to admins too
REQUIRE_CONVO_RES  = True              # require all review threads resolved
# ====================================

API = "https://api.github.com"
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json"
}

def protect_branch(repo, branch):
    url = f"{API}/repos/{ORG}/{repo}/branches/{branch}/protection"
    payload = {
        # If you don't use status checks, keep this null
        "required_status_checks": None,

        "enforce_admins": ENFORCE_ADMINS,

        "required_pull_request_reviews": {
            "dismiss_stale_reviews": False,
            "require_code_owner_reviews": True,          # <-- Require review from CODEOWNERS
            "required_approving_review_count": REQUIRED_APPROVALS,
            # Allow specified actors to bypass PR requirements:
            "bypass_pull_request_allowances": {
                "users": BYPASS_USERS,                   # usernames
                "teams": [],                             # e.g., ["org/team-slug"]
                "apps":  []                              # e.g., ["github-actions"]
            }
        },

        # No push restrictions (set to object for allowlist)
        "restrictions": None,

        # Optional extras (keep as-is or tune)
        "required_linear_history": False,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_conversation_resolution": REQUIRE_CONVO_RES
    }

    r = requests.put(url, headers=HEADERS, data=json.dumps(payload), timeout=60)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"{repo}@{branch} -> {r.status_code} {r.text}")
    print(f"[OK] Protection set on {repo}@{branch}")

def main():
    for repo, branches in REPO_BRANCHES.items():
        for br in branches:
            try:
                protect_branch(repo, br)
            except Exception as e:
                print(f"[ERR] {repo}@{br}: {e}")

if __name__ == "__main__":
    main()
