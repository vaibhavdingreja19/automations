#!/usr/bin/env python3
import base64, json, requests

# ====== CONFIG (hard-code here) ======
TOKEN   = "ghp_xxxxxxx"          # your PAT with repo scope
ORG     = "JHDevOps"             # org name
REPO    = "your-repo-name"       # repo name
BRANCHES = ["develop", "release/1.0"]  # list of branches

REVIEWERS = ["@gannara", "@syedabd105", "@mateuem", "@scrivth"]
CODEOWNERS_PATH = ".github/CODEOWNERS"
# =====================================

API = "https://api.github.com"
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json"
}

def get_file(branch):
    url = f"{API}/repos/{ORG}/{REPO}/contents/{CODEOWNERS_PATH}"
    r = requests.get(url, headers=HEADERS, params={"ref": branch})
    if r.status_code == 200:
        return r.json()["sha"]
    elif r.status_code == 404:
        return None
    else:
        raise Exception(f"GET failed: {r.status_code} {r.text}")

def put_file(branch, sha=None):
    url = f"{API}/repos/{ORG}/{REPO}/contents/{CODEOWNERS_PATH}"
    content = "* " + " ".join(REVIEWERS) + "\n"
    data = {
        "message": f"Add/Update CODEOWNERS for {branch}",
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch
    }
    if sha:
        data["sha"] = sha
    r = requests.put(url, headers=HEADERS, data=json.dumps(data))
    if r.status_code not in (200,201):
        raise Exception(f"PUT failed: {r.status_code} {r.text}")
    print(f"[OK] CODEOWNERS updated on {branch}")

def main():
    for br in BRANCHES:
        sha = get_file(br)
        put_file(br, sha)

if __name__ == "__main__":
    main()
