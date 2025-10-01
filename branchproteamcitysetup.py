
import base64
import os
import re
import sys
from typing import Optional, Tuple, List, Dict
import requests

def getenv_required(name: str) -> str:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        print(f"ERROR: missing env var {name}")
        sys.exit(1)
    return v.strip()

def getenv_default(name: str, default: str) -> str:
    v = os.getenv(name)
    return default if v is None or v.strip() == "" else v.strip()

def getenv_int(name: str) -> int:
    raw = getenv_required(name)
    try:
        return int(raw.strip())
    except ValueError:
        print(f"ERROR: {name} must be integer, got '{raw}'")
        sys.exit(1)

def split_csv(s: str) -> List[str]:
    return [x.strip() for x in s.split(",") if x.strip()]

def normalize_owner(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    return s if s.startswith("@") else f"@{s}"

GITHUB_TOKEN = getenv_required("GITHUB_TOKEN")
ORG = getenv_default("ORG", "JHDevOps")
REQUIRED_APPROVALS = getenv_int("REQUIRED_APPROVALS")
REPOS = split_csv(getenv_required("REPOS"))
CODEOWNERS = [o for o in [normalize_owner(x) for x in split_csv(getenv_required("CODEOWNERS"))] if o]
seen = set()
CODEOWNERS = [x for x in CODEOWNERS if not (x.lower() in seen or seen.add(x.lower()))]
PAIR_TEXT = getenv_required("REPO_BRANCH_PAIRS")

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
            print(f"{repo}: cannot list branches {r.status_code} {r.text}")
            break
        items = r.json()
        if not items:
            break
        for b in items:
            n = b.get("name")
            if n:
                branches.append(n)
        page += 1
    return branches

def resolve_branch_case_insensitive(owner: str, repo: str, desired_name: str, cached_branches: Optional[List[str]] = None) -> Optional[str]:
    if cached_branches is None:
        cached_branches = list_branches(owner, repo)
    dl = desired_name.strip().lower()
    for b in cached_branches:
        if b.lower() == dl:
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
    content = "# Managed by automation\n# All files require reviews from these Code Owners\n* " + " ".join(users) + "\n"
    sha, _ = get_existing_content_sha(owner, repo, path, branch)
    if sha:
        resp = gh_put_contents(owner, repo, path, content.encode("utf-8"), "chore: update CODEOWNERS", branch, sha=sha)
        if resp.status_code in (200, 201):
            print(f"{repo}:{branch}: CODEOWNERS updated")
            return True
    else:
        resp = gh_put_contents(owner, repo, path, content.encode("utf-8"), "chore: add CODEOWNERS", branch)
        if resp.status_code in (200, 201):
            print(f"{repo}:{branch}: CODEOWNERS created")
            return True
    print(f"{repo}:{branch}: CODEOWNERS failed {resp.status_code} {resp.text}")
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
        print(f"{repo}:{branch}: protection set")
        return True
    print(f"{repo}:{branch}: protection failed {r.status_code} {r.text}")
    return False

def parse_pairs(text: str) -> List[Tuple[str,str]]:
    pairs = []
    for token in split_csv(text):
        m = re.fullmatch(r"\[(.+?)\]-\[(.+?)\]", token)
        if not m:
            print(f"pair parse error for token '{token}', expected format [repo]-[branch]")
            sys.exit(1)
        repo = m.group(1).strip()
        branch = m.group(2).strip()
        if not repo or not branch:
            print(f"pair contains empty repo or branch in token '{token}'")
            sys.exit(1)
        pairs.append((repo, branch))
    return pairs

def main():
    if not CODEOWNERS:
        print("ERROR: CODEOWNERS empty after normalization")
        sys.exit(1)
    repo_set = {r.strip().lower() for r in REPOS}
    pairs = parse_pairs(PAIR_TEXT)
    by_repo: Dict[str, List[str]] = {}
    for repo, br in pairs:
        key = repo.strip()
        by_repo.setdefault(key, []).append(br.strip())
    for repo, desired_branches in by_repo.items():
        if repo.lower() not in repo_set:
            print(f"{repo}: not listed in REPOS, skipping")
            continue
        print(f"{ORG}/{repo}")
        branch_list = list_branches(ORG, repo)
        if not branch_list:
            print(f"{repo}: no branches listed or access error")
            continue
        for desired in desired_branches:
            actual = resolve_branch_case_insensitive(ORG, repo, desired, branch_list)
            if not actual:
                print(f"{repo}: branch '{desired}' not found")
                continue
            ensure_codeowners(ORG, repo, actual, CODEOWNERS)
            protect_branch(ORG, repo, actual)
    print("Done.")

if __name__ == "__main__":
    main()


#!/bin/bash
set -e

echo "Installing Git LFS..."
GIT_LFS_VERSION=$(curl -s https://api.github.com/repos/git-lfs/git-lfs/releases/latest | grep tag_name | cut -d '"' -f 4)
curl -LO https://github.com/git-lfs/git-lfs/releases/download/${GIT_LFS_VERSION}/git-lfs-${GIT_LFS_VERSION#v}-linux-amd64.tar.gz
tar -xzf git-lfs-*-linux-amd64.tar.gz
sudo ./git-lfs-*/install.sh || ./git-lfs-*/install.sh
git lfs install
git lfs version
