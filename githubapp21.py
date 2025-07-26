#!/usr/bin/env python3
import os
import sys
import time
import argparse
import logging
from typing import Dict, List
import requests
import jwt  # PyJWT

BASE_URL = "https://api.github.com"

# ----------------------- CONFIG -----------------------
# Put your apps here. One place -> no index/key mismatches.
# Prefer loading the PEMs from files or env vars in real life.
APPS: Dict[str, Dict[str, str]] = {
    # slug: { "id": <app id>, "private_key": <PEM string or path> }
    "jh-teamcity-githubapp-1": {
        "id": 1032907,
        "private_key": os.environ.get("GH_APP1_PEM", "").replace("\\n", "\n"),
    },
    "jh-teamcity-githubapp-2": {
        "id": 1032914,
        "private_key": os.environ.get("GH_APP2_PEM", "").replace("\\n", "\n"),
    },
}
# ------------------------------------------------------

log = logging.getLogger("gh-app-repos")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

class GitHubError(Exception):
    pass

def die(msg: str, code: int = 1):
    log.error(msg)
    sys.exit(code)

def gh_request(method: str, url: str, headers: Dict[str, str], **kwargs):
    for attempt in range(5):
        resp = requests.request(method, url, headers=headers, **kwargs)
        if resp.status_code in (403, 429) and "rate limit" in resp.text.lower():
            reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            sleep_for = max(1, reset - int(time.time()) + 1)
            log.warning("Rate limited. Sleeping %s seconds...", sleep_for)
            time.sleep(sleep_for)
            continue
        if 200 <= resp.status_code < 300:
            return resp
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        raise GitHubError(f"{method} {url} -> {resp.status_code}: {body}")
    raise GitHubError("Exceeded retry attempts")

def generate_jwt(app_id: int, private_key_pem: str) -> str:
    if private_key_pem.strip().startswith("/") and os.path.exists(private_key_pem):
        with open(private_key_pem, "rb") as f:
            private_key_pem = f.read().decode()
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 10 * 60,
        "iss": app_id,
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")

def get_app(jwt_token: str) -> Dict:
    url = f"{BASE_URL}/app"
    headers = {"Authorization": f"Bearer {jwt_token}", "Accept": "application/vnd.github+json"}
    return gh_request("GET", url, headers).json()

def get_installations(jwt_token: str) -> List[Dict]:
    url = f"{BASE_URL}/app/installations"
    headers = {"Authorization": f"Bearer {jwt_token}", "Accept": "application/vnd.github+json"}
    return gh_request("GET", url, headers).json()

def repo_id_with_pat(pat: str, full_name: str) -> int:
    url = f"{BASE_URL}/repos/{full_name}"
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}
    return gh_request("GET", url, headers).json()["id"]

def add_repo_with_pat(pat: str, installation_id: int, repo_id: int):
    url = f"{BASE_URL}/user/installations/{installation_id}/repositories/{repo_id}"
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}
    resp = requests.put(url, headers=headers)
    if resp.status_code not in (201, 204):
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        raise GitHubError(f"PUT {url} -> {resp.status_code}: {body}")

def remove_repo_with_pat(pat: str, installation_id: int, repo_id: int):
    url = f"{BASE_URL}/user/installations/{installation_id}/repositories/{repo_id}"
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}
    resp = requests.delete(url, headers=headers)
    if resp.status_code not in (204,):
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        raise GitHubError(f"DELETE {url} -> {resp.status_code}: {body}")

def main():
    parser = argparse.ArgumentParser(
        description="Add/remove a repository to a GitHub App installation (selected repos mode)."
    )
    parser.add_argument("--app-slug", required=True, help="GitHub App slug key from APPS dict")
    parser.add_argument("--repo", required=True, help="Full repo name owner/repo")
    parser.add_argument("--installation-id", type=int, help="Installation id (if omitted, will list and ask)")
    parser.add_argument("--action", choices=["add", "remove"], default="add")
    parser.add_argument("--pat", default=os.getenv("GH_PAT"), help="User PAT with admin rights on the org/repo")
    args = parser.parse_args()

    if args.app_slug.lower() not in APPS:
        die(f"Unknown app slug '{args.app_slug}'. Known: {list(APPS.keys())}")

    if not args.pat:
        die("Provide a user PAT via --pat or GH_PAT env var (needs admin rights)")

    cfg = APPS[args.app_slug.lower()]
    app_id = cfg["id"]
    private_key = cfg["private_key"]
    if not private_key:
        die(f"No private key configured for app '{args.app_slug}'. Set GH_APP*_PEM env var or edit APPS dict.")

    # 1) Build JWT & verify which app we are
    jwt_token = generate_jwt(app_id, private_key)
    app_info = get_app(jwt_token)
    log.info("Selected app: %s (slug: %s, id: %s)", app_info["name"], app_info["slug"], app_info["id"])
    if app_info["id"] != app_id:
        die("App ID / private key mismatch (JWT says id %s, config says %s)" % (app_info["id"], app_id))

    # 2) List installations for THIS app
    installs = get_installations(jwt_token)
    if not installs:
        die("This app has no installations visible to it.")

    if args.installation_id:
        installation_id = args.installation_id
        if installation_id not in [i["id"] for i in installs]:
            die(f"Installation {installation_id} is not owned by app {app_info['slug']} ({app_info['id']}).")
        chosen_install = [i for i in installs if i["id"] == installation_id][0]
    else:
        # If exactly one, auto pick; else list and ask
        if len(installs) == 1:
            chosen_install = installs[0]
        else:
            log.info("Installations for this app:")
            for i in installs:
                log.info("  id=%s owner=%s", i["id"], i["account"]["login"])
            die("Specify which one with --installation-id")
        installation_id = chosen_install["id"]

    log.info("Found installation %s on owner '%s'", installation_id, chosen_install["account"]["login"])

    # 3) Resolve repo id using PAT
    repo_full = args.repo
    if "/" not in repo_full:
        die("Repo must be in form owner/repo")
    repo_id = repo_id_with_pat(args.pat, repo_full)
    log.info("Repository id for %s is %s", repo_full, repo_id)

    # 4) Add or remove using PAT against /user/installations/...
    log.info("%s %s to installation %s ...", "Adding" if args.action == "add" else "Removing", repo_full, installation_id)
    try:
        if args.action == "add":
            add_repo_with_pat(args.pat, installation_id, repo_id)
        else:
            remove_repo_with_pat(args.pat, installation_id, repo_id)
    except GitHubError as e:
        die(f"Fatal error: {e}")

    log.info("Done.")

if __name__ == "__main__":
    main()
