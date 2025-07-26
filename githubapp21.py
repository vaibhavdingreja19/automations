#!/usr/bin/env python3
import sys
import time
import jwt
import argparse
import requests
import logging
from typing import Dict, List

BASE_URL = "https://api.github.com"

# ---- Configure only TWO apps here ----
APP_IDS = ['1032222', '10322222']  # <- your two GitHub App IDs as strings
RSA_KEYS = [
    """-----BEGIN RSA PRIVATE KEY-----
rsakey1
-----END RSA PRIVATE KEY-----""",
    """-----BEGIN RSA PRIVATE KEY-----
rsakey2
-----END RSA PRIVATE KEY-----"""
]

# Optional PAT to resolve private repo IDs
REPO_LOOKUP_TOKEN = 'ghp_TboB'  # replace / or leave empty if public repos only

# ------------- Logging -------------

LOG = logging.getLogger("gh-add-repo")

def setup_logging(debug: bool):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

# ------------- Errors -------------

class GitHubError(Exception):
    pass

# ------------- HTTP helper -------------

def gh_request(method: str, url: str, headers: Dict[str, str], **kwargs) -> requests.Response:
    LOG.debug("HTTP %s %s headers=%s kwargs=%s", method, url, _redact_headers(headers), _shallow_kwargs(kwargs))
    for attempt in range(5):
        resp = requests.request(method, url, headers=headers, **kwargs)
        LOG.debug("-> %s %s (attempt %d) status=%d ratelimit-remaining=%s",
                  method, url, attempt + 1, resp.status_code, resp.headers.get("X-RateLimit-Remaining"))

        # Handle secondary / standard rate limits
        if resp.status_code == 429 or (resp.status_code == 403 and 'rate limit' in resp.text.lower()):
            reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 5))
            sleep_for = max(1, reset - int(time.time())) + 1
            LOG.warning("Rate limited. Sleeping %ss then retrying...", sleep_for)
            time.sleep(sleep_for)
            continue

        if 200 <= resp.status_code < 300:
            return resp

        # Not successful, raise with context
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        raise GitHubError(f"{method} {url} -> {resp.status_code}: {body}")

    raise GitHubError("Exceeded retry attempts due to rate limiting.")

def _redact_headers(h: Dict[str, str]) -> Dict[str, str]:
    redacted = dict(h)
    for k in list(redacted.keys()):
        if k.lower() in ("authorization",):
            redacted[k] = "***redacted***"
    return redacted

def _shallow_kwargs(kwargs):
    # Avoid dumping big bodies
    shallow = dict(kwargs)
    if "data" in shallow:
        shallow["data"] = "<data redacted>"
    if "json" in shallow:
        shallow["json"] = "<json redacted>"
    return shallow

# ------------- GitHub API wrappers -------------

