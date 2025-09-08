# 02_sample_api_env_append.py
# Collect GitHub App API usage and append to one growing CSV log.
# Run this script every hour (cron, Task Scheduler, etc).
# App IDs and RSA keys are read from env vars: appid1, rsakey1, appid2, rsakey2, ...

import os, time, pathlib, logging, requests, jwt
from datetime import datetime, timezone
import pandas as pd

# ---------- CONFIG ----------
ORG = "JHDevOps"
NUM_APPS = 7  # how many appid/rsakey pairs to read
DATA_DIR = pathlib.Path("./data"); DATA_DIR.mkdir(exist_ok=True)
SAMPLES_FILE = DATA_DIR / "api_usage_samples.csv"
# ---------- END CONFIG ----------

GITHUB_API = "https://api.github.com"
logging.basicConfig(level=logging.INFO, format="%(message)s")

# Build APPS list from env vars
APPS = []
for i in range(1, NUM_APPS+1):
    app_id = os.getenv(f"appid{i}")
    rsakey = os.getenv(f"rsakey{i}")
    if not app_id or not rsakey:
        logging.warning(f"appid{i}/rsakey{i} not found in env; skipping.")
        continue
    APPS.append({
        "slug": f"app-{i}",
        "app_id": int(app_id),
        "private_key_pem": rsakey
    })

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
    headers = {"Authorization": f"Bearer {app_jwt_token}", "Accept": "application/vnd.github+json"}
    url = f"{GITHUB_API}/app/installations"
    out = []
    while url:
        r = req("GET", url, headers)
        data = r.json()
        installs = data if isinstance(data, list) else data.get("installations", data)
        if isinstance(installs, list):
            out.extend(installs)
        url = r.links.get("next", {}).get("url")
    return out

def create_installation_token(app_jwt_token: str, installation_id: int) -> str:
    headers = {"Authorization": f"Bearer {app_jwt_token}", "Accept": "application/vnd.github+json"}
    url = f"{GITHUB_API}/app/installations/{installation_id}/access_tokens"
    return req("POST", url, headers).json()["token"]

def get_rate_limit(inst_token: str):
    headers = {"Authorization": f"token {inst_token}", "Accept": "application/vnd.github+json"}
    return req("GET", f"{GITHUB_API}/rate_limit", headers).json().get("resources", {})

def main():
    ts = datetime.now(timezone.utc).isoformat()
    rows = []

    for app in APPS:
        slug = app["slug"]; app_id = app["app_id"]; pem = app["private_key_pem"]
        try:
            app_jwt = make_app_jwt(app_id, pem)
            installs = list_all_installations(app_jwt)
        except Exception as e:
            logging.error(f"[{slug}] list installations failed: {e}")
            continue

        for ins in installs:
            inst_id = ins.get("id")
            acct = (ins.get("account") or {}).get("login")
            if acct != ORG:  # only our org
                continue
            try:
                inst_token = create_installation_token(app_jwt, inst_id)
                resources = get_rate_limit(inst_token)
            except Exception as e:
                logging.warning(f"[{slug}] inst {inst_id} failed: {e}")
                continue

            core, gql = resources.get("core", {}), resources.get("graphql", {})
            rows.append({
                "timestamp": ts,
                "app_slug": slug,
                "installation_id": inst_id,
                "core_limit": core.get("limit"),
                "core_used": core.get("used"),
                "core_remaining": core.get("remaining"),
                "graphql_limit": gql.get("limit"),
                "graphql_used": gql.get("used"),
                "graphql_remaining": gql.get("remaining")
            })

    if not rows:
        logging.info("No rows collected.")
        return

    new_df = pd.DataFrame(rows)

    if SAMPLES_FILE.exists():
        old_df = pd.read_csv(SAMPLES_FILE)
        out_df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        out_df = new_df

    out_df.to_csv(SAMPLES_FILE, index=False)
    logging.info(f"Appended {len(new_df)} rows. File now has {len(out_df)} total rows → {SAMPLES_FILE}")

if __name__ == "__main__":
    main()
