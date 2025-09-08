# 01_repo_map_auto.py
# Maps repos in org 'JHDevOps' to each GitHub App by discovering installations automatically.
# Only needs: app_id + private_key_pem per app. No installation_id required.

import time, pathlib, logging, requests, jwt
import pandas as pd

# ---------- CONFIG: EDIT THIS ONLY ----------
ORG = "JHDevOps"

APPS = [
    {
        "slug": "app-1-slug",
        "app_id": 111111,
        "private_key_pem": """-----BEGIN RSA PRIVATE KEY-----
PASTE_APP_1_PEM_HERE
-----END RSA PRIVATE KEY-----"""
    },
    {
        "slug": "app-2-slug",
        "app_id": 222222,
        "private_key_pem": """-----BEGIN RSA PRIVATE KEY-----
PASTE_APP_2_PEM_HERE
-----END RSA PRIVATE KEY-----"""
    },
    {
        "slug": "app-3-slug",
        "app_id": 333333,
        "private_key_pem": """-----BEGIN RSA PRIVATE KEY-----
PASTE_APP_3_PEM_HERE
-----END RSA PRIVATE KEY-----"""
    },
    {
        "slug": "app-4-slug",
        "app_id": 444444,
        "private_key_pem": """-----BEGIN RSA PRIVATE KEY-----
PASTE_APP_4_PEM_HERE
-----END RSA PRIVATE KEY-----"""
    },
    {
        "slug": "app-5-slug",
        "app_id": 555555,
        "private_key_pem": """-----BEGIN RSA PRIVATE KEY-----
PASTE_APP_5_PEM_HERE
-----END RSA PRIVATE KEY-----"""
    },
    {
        "slug": "app-6-slug",
        "app_id": 666666,
        "private_key_pem": """-----BEGIN RSA PRIVATE KEY-----
PASTE_APP_6_PEM_HERE
-----END RSA PRIVATE KEY-----"""
    },
    {
        "slug": "app-7-slug",
        "app_id": 777777,
        "private_key_pem": """-----BEGIN RSA PRIVATE KEY-----
PASTE_APP_7_PEM_HERE
-----END RSA PRIVATE KEY-----"""
    }
]
# ---------- END CONFIG ----------

GITHUB_API = "https://api.github.com"
DATA_DIR = pathlib.Path("./data"); DATA_DIR.mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(message)s")

def make_app_jwt(app_id: int, private_key_pem: str) -> str:
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 540, "iss": int(app_id)}
    return jwt.encode(payload, private_key_pem, algorithm="RS256")

def req(method: str, url: str, headers: dict, **kw):
    r = requests.request(method, url, headers=headers, timeout=45, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {url} -> {r.status_code} {r.text[:300]}")
    return r

def list_all_installations(app_jwt_token: str):
    """Return list of installations for this App (handles both array and 'installations' keyed responses)."""
    headers = {"Authorization": f"Bearer {app_jwt_token}", "Accept": "application/vnd.github+json"}
    url = f"{GITHUB_API}/app/installations"
    out = []
    while url:
        r = req("GET", url, headers)
        data = r.json()
        installs = data if isinstance(data, list) else data.get("installations", data)  # support both shapes
        if isinstance(installs, list):
            out.extend(installs)
        url = r.links.get("next", {}).get("url")
    return out

def create_installation_token(app_jwt_token: str, installation_id: int) -> str:
    headers = {"Authorization": f"Bearer {app_jwt_token}", "Accept": "application/vnd.github+json"}
    url = f"{GITHUB_API}/app/installations/{installation_id}/access_tokens"
    return req("POST", url, headers).json()["token"]

def list_repos_for_installation(inst_token: str):
    headers = {"Authorization": f"token {inst_token}", "Accept": "application/vnd.github+json"}
    url = f"{GITHUB_API}/installation/repositories"
    repos = []
    while url:
        r = req("GET", url, headers)
        j = r.json()
        repos.extend(j.get("repositories", []))
        url = r.links.get("next", {}).get("url")
    return repos

def main():
    rows = []
    for app in APPS:
        slug = app["slug"]
        app_id = int(app["app_id"])
        pem = app["private_key_pem"]

        logging.info(f"[{slug}] Creating App JWT…")
        app_jwt = make_app_jwt(app_id, pem)

        logging.info(f"[{slug}] Listing installations for this App…")
        installs = list_all_installations(app_jwt)
        if not installs:
            logging.warning(f"[{slug}] No installations found (is the app installed anywhere?).")
            continue

        # Iterate every installation; collect only repos that belong to ORG
        total_repos_for_org = 0
        for ins in installs:
            inst_id = ins.get("id")
            acct = ins.get("account", {}) or {}
            target_login = acct.get("login")
            try:
                inst_token = create_installation_token(app_jwt, inst_id)
                repos = list_repos_for_installation(inst_token)
            except Exception as e:
                logging.warning(f"[{slug}] installation {inst_id} fetch failed: {e}")
                continue

            # Keep only repos owned by our org
            for r in repos:
                owner = (r.get("owner") or {}).get("login")
                if owner == ORG:
                    total_repos_for_org += 1
                    rows.append({
                        "repo_full_name": r.get("full_name"),
                        "repo_id": r.get("id"),
                        "private": r.get("private"),
                        "html_url": r.get("html_url"),
                        "app_slug": slug,
                        "app_id": app_id,
                        "installation_id": inst_id  # recorded for reference, but not required as input
                    })

        logging.info(f"[{slug}] repos in org '{ORG}': {total_repos_for_org}")

    df = pd.DataFrame(rows)
    out = DATA_DIR / "repo_app_map.csv"
    df.to_csv(out, index=False)
    logging.info(f"Saved: {out} ({len(df)} rows). Apps discovered in org: {df['app_slug'].nunique() if not df.empty else 0}")

if __name__ == "__main__":
    main()
