import time
import logging
from typing import Dict, List
import requests
import jwt  # pip install pyjwt

# ---------------------------------------------------------
# >>>>>> EDIT THESE 4 LINES <<<<<<
USER_PAT = "ghp_your_PAT_here"  # user PAT (org admin)
APP_SLUG = "jh-teamcity-githubapp-1"  # choose from APPS below
ACTION = "add"  # "add" or "remove"
REPO_FULLNAME = "JHDevOps/githubapptestrepo"  # owner/repo
# If you don't know the installation id, set it to None and we will list for you.
INSTALLATION_ID = None
# ---------------------------------------------------------

BASE_URL = "https://api.github.com"

APPS: Dict[str, Dict[str, str]] = {
    "jh-teamcity-githubapp-1": {
        "id": 1032907,
        "private_key": """-----BEGIN RSA PRIVATE KEY-----
PASTE THE FULL PEM FOR APP-1 HERE
-----END RSA PRIVATE KEY-----""",
    },
    "jh-teamcity-githubapp-2": {
        "id": 1032914,
        "private_key": """-----BEGIN RSA PRIVATE KEY-----
PASTE THE FULL PEM FOR APP-2 HERE
-----END RSA PRIVATE KEY-----""",
    },
}

log = logging.getLogger("gh-app-repos")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

class GitHubError(Exception):
    pass

def gh_request(method: str, url: str, headers: Dict[str, str], **kwargs):
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
    payload = {"iat": now - 60, "exp": now + 600, "iss": app_id}
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

def add_repo_with_user_pat(pat: str, installation_id: int, repo_id: int):
    url = f"{BASE_URL}/user/installations/{installation_id}/repositories/{repo_id}"
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}
    resp = requests.put(url, headers=headers)
    if resp.status_code not in (201, 204):
        try: body = resp.json()
        except Exception: body = resp.text
        raise GitHubError(f"PUT {url} -> {resp.status_code}: {body}")

def remove_repo_with_user_pat(pat: str, installation_id: int, repo_id: int):
    url = f"{BASE_URL}/user/installations/{installation_id}/repositories/{repo_id}"
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}
    resp = requests.delete(url, headers=headers)
    if resp.status_code != 204:
        try: body = resp.json()
        except Exception: body = resp.text
        raise GitHubError(f"DELETE {url} -> {resp.status_code}: {body}")

def run():
    if APP_SLUG not in APPS:
        raise SystemExit(f"Unknown APP_SLUG '{APP_SLUG}'. Choose one of: {list(APPS.keys())}")
    if ACTION not in ("add", "remove"):
        raise SystemExit("ACTION must be 'add' or 'remove'")
    if not USER_PAT or USER_PAT.startswith("ghp_your_PAT_here"):
        raise SystemExit("Set USER_PAT at the top (needs to be an org admin PAT).")
    if "/" not in REPO_FULLNAME:
        raise SystemExit("REPO_FULLNAME must be owner/repo")

    cfg = APPS[APP_SLUG]
    app_id = cfg["id"]
    private_key = cfg["private_key"]

    # 1) Build JWT & verify app identity
    jwt_token = generate_jwt(app_id, private_key)
    app_info = get_app(jwt_token)
    log.info("Using app: %s (slug: %s, id: %s)", app_info["name"], app_info["slug"], app_info["id"])
    if app_info["id"] != app_id:
        raise SystemExit(f"App ID/private key mismatch. JWT says {app_info['id']} but config is {app_id}.")

    # 2) Get installations and optionally ask which one
    installs = get_installations(jwt_token)
    if not installs:
        raise SystemExit("This app has no installations.")

    if INSTALLATION_ID is None:
        log.info("Installations for this app:")
        for i in installs:
            log.info("  id=%s owner=%s", i["id"], i["account"]["login"])
        raise SystemExit("Set INSTALLATION_ID at the top after checking the list above.")
    else:
        ids = [i["id"] for i in installs]
        if INSTALLATION_ID not in ids:
            raise SystemExit(f"INSTALLATION_ID {INSTALLATION_ID} does not belong to this app.")
        owner = [i for i in installs if i["id"] == INSTALLATION_ID][0]["account"]["login"]
        log.info("Chosen installation %s on owner '%s'", INSTALLATION_ID, owner)

    # 3) Resolve repo id with PAT
    repo_id = repo_id_with_pat(USER_PAT, REPO_FULLNAME)
    log.info("Repo id for %s is %s", REPO_FULLNAME, repo_id)

    # 4) Add/remove using PAT on /user/installations/...
    log.info("%s %s to installation %s ...",
             "Adding" if ACTION == "add" else "Removing", REPO_FULLNAME, INSTALLATION_ID)
    if ACTION == "add":
        add_repo_with_user_pat(USER_PAT, INSTALLATION_ID, repo_id)
    else:
        remove_repo_with_user_pat(USER_PAT, INSTALLATION_ID, repo_id)

    log.info("Done.")

# Run it
run()
