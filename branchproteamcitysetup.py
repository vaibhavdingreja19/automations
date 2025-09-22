
import base64
import os
import sys
from typing import Optional, Tuple, List
import requests


def getenv_required(name: str) -> str:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        print(f"ERROR: Missing required environment variable: {name}")
        sys.exit(1)
    return val.strip()

def getenv_default(name: str, default: str) -> str:
    val = os.getenv(name)
    return default if val is None or val.strip() == "" else val.strip()

def getenv_int(name: str) -> int:
    raw = getenv_required(name)
    try:
        return int(raw.strip())
    except ValueError:
        print(f"ERROR: Env var {name} must be an integer; got '{raw}'")
        sys.exit(1)

GITHUB_TOKEN = getenv_required("GITHUB_TOKEN")
ORG = getenv_default("ORG", "JHDevOps")
NUM_REPOS = getenv_int("NUM_REPOS")
NUM_CODEOWNERS = getenv_int("NUM_CODEOWNERS")
REQUIRED_APPROVALS = getenv_int("REQUIRED_APPROVALS")


def normalize_owner(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    if not s.startswith("@"):
        return f"@{s}"
    return s

CODEOWNERS_USERS: List[str] = []
for i in range(1, NUM_CODEOWNERS + 1):
    v = getenv_required(f"CODEOWNER_{i}")
    norm = normalize_owner(v)
    if norm and norm not in CODEOWNERS_USERS:
        CODEOWNERS_USERS.append(norm)

if not CODEOWNERS_USERS:
    print("ERROR: No CODEOWNERS provided after normalization.")
    sys.exit(1)


API = "https://api.github.com"
HDRS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "Content-Type": "application/json",
}


def gh_get(url, **kwargs):
    return requests.get(url, headers=HDRS, **kwargs)

def gh_put(url, json=None, **kwargs):
    return requests.put(url, headers=HDRS, json=json, **kwargs)

def gh_put_contents(owner: str, repo: str, path: str, content_bytes: bytes, message: str, branch: str, sha: Optional[str] = None):
    url = f"{API}/repos/{owner}/{repo}/contents/{path}"
    body = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
        "branch": branch,
        "committer": {"name": "Automation Bot", "email": "automation@example.com"},
    }
    if sha:
        body["sha"] = sha
    return requests.put(url, headers=HDRS, json=body)


def list_branches(owner: str, repo: str) -> List[str]:
    branches = []
    page = 1
    while True:
        url = f"{API}/repos/{owner}/{repo}/branches?per_page=100&page={page}"
        r = gh_get(url)
        if r.status_code != 200:
            print(f"Unable to list branches for {repo}: {r.status_code} {r.text}")
            break
        items = r.json()
        if not items:
            break
        for b in items:
            if b.get("name"):
                branches.append(b["name"])
        page += 1
    return branches

def resolve_branch_case_insensitive(owner: str, repo: str, desired_name: str, cached_branches: Optional[List[str]] = None) -> Optional[str]:
    if cached_branches is None:
        cached_branches = list_branches(owner, repo)
    desired_lower = desired_name.strip().lower()
    for b in cached_branches:
        if b.lower() == desired_lower:
            return b
    return None

def get_existing_content_sha(owner: str, repo: str, path: str, branch: str) -> Tuple[Optional[str], Optional[str]]:
    url = f"{API}/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    r = gh_get(url)
    if r.status_code == 200:
        j = r.json()
        return j.get("sha"), j.get("download_url")
    return None, None

def ensure_codeowners(owner: str, repo: str, branch: str, users: List[str]) -> bool:
    path = ".github/CODEOWNERS"
    content = (f"# All files require reviews from these Code Owners\n"
               f"* {' '.join(users)}\n")
    sha, _ = get_existing_content_sha(owner, repo, path, branch)
    if sha:
        resp = gh_put_contents(owner, repo, path, content.encode("utf-8"),
                               message="chore: update CODEOWNERS",
                               branch=branch, sha=sha)
        if resp.status_code in (200, 201):
            print(f"Updated CODEOWNERS on {repo}:{branch}")
            return True
    else:
        resp = gh_put_contents(owner, repo, path, content.encode("utf-8"),
                               message="chore: add CODEOWNERS",
                               branch=branch)
        if resp.status_code in (200, 201):
            print(f"Created CODEOWNERS on {repo}:{branch}")
            return True
    print(f"Failed CODEOWNERS on {repo}:{branch} -> {resp.status_code} {resp.text}")
    return False

def protect_branch(owner: str, repo: str, branch: str) -> bool:
    url = f"{API}/repos/{owner}/{repo}/branches/{branch}/protection"
    payload = {
        "required_status_checks": None,
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
            "required_approving_review_count": REQUIRED_APPROVALS,
            "require_last_push_approval": False,
        },
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_linear_history": False,
        "block_creations": False,
        "required_conversation_resolution": True,
    }
    r = gh_put(url, json=payload)
    if r.status_code in (200, 201):
        print(f"Branch protection set on {repo}:{branch}")
        return True
    print(f"Failed protection on {repo}:{branch} -> {r.status_code} {r.text}")
    return False


def parse_repo_branches_from_env() -> List[Tuple[str, List[str]]]:
    out = []
    for i in range(1, NUM_REPOS + 1):
        repo = getenv_required(f"REPO_{i}")
        branches_csv = getenv_required(f"REPO_{i}_BRANCHES")
        branches = [b.strip() for b in branches_csv.split(",") if b.strip()]
        if not branches:
            print(f"ERROR: REPO_{i}_BRANCHES produced no valid branch names.")
            sys.exit(1)
        out.append((repo, branches))
    return out

def main():
    print(f"ORG={ORG}")
    print(f"NUM_REPOS={NUM_REPOS}")
    print(f"NUM_CODEOWNERS={NUM_CODEOWNERS}")
    print(f"REQUIRED_APPROVALS={REQUIRED_APPROVALS}")
    print(f"CODEOWNERS={', '.join(CODEOWNERS_USERS)}")

    repos_and_branches = parse_repo_branches_from_env()

    for repo, desired_branches in repos_and_branches:
        print(f"\n=== {ORG}/{repo} ===")
        branch_list = list_branches(ORG, repo)
        if not branch_list:
            print(f" No branches found for repo '{repo}'. Skipping.")
            continue

        for desired in desired_branches:
            actual_branch = resolve_branch_case_insensitive(ORG, repo, desired, cached_branches=branch_list)
            if not actual_branch:
                print(f" Branch '{desired}' not found in {repo}. Skipping.")
                continue

            ensure_codeowners(ORG, repo, actual_branch, CODEOWNERS_USERS)
            protect_branch(ORG, repo, actual_branch)

    print("\nDone.")

if __name__ == "__main__":
    main()
