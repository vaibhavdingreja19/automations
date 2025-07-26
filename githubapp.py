
import os
import sys
import jwt
import time
import argparse
import requests
from typing import Dict, List, Tuple, Optional

BASE_URL = "https://api.github.com"

APP_IDS = ['1032222', '10322222']  
RSA_KEYS = ['rsakey1', 'rsakey2']  

REPO_LOOKUP_TOKEN = 'ghp_TboB'



class GitHubError(Exception):
    pass

def gh_request(method: str, url: str, headers: Dict[str, str], **kwargs):
    
    for attempt in range(5):
        resp = requests.request(method, url, headers=headers, **kwargs)
        # Handle secondary / standard rate limits
        if resp.status_code == 429 or (resp.status_code == 403 and 'rate limit' in resp.text.lower()):
            reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 5))
            sleep_for = max(1, reset - int(time.time())) + 1
            print(f"Rate limited. Sleeping {sleep_for}s...", file=sys.stderr)
            time.sleep(sleep_for)
            continue

        if 200 <= resp.status_code < 300:
            return resp

        
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        raise GitHubError(f"{method} {url} -> {resp.status_code}: {body}")
    raise GitHubError("Exceeded retry attempts due to rate limiting.")

def generate_jwt(app_id, private_key):
    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + (10 * 60),
        "iss": app_id,
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token

def get_app(jwt_token: str) -> Dict:
    url = f"{BASE_URL}/app"
    headers = {"Authorization": f"Bearer {jwt_token}",
               "Accept": "application/vnd.github+json"}
    return gh_request("GET", url, headers).json()

def get_installations(jwt_token):
    url = f"{BASE_URL}/app/installations"
    headers = {"Authorization": f"Bearer {jwt_token}", "Accept": "application/vnd.github+json"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def get_installation_token(installation_id, jwt_token):
    url = f"{BASE_URL}/app/installations/{installation_id}/access_tokens"
    headers = {"Authorization": f"Bearer {jwt_token}", "Accept": "application/vnd.github+json"}
    response = requests.post(url, headers=headers)
    response.raise_for_status()
    return response.json()["token"]

def resolve_repo_id(owner: str, repo: str) -> int:
    """
    Resolve repository ID using either:
      - GH_REPO_LOOKUP_TOKEN (recommended for private repos)
      - anonymous (for public repos)
    """
    url = f"{BASE_URL}/repos/{owner}/{repo}"
    headers = {"Accept": "application/vnd.github+json"}
    if REPO_LOOKUP_TOKEN:
        headers["Authorization"] = f"Bearer {REPO_LOOKUP_TOKEN}"

    try:
        resp = gh_request("GET", url, headers)
        return resp.json()["id"]
    except GitHubError as e:
        print(f"Failed to resolve repository id for {owner}/{repo}. "
              f"Provide GH_REPO_LOOKUP_TOKEN if this is a private repo.\n{e}", file=sys.stderr)
        raise

def add_repo_to_installation(installation_token: str, installation_id: int, repo_id: int) -> None:
    """
    Uses the installation access token to add a repository to the installation.
    Endpoint: PUT /user/installations/{installation_id}/repositories/{repository_id}
    """
    url = f"{BASE_URL}/app/installations/{installation_id}/repositories/{repo_id}"
    headers = {"Authorization": f"Bearer {installation_token}",
               "Accept": "application/vnd.github+json"}
    # GitHub returns 204 No Content on success
    resp = gh_request("PUT", url, headers)
    if resp.status_code not in (200, 201, 202, 204):
        raise GitHubError(f"Unexpected status code when adding repository: {resp.status_code}")

def list_installation_repos(installation_token: str) -> List[int]:
    """
    Returns list of repo IDs currently accessible by installation.
    """
    url = f"{BASE_URL}/installation/repositories"
    headers = {"Authorization": f"Bearer {installation_token}",
               "Accept": "application/vnd.github+json"}
    ids = []
    page = 1
    while True:
        resp = gh_request("GET", url, headers, params={"per_page": 100, "page": page})
        data = resp.json()
        repos = data.get("repositories", [])
        if not repos:
            break
        ids.extend([r["id"] for r in repos])
        page += 1
    return ids

def pick_app_by_slug_or_name(apps: List[Dict], wanted: str) -> Dict:
    wanted_lower = wanted.lower()
    for a in apps:
        if a["slug"].lower() == wanted_lower or a["name"].lower() == wanted_lower:
            return a
    raise ValueError(f"No app found with slug/name '{wanted}'.")

def find_installation_for_owner(installations: List[Dict], owner: str) -> Dict:
    owner_lower = owner.lower()
    for inst in installations:
        account = inst.get("account", {})
        if account.get("login", "").lower() == owner_lower:
            return inst
    raise ValueError(f"No installation found for owner '{owner}'. "
                     f"Is the app installed on that org/user?")



def main():
    parser = argparse.ArgumentParser(description="Add a specific repo to a specific GitHub App installation.")
    parser.add_argument("--app", help="GitHub App name or slug", required=False)
    parser.add_argument("--repo", help="Full repo name: owner/repo", required=False)
    args = parser.parse_args()

    if len(APP_IDS) != len(RSA_KEYS):
        print("APP_IDS and RSA_KEYS length mismatch.", file=sys.stderr)
        sys.exit(1)

    app_input = args.app or input("Enter GitHub App name/slug: ").strip()
    repo_full = args.repo or input("Enter repository full name (owner/repo): ").strip()

    if "/" not in repo_full:
        print("Repository must be in form owner/repo.", file=sys.stderr)
        sys.exit(1)
    owner, repo = repo_full.split("/", 1)

    # Build app catalog
    apps_meta = []
    for idx, (app_id, private_key) in enumerate(zip(APP_IDS, RSA_KEYS), start=1):
        if not app_id or not private_key:
            continue
        jwt_token = generate_jwt(app_id, private_key)
        app_info = get_app(jwt_token)
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
        print("No valid APP_IDS/RSA_KEYS found in environment.", file=sys.stderr)
        sys.exit(1)

    
    chosen = pick_app_by_slug_or_name(apps_meta, app_input)
    print(f"Selected app: {chosen['name']} (slug: {chosen['slug']}, id: {chosen['id']})")

    
    installations = get_installations(chosen["jwt"])
    installation = find_installation_for_owner(installations, owner)
    installation_id = installation["id"]
    print(f"Found installation {installation_id} on owner '{owner}'")

    
    repo_id = resolve_repo_id(owner, repo)
    print(f"Repository id for {owner}/{repo} is {repo_id}")

    
    installation_token = get_installation_token(installation_id, jwt_token)

    
    current_repo_ids = set(list_installation_repos(installation_token))
    if repo_id in current_repo_ids:
        print(f"Repo {owner}/{repo} is already accessible by this installation. Nothing to do.")
        return

    
    print(f"Adding {owner}/{repo} to installation {installation_id} ...")
    add_repo_to_installation(installation_token, installation_id, repo_id)

    
    current_repo_ids = set(list_installation_repos(installation_token))
    if repo_id in current_repo_ids:
        print(f"Successfully added {owner}/{repo} to the GitHub App installation.")
    else:
        print(f"Could not verify that the repository was added. Please check manually.")

if __name__ == "__main__":
    main()
