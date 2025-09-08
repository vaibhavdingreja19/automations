# 02_sample_api_env.py
# Samples GitHub API usage per GitHub App by polling /rate_limit for each installation.
# App IDs and RSA keys are read from environment variables: appid1, rsakey1, appid2, rsakey2, ...

import os, time, pathlib, logging, requests, jwt
from datetime import datetime, timezone, timedelta
import pandas as pd

# ---------- CONFIG ----------
ORG = "JHDevOps"

# How many apps you have
NUM_APPS = 7

# Sampling window: set POLL_MINUTES=0 for a quick snapshot (fast),
# or >0 (e.g., 10–30) to estimate real call volume more accurately.
POLL_MINUTES = 0
INTERVAL_SECONDS = 60
# ---------- END CONFIG ----------

GITHUB_API = "https://api.github.com"
DATA_DIR = pathlib.Path("./data"); DATA_DIR.mkdir(exist_ok=True)
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
    samples = []
    last_used_core, last_used_graphql = {}, {}

    def snap_once():
        ts = datetime.now(timezone.utc).isoformat()
        for app in APPS:
            slug = app["slug"]; app_id = int(app["app_id"]); pem = app["private_key_pem"]
            app_jwt = make_app_jwt(app_id, pem)

            installs = list_all_installations(app_jwt)
            if not installs:
                logging.info(f"[{slug}] no installations found."); continue

            for ins in installs:
                inst_id = ins.get("id")
                acct = ins.get("account") or {}
                if acct.get("login") != ORG:  # only keep repos in our org
                    continue
                try:
                    inst_token = create_installation_token(app_jwt, inst_id)
                    resources = get_rate_limit(inst_token)
                except Exception as e:
                    logging.warning(f"[{slug}] inst {inst_id} failed: {e}"); continue

                core, gql = resources.get("core", {}), resources.get("graphql", {})
                used_c, used_g = core.get("used"), gql.get("used")

                key = (slug, inst_id)
                d_core = d_gql = None
                if isinstance(used_c, int):
                    prev = last_used_core.get(key)
                    d_core = used_c if prev is None or used_c < prev else used_c - prev
                    last_used_core[key] = used_c
                if isinstance(used_g, int):
                    prev = last_used_graphql.get(key)
                    d_gql = used_g if prev is None or used_g < prev else used_g - prev
                    last_used_graphql[key] = used_g

                samples.append({
                    "timestamp": ts,
                    "app_slug": slug,
                    "installation_id": inst_id,
                    "core_used": used_c,
                    "graphql_used": used_g,
                    "delta_core": d_core,
                    "delta_graphql": d_gql
                })

    if POLL_MINUTES > 0:
        logging.info(f"Sampling ~{POLL_MINUTES} minutes (every {INTERVAL_SECONDS}s)…")
        end = datetime.now(timezone.utc) + timedelta(minutes=POLL_MINUTES)
        while datetime.now(timezone.utc) < end:
            try: snap_once()
            except Exception as e: logging.warning(f"sample error: {e}")
            time.sleep(INTERVAL_SECONDS)
        logging.info("Sampling finished.")
    else:
        logging.info("Single snapshot mode (POLL_MINUTES=0).")
        snap_once()

    samples_df = pd.DataFrame(samples)
    samples_df.to_csv(DATA_DIR / "api_usage_samples.csv", index=False)

    def safe_sum(s): return pd.to_numeric(s, errors="coerce").fillna(0).sum()
    agg = samples_df.groupby(["app_slug","installation_id"], dropna=False).agg(
        api_core_calls=("delta_core", safe_sum),
        api_graphql_calls=("delta_graphql", safe_sum),
        last_core_used=("core_used", "max"),
        last_graphql_used=("graphql_used", "max"),
        samples=("timestamp", "count")
    ).reset_index()
    agg["api_calls_total"] = agg["api_core_calls"].fillna(0) + agg["api_graphql_calls"].fillna(0)
    agg.to_csv(DATA_DIR / "api_usage_by_app.csv", index=False)

    logging.info("Saved: data/api_usage_samples.csv and data/api_usage_by_app.csv")

if __name__ == "__main__":
    main()
