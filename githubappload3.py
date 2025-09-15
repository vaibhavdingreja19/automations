# 02_sample_api_env_append_overwrite.py
# Collect GitHub App API usage and update a CSV that keeps one row per app+installation.
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
        r = req("GET", url, headers=headers)
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
                "last_timestamp": ts,                # last seen timestamp
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

    new_df = pd.DataFrame(rows).astype({
        "app_slug": "string",
        "installation_id": "int64"
    })

    # If file exists, load and update rather than append.
    if SAMPLES_FILE.exists():
        old_df = pd.read_csv(SAMPLES_FILE, dtype={"app_slug": "string", "installation_id": "int64"})
        # Ensure required columns exist in old_df
        if "count" not in old_df.columns:
            old_df["count"] = 1  # fallback: treat existing rows as seen once before
        if "last_timestamp" not in old_df.columns:
            old_df["last_timestamp"] = ""

        # Set multi-index for quick lookups
        old_df.set_index(["app_slug", "installation_id"], inplace=True)
        new_df.set_index(["app_slug", "installation_id"], inplace=True)

        # For each incoming row, update or create:
        for idx, new_row in new_df.iterrows():
            if idx in old_df.index:
                # increment count, replace limit/used/remaining and last_timestamp
                old_df.at[idx, "core_limit"] = new_row["core_limit"]
                old_df.at[idx, "core_used"] = new_row["core_used"]
                old_df.at[idx, "core_remaining"] = new_row["core_remaining"]
                old_df.at[idx, "graphql_limit"] = new_row["graphql_limit"]
                old_df.at[idx, "graphql_used"] = new_row["graphql_used"]
                old_df.at[idx, "graphql_remaining"] = new_row["graphql_remaining"]
                old_df.at[idx, "last_timestamp"] = new_row["last_timestamp"]
                # safe increment (handle NaN)
                try:
                    old_df.at[idx, "count"] = int(old_df.at[idx, "count"]) + 1
                except Exception:
                    old_df.at[idx, "count"] = 1
            else:
                # insert new row with count = 1
                insert = new_row.to_dict()
                insert["count"] = 1
                old_df.loc[idx] = insert

        # Reset index and write full table (overwrite)
        out_df = old_df.reset_index()
    else:
        # New file — set count = 1 for all
        new_df = new_df.reset_index()
        new_df["count"] = 1
        new_df = new_df.rename(columns={"last_timestamp": "last_timestamp"})
        out_df = new_df

    # Write (overwrite) the CSV
    out_df.to_csv(SAMPLES_FILE, index=False)
    logging.info(f"Updated/created {len(rows)} rows. File now has {len(out_df)} total rows → {SAMPLES_FILE}")

if __name__ == "__main__":
    main()
