import time
import logging
from typing import Dict, List, Optional, Tuple
import requests
import jwt  
import os


USER_PAT = os.getenv('GITHUB_PAT') 
APP_SLUG = os.getenv('githubapp') 
ACTION = os.getenv('action')  
REPO_FULLNAME = os.getenv('repo_name') 


BASE_URL = "https://api.github.com"

APPS: Dict[str, Dict[str, str]] = {
    "jh-teamcity-githubapp-1": {
        "id": os.getenv('appid1'),
        "private_key": os.getenv('rsakey1'),
    },
    "jh-teamcity-githubapp-2": {
        "id": os.getenv('appid2'),
        "private_key": os.getenv('rsakey2'),
    },
    "jh-teamcity-githubapp-3": {
        "id": os.getenv('appid3'),
        "private_key": os.getenv('rsakey3'),
    },
    "jh-teamcity-githubapp-4": {
        "id": os.getenv('appid4'),
        "private_key": os.getenv('rsakey4'),
    },
    "jh-teamcity-githubapp-5": {
        "id": os.getenv('appid5'),
        "private_key": os.getenv('rsakey5'),
    },
    "jh-teamcity-githubapp-6": {
        "id": os.getenv('appid6'),
        "private_key": os.getenv('rsakey6'),
    },
    "jh-teamcity-githubapp-7": {
        "id": os.getenv('appid7'),
        "private_key": os.getenv('rsakey7'),
    },
    "jh-teamcity-githubapp-8": {
        "id": os.getenv('appid8'),
        "private_key": os.getenv('rsakey8'),
    },
    
    
}


READ_TEAM_SLUG = "jh_devops_pipeline_team_acl"

log = logging.getLogger("gh-app-repos")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")

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

def get_installation_token(jwt_token: str, installation_id: int) -> str:
    url = f"{BASE_URL}/app/installations/{installation_id}/access_tokens"
    headers = {"Authorization": f"Bearer {jwt_token}", "Accept": "application/vnd.github+json"}
    r = gh_request("POST", url, headers)
    return r.json()["token"]

def installation_has_repo_with_inst_token(inst_token: str, repo_id: int) -> bool:
    headers = {"Authorization": f"Bearer {inst_token}", "Accept": "application/vnd.github+json"}
    page = 1
    while True:
        url = f"{BASE_URL}/installation/repositories?per_page=100&page={page}"
        resp = gh_request("GET", url, headers)
        data = resp.json()
        for repo in data.get("repositories", []):
            if repo.get("id") == repo_id:
                return True
        if "next" not in resp.links:
            break
        page += 1
    return False

def installation_has_repo(jwt_token: str, installation_id: int, repo_id: int) -> bool:
    inst_token = get_installation_token(jwt_token, installation_id)
    return installation_has_repo_with_inst_token(inst_token, repo_id)

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

def pick_installation(installs: List[Dict], repo_owner: str) -> int:
    if len(installs) == 1:
        inst = installs[0]
        log.info("Single installation found: %s (owner=%s)", inst["id"], inst["account"]["login"])
        return inst["id"]

    matches = [i for i in installs if i["account"]["login"].lower() == repo_owner.lower()]
    if len(matches) == 1:
        inst = matches[0]
        log.info("Matched installation by owner '%s': %s", repo_owner, inst["id"])
        return inst["id"]

    log.error("Could not auto-pick installation. Installations for this app:")
    for i in installs:
        log.error("  id=%s owner=%s", i["id"], i["account"]["login"])
    raise SystemExit("Disambiguation needed: multiple installations and none/too many match repo owner.")

def find_repo_in_any_app(repo_id: int) -> Optional[Tuple[str, int]]:
    
    for slug, cfg in APPS.items():
        try:
            jwt_token = generate_jwt(cfg["id"], cfg["private_key"])
            
            _ = get_app(jwt_token)
            installs = get_installations(jwt_token)
            for inst in installs:
                inst_id = inst["id"]
                if installation_has_repo(jwt_token, inst_id, repo_id):
                    return slug, inst_id
        except Exception as e:
            
            log.debug("Skipping app %s during global check: %s", slug, e)
            continue
    return None


def grant_team_repo_access_read(pat: str, org: str, repo: str, team_slug: str):
   
    url = f"{BASE_URL}/orgs/{org}/teams/{team_slug}/repos/{org}/{repo}"
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}
    payload = {"permission": "pull"}  # READ
    resp = requests.put(url, headers=headers, json=payload)
    if resp.status_code not in (201, 204):
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        raise GitHubError(f"PUT {url} -> {resp.status_code}: {body}")
    log.info("Granted READ access to team '%s' on %s/%s", team_slug, org, repo)


def run():
    if APP_SLUG not in APPS:
        raise SystemExit(f"Unknown APP_SLUG '{APP_SLUG}'. Choose one of: {list(APPS.keys())}")
    if ACTION not in ("add", "remove"):
        raise SystemExit("ACTION must be 'add' or 'remove'")
    if not USER_PAT or USER_PAT.startswith("ghp_your_PAT_here"):
        raise SystemExit("Set USER_PAT at the top (needs to be an org admin PAT).")
    if "/" not in REPO_FULLNAME:
        raise SystemExit("REPO_FULLNAME must be owner/repo")

    repo_owner, _ = REPO_FULLNAME.split("/", 1)

    
    repo_id = repo_id_with_pat(USER_PAT, REPO_FULLNAME)
    log.info("Repo id for %s is %s", REPO_FULLNAME, repo_id)

    
    found = find_repo_in_any_app(repo_id)
    if ACTION == "add" and found:
        slug, inst_id = found
        log.info("Repo %s is already part of app '%s' (installation %s). Skipping.",
                 REPO_FULLNAME, slug, inst_id)
        return

    
    cfg = APPS[APP_SLUG]
    app_id = cfg["id"]
    private_key = cfg["private_key"]

    jwt_token = generate_jwt(app_id, private_key)
    app_info = get_app(jwt_token)
    log.info("Using app: %s (slug: %s, id: %s)", app_info["name"], app_info["slug"], app_info["id"])
    if int(app_info["id"]) != int(app_id):
        raise SystemExit(f"App ID/private key mismatch. JWT says {app_info['id']} but config is {app_id}.")

    installs = get_installations(jwt_token)
    if not installs:
        raise SystemExit("This app has no installations.")
    installation_id = pick_installation(installs, repo_owner)
    owner = [i for i in installs if i["id"] == installation_id][0]["account"]["login"]
    log.info("Chosen installation %s on owner '%s'", installation_id, owner)

    
    is_member = installation_has_repo(jwt_token, installation_id, repo_id)
    if ACTION == "add" and is_member:
        log.info("Repo %s is already part of this app installation %s. Skipping.", REPO_FULLNAME, installation_id)
        return
    if ACTION == "remove" and not is_member:
        log.info("Repo %s is NOT part of this app installation %s (will attempt remove anyway).",
                 REPO_FULLNAME, installation_id)

    log.info("%s %s to installation %s ...",
             "Adding" if ACTION == "add" else "Removing", REPO_FULLNAME, installation_id)
    if ACTION == "add":
        add_repo_with_user_pat(USER_PAT, installation_id, repo_id)
        # NEW (single added line): grant team READ access after a successful add
        grant_team_repo_access_read(USER_PAT, repo_owner, REPO_FULLNAME.split("/", 1)[1], READ_TEAM_SLUG)
    else:
        remove_repo_with_user_pat(USER_PAT, installation_id, repo_id)

    log.info("Done.")


run()
