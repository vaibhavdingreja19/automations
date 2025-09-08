# 01_repo_map_hardcoded.py
# Maps org repos to the GitHub App (by installation) that owns them.
# Hardcode your 7 apps below (app_id, installation_id, private_key_pem).

import time, pathlib, logging, requests, jwt
import pandas as pd

# ---------- CONFIG: EDIT THIS ----------
ORG = "JHDevOps"

APPS = [
    {
        "slug": "app-1-slug",
        "app_id": 111111,
        "installation_id": 99999999,
        "private_key_pem": """-----BEGIN RSA PRIVATE KEY-----
PASTE_APP_1_PEM_HERE
-----END RSA PRIVATE KEY-----"""
    },
    {
        "slug": "app-2-slug",
        "app_id": 222222,
        "installation_id": 99999998,
        "private_key_pem": """-----BEGIN RSA PRIVATE KEY-----
PASTE_APP_2_PEM_HERE
-----END RSA PRIVATE KEY-----"""
    },
    {
        "slug": "app-3-slug",
        "app_id": 333333,
        "installation_id": 99999997,
        "private_key_pem": """-----BEGIN RSA PRIVATE KEY-----
PASTE_APP_3_PEM_HERE
-----END RSA PRIVATE KEY-----"""
    },
    {
        "slug": "app-4-slug",
        "app_id": 444444,
        "installation_id": 99999996,
        "private_key_pem": """-----BEGIN RSA PRIVATE KEY-----
PASTE_APP_4_PEM_HERE
-----END RSA PRIVATE KEY-----"""
    },
    {
        "slug": "app-5-slug",
        "app_id": 555555,
        "installation_id": 99999995,
        "private_key_pem": """-----BEGIN RSA PRIVATE KEY-----
PASTE_APP_5_PEM_HERE
-----END RSA PRIVATE KEY-----"""
    },
    {
        "slug": "app-6-slug",
        "app_id": 666666,
        "installation_id": 99999994,
        "private_key_pem": """-----BEGIN RSA PRIVATE KEY-----
PASTE_APP_6_PEM_HERE
-----END RSA PRIVATE KEY-----"""
    },
    {
        "slug": "app-7-slug",
        "app_id": 777777,
        "installation_id": 99999993,
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

def gh_get(url: str, headers: dict):
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"GET {url} -> {r.status_code} {r.text[:200]}")
    return r

def gh_post(url: str, headers: dict):
    r = requests.post(url, headers=headers, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"POST {url} -> {r.status_code} {r.text[:200]}")
    return r

def get_installation_token(app_jwt_token: str, installation_id: int) -> str:
    url = f"{GITHUB_API}/app/installations/{installation_id}/access_tokens"
    hdr = {"Authorization": f"Bearer {app_jwt_token}", "Accept": "application/vnd.github+json"}
    return gh_post(url, hdr).json()["token"]

def list_installation_repos(inst_token: str):
    hdr = {"Authorization": f"token {inst_token}", "Accept":"application/vnd.github+json"}
    url = f"{GITHUB_API}/installation/repositories"
    out = []
    while url:
        r = gh_get(url, hdr)
        j = r.json()
        out += j.get("repositories", [])
        url = r.links.get("next", {}).get("url")
    return out

def main():
    rows = []
    for app in APPS:
        slug = app["slug"]
        app_id = int(app["app_id"])
        inst_id = int(app["installation_id"])
        pem = app["private_key_pem"]

        logging.info(f"[{slug}] installation={inst_id} → fetching repos…")
        app_jwt = make_app_jwt(app_id, pem)
        inst_token = get_installation_token(app_jwt, inst_id)
        repos = list_installation_repos(inst_token)
        logging.info(f"  found {len(repos)} repos")

        for r in repos:
            rows.append({
                "repo_full_name": r.get("full_name"),
                "repo_id": r.get("id"),
                "private": r.get("private"),
                "html_url": r.get("html_url"),
                "app_slug": slug,
                "app_id": app_id,
                "installation_id": inst_id
            })

    df = pd.DataFrame(rows)
    out = DATA_DIR / "repo_app_map.csv"
    df.to_csv(out, index=False)
    logging.info(f"Saved: {out} ({len(df)} rows) | apps found: {df['app_slug'].nunique() if not df.empty else 0}")

if __name__ == "__main__":
    main()