def generate_jwt(app_id: str, private_key: str) -> str:
    payload = {
        "iat": int(time.time()) - 60,       # allow small clock skew
        "exp": int(time.time()) + (10 * 60),
        "iss": app_id,
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    LOG.debug("Generated JWT for app_id=%s (len=%d)", app_id, len(token))
    return token

def get_app(jwt_token: str) -> Dict:
    url = f"{BASE_URL}/app"
    headers = {"Authorization": f"Bearer {jwt_token}",
               "Accept": "application/vnd.github+json"}
    return gh_request("GET", url, headers).json()

def get_installations(jwt_token: str) -> List[Dict]:
    url = f"{BASE_URL}/app/installations"
    headers = {"Authorization": f"Bearer {jwt_token}",
               "Accept": "application/vnd.github+json"}
    installations = []
    page = 1
    while True:
        resp = gh_request("GET", url, headers, params={"per_page": 100, "page": page})
        chunk = resp.json()
        LOG.debug("Fetched %d installations on page %d", len(chunk), page)
        if not chunk:
            break
        installations.extend(chunk)
        page += 1
    return installations

def get_installation_token(installation_id: int, jwt_token: str) -> str:
    url = f"{BASE_URL}/app/installations/{installation_id}/access_tokens"
    headers = {"Authorization": f"Bearer {jwt_token}",
               "Accept": "application/vnd.github+json"}
    resp = gh_request("POST", url, headers)
    token = resp.json()["token"]
    LOG.debug("Got installation token for installation_id=%s (len=%d)", installation_id, len(token))
    return token

def resolve_repo_id(owner: str, repo: str) -> int:
    url = f"{BASE_URL}/repos/{owner}/{repo}"
    headers = {"Accept": "application/vnd.github+json"}
    if REPO_LOOKUP_TOKEN:
        headers["Authorization"] = f"token {REPO_LOOKUP_TOKEN}"

    try:
        resp = gh_request("GET", url, headers)
        repo_id = resp.json()["id"]
        LOG.debug("Resolved repo id: %s/%s -> %d", owner, repo, repo_id)
        return repo_id
    except GitHubError as e:
        LOG.error("Failed to resolve repository id for %s/%s. "
                  "Provide GH_REPO_LOOKUP_TOKEN if this is a private repo. Error: %s", owner, repo, e)
        raise

def add_repo_to_installation(installation_token: str, installation_id: int, repo_id: int) -> None:
    """
    Correct endpoint:
    PUT /user/installations/{installation_id}/repositories/{repository_id}
    """
    url = f"{BASE_URL}/user/installations/{installation_id}/repositories/{repo_id}"
    headers = {"Authorization": f"Bearer {installation_token}",
               "Accept": "application/vnd.github+json"}
    resp = gh_request("PUT", url, headers)
    LOG.debug("Add repo response status=%d", resp.status_code)
    if resp.status_code not in (200, 201, 202, 204):
        raise GitHubError(f"Unexpected status code when adding repository: {resp.status_code}")

def list_installation_repos(installation_token: str) -> List[int]:
    url = f"{BASE_URL}/installation/repositories"
    headers = {"Authorization": f"Bearer {installation_token}",
               "Accept": "application/vnd.github+json"}
    ids = []
    page = 1
    while True:
        resp = gh_request("GET", url, headers, params={"per_page": 100, "page": page})
        data = resp.json()
        repos = data.get("repositories", [])
        LOG.debug("Fetched %d repos from installation (page %d)", len(repos), page)
        if not repos:
            break
        ids.extend([r["id"] for r in repos])
        page += 1
    return ids

def pick_app_by_slug_or_name(apps: List[Dict], wanted: str) -> Dict:
    wanted_lower = wanted.lower()
    for a in apps:
        if a.get("slug", "").lower() == wanted_lower or a.get("name", "").lower() == wanted_lower:
            return a
    raise ValueError(f"No app found with slug/name '{wanted}'.")

def find_installation_for_owner(installations: List[Dict], owner: str) -> Dict:
    owner_lower = owner.lower()
    for inst in installations:
        account = inst.get("account", {})
        if account.get("login", "").lower() == owner_lower:
            return inst
    raise ValueError(f"No installation found for owner '{owner}'. Is the app installed on that org/user?")

# ------------- Main -------------

def main():
    parser = argparse.ArgumentParser(description="Add a specific repo to a specific GitHub App installation.")
    parser.add_argument("--app", help="GitHub App name or slug", required=False)
    parser.add_argument("--repo", help="Full repo name: owner/repo", required=False)
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    setup_logging(args.debug)

    if len(APP_IDS) != len(RSA_KEYS):
        LOG.critical("APP_IDS and RSA_KEYS length mismatch.")
        sys.exit(1)

    app_input = args.app or input("Enter GitHub App name/slug: ").strip()
    repo_full = args.repo or input("Enter repository full name (owner/repo): ").strip()

    if "/" not in repo_full:
        LOG.critical("Repository must be in form owner/repo.")
        sys.exit(1)
    owner, repo = repo_full.split("/", 1)

    # Build app catalog
    apps_meta = []
    for idx, (app_id, private_key) in enumerate(zip(APP_IDS, RSA_KEYS), start=1):
        if not app_id or not private_key:
            LOG.warning("Skipping index %d due to empty app_id/private_key", idx)
            continue
        LOG.debug("Building JWT for app #%d id=%s", idx, app_id)
        jwt_token = generate_jwt(app_id, private_key)
        app_info = get_app(jwt_token)
        LOG.debug("App #%d: slug=%s, name=%s, id=%s", idx, app_info.get("slug"), app_info.get("name"), app_info.get("id"))
        apps_meta.append({
            "idx": idx,
            "app_id": app_id,
            "private_key": private_key,
            "jwt": jwt_token,
            "slug": app_info.get("slug"),
            "name": app_info.get("name"),
            "id": app_info.get("id"),
        })

    if not apps_meta:
        LOG.critical("No valid APP_IDS/RSA_KEYS provided.")
        sys.exit(1)

    # Pick the app
    chosen = pick_app_by_slug_or_name(apps_meta, app_input)
    LOG.info("Selected app: %s (slug: %s, id: %s)", chosen['name'], chosen['slug'], chosen['id'])

    # Installations for chosen app
    installations = get_installations(chosen["jwt"])
    LOG.debug("Total installations for chosen app: %d", len(installations))
    installation = find_installation_for_owner(installations, owner)
    installation_id = installation["id"]
    LOG.info("Found installation %s on owner '%s'", installation_id, owner)

    # Resolve repo id
    repo_id = resolve_repo_id(owner, repo)
    LOG.info("Repository id for %s/%s is %d", owner, repo, repo_id)

    # Installation token
    installation_token = get_installation_token(installation_id, chosen["jwt"])

    # Already there?
    current_repo_ids = set(list_installation_repos(installation_token))
    if repo_id in current_repo_ids:
        LOG.info("Repo %s/%s is already accessible by this installation. Nothing to do.", owner, repo)
        return

    # Add
    LOG.info("Adding %s/%s to installation %s ...", owner, repo, installation_id)
    add_repo_to_installation(installation_token, installation_id, repo_id)

    # Verify
    current_repo_ids = set(list_installation_repos(installation_token))
    if repo_id in current_repo_ids:
        LOG.info("✅ Successfully added %s/%s to the GitHub App installation.", owner, repo)
    else:
        LOG.warning("⚠️ Could not verify that the repository was added. Please check manually.")

if __name__ == "__main__":
    try:
        main()
    except (GitHubError, ValueError) as e:
        LOG = logging.getLogger("gh-add-repo")  # in case logging not yet configured
        logging.basicConfig(level=logging.ERROR, format="%(asctime)s [%(levelname)s] %(message)s")
        LOG.error("Fatal error: %s", e)
        sys.exit(1)
