#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import time
import argparse
import logging
from typing import Dict, List
import requests
import jwt  # pip install pyjwt

BASE_URL = "https://api.github.com"

###############################################################################
#                     >>>>>>  EDIT THESE CONSTANTS  <<<<<<
###############################################################################

# Your **user** Personal Access Token (admin on the org). Needs repo/admin:org scope good enough
# to add repos to the app installation.
USER_PAT = "ghp_yourPAT_here"

# Define ALL your apps here so you can't mix IDs & keys.
# Key = the app slug (as shown in GitHub UI)
APPS: Dict[str, Dict[str, str]] = {
    "jh-teamcity-githubapp-1": {
        "id": 1032907,
        "private_key": """-----BEGIN RSA PRIVATE KEY-----
PASTE THE FULL PEM HERE
-----END RSA PRIVATE KEY-----""",
    },
    "jh-teamcity-githubapp-2": {
        "id": 1032914,
        "private_key": """-----BEGIN RSA PRIVATE KEY-----
PASTE THE FULL PEM HERE
-----END RSA PRIVATE KEY-----""",
    },
}

###############################################################################

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

def gh_request(method: str, url: str, headers: Dict[str, str], **kwargs) -> requests.Response:
    """Thin wrapper with one-shot error surfacing (you can add retries if you want)."""
    resp = requests.request(method, url, headers=headers, **kwargs)
    if 200 <= resp.status_code < 300:
        return resp
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    raise GitHubError(f"{method} {url} -> {resp.status_code}: {body}")

def generate_jwt(app_id: int, private_key_pem: str) -> str:
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 10 * 60,
        "iss": app_id,
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")

def get_app(jwt_token: str) -> Dict:
    url = f"{BASE_URL}/app"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
    }
    return gh_request("GET", url, headers).json()

def get_installations(jwt_token: str) -> List[Dict]:
    url = f"{BASE_URL}/app/installations"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
    }
    return gh_request("GET", url, headers).json()

def repo_id_with_pat(pat: str, full_name: str) -> int:
    url = f"{BASE_URL}/repos/{full_name}"
    headers = {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github+json",
    }
    return gh_request("GET", url, headers).json()["id"]

def add_repo_with_user_pat(pat: str, installation_id: int, repo_id: int):
    url = f"{BASE_URL}/user/installations/{installation_id}/repositories/{repo_id}"
    headers = {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github+json",
    }
    resp = requests.put(url, headers=headers)
    if resp.status_code not in (201, 204):
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        raise GitHubError(f"PUT {url} -> {resp.status_code}: {body}")

def remove_repo_with_user_pat(pat: str, installation_id: int, repo_id: int):
    url = f"{BASE_URL}/user/installations/{installation_id}/repositories/{repo_id}"
    headers = {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github+json",
    }
    resp = requests.delete(url, headers=headers)
    if resp.status_code not in (204,):
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        raise GitHubError(f"DELETE {url} -> {resp.status_code}: {body}")

def list_installations_for_app(app_slug: str):
    cfg = APPS[app_slug]
    jwt_token = generate_jwt(cfg["id"], cfg["private_key"])
    app_info = get_app(jwt_token)
    log.info("App verified: %s (slug: %s, id: %s)", app_info["name"], app_info["slug"], app_info["id"])
    installs = get_installations(jwt_token)
    if not installs:
        log.info("No installations for this app.")
        return
    log.info("Installations:")
    for inst in installs:
        log.info("  id=%s owner=%s", inst["id"], inst["account"]["login"])

def main():
    parser = argparse.ArgumentParser(
        description="Add/remove a repository to a GitHub App installation (selected repos mode)."
    )
    parser.add_argument("--app-slug", required=True, help="One of: %s" % ", ".join(APPS.keys()))
    parser.add_argument("--repo", help="Repo full name owner/repo (required for add/remove)")
    parser.add_argument("--installation-id", type=int, help="Installation id (required for add/remove)")
    parser.add_argument("--action", choices=["add", "remove", "list-installations"], required=True)
    args = parser.parse_args()

    if args.app_slug not in APPS:
        die(f"Unknown app slug '{args.app_slug}'. Known: {list(APPS.keys())}")

    cfg = APPS[args.app_slug]
    app_id = cfg["id"]
    private_key = cfg["private_key"]

    if args.action == "list-installations":
        list_installations_for_app(args.app_slug)
        return

    # For add/remove we need these:
    if not USER_PAT or USER_PAT.startswith("ghp_yourPAT_here"):
        die("Set USER_PAT at the top of the file to a valid user PAT (admin on the org).")

    if not args.repo or "/" not in args.repo:
        die("--repo must be provided as owner/repo for add/remove")

    if not args.installation_id:
        die("--installation-id is required for add/remove. Use --action list-installations to see them.")

    # 1) Build JWT, verify app, and validate installation belongs to it
    jwt_token = generate_jwt(app_id, private_key)
    app_info = get_app(jwt_token)
    log.info("Selected app: %s (slug: %s, id: %s)", app_info["name"], app_info["slug"], app_info["id"])
    if app_info["id"] != app_id:
        die(f"App ID / private key mismatch. JWT says {app_info['id']}, config says {app_id}")

    installs = get_installations(jwt_token)
    install_ids = [i["id"] for i in installs]
    if args.installation_id not in install_ids:
        die(f"Installation {args.installation_id} is NOT owned by app {app_info['slug']} ({app_info['id']}).")

    owner = [i for i in installs if i["id"] == args.installation_id][0]["account"]["login"]
    log.info("Found installation %s on owner '%s'", args.installation_id, owner)

    # 2) Resolve repo id using PAT
    repo_id = repo_id_with_pat(USER_PAT, args.repo)
    log.info("Repository id for %s is %s", args.repo, repo_id)

    # 3) Add or remove using PAT on /user/installations/...
    log.info("%s %s to installation %s ...",
             "Adding" if args.action == "add" else "Removing",
             args.repo, args.installation_id)

    try:
        if args.action == "add":
            add_repo_with_user_pat(USER_PAT, args.installation_id, repo_id)
        else:
            remove_repo_with_user_pat(USER_PAT, args.installation_id, repo_id)
    except GitHubError as e:
        die(f"Fatal error: {e}")

    log.info("Done.")

if __name__ == "__main__":
    main()
