

import os, time, pathlib, logging, requests, jwt
from datetime import datetime, timezone
import pandas as pd


ORG = "JHDevOps"
NUM_APPS = 7  # how many appid/rsakey pairs to read
DATA_DIR = pathlib.Path("./data"); DATA_DIR.mkdir(exist_ok=True)
SAMPLES_FILE = DATA_DIR / "api_usage_samples.csv"


GITHUB_API = "https://api.github.com"
logging.basicConfig(level=logging.INFO, format="%(message)s")


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

def safe_int(v, default=None):
    try:
        return int(v)
    except Exception:
        return default

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
                "installation_id": safe_int(inst_id, None),
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

    
    new_df["installation_id"] = pd.to_numeric(new_df["installation_id"], errors="coerce").astype("Int64")
    new_df["app_slug"] = new_df["app_slug"].astype("string")

    
    if SAMPLES_FILE.exists():
        try:
            old_df = pd.read_csv(SAMPLES_FILE, dtype={"app_slug": "string"})
        except Exception as e:
            logging.error(f"Failed to read existing samples file: {e}. Will recreate file.")
            old_df = pd.DataFrame()

        
        if old_df.empty:
            old_df = pd.DataFrame(columns=[
                "app_slug", "installation_id", "last_timestamp",
                "core_limit", "core_used", "core_remaining",
                "graphql_limit", "graphql_used", "graphql_remaining",
                "count"
            ])

        
        if "installation_id" in old_df.columns:
            old_df["installation_id"] = pd.to_numeric(old_df["installation_id"], errors="coerce").astype("Int64")
        else:
            old_df["installation_id"] = pd.Series(dtype="Int64")

        if "app_slug" not in old_df.columns:
            old_df["app_slug"] = pd.Series(dtype="string")

        if "count" not in old_df.columns:
            old_df["count"] = 0

        
        old_df.set_index(["app_slug", "installation_id"], inplace=True, drop=False)
        new_df.set_index(["app_slug", "installation_id"], inplace=True)

        
        for idx, new_row in new_df.iterrows():
            if idx in old_df.index:
                # replace the rate-limit fields and timestamp, increment count
                for fld in ["core_limit", "core_used", "core_remaining",
                            "graphql_limit", "graphql_used", "graphql_remaining",
                            "last_timestamp"]:
                    old_df.at[idx, fld] = new_row.get(fld)
                
                try:
                    old_count = int(old_df.at[idx, "count"])
                    old_df.at[idx, "count"] = old_count + 1
                except Exception:
                    old_df.at[idx, "count"] = 1
            else:
                insert = {
                    "app_slug": new_row.get("app_slug"),
                    "installation_id": new_row.get("installation_id"),
                    "last_timestamp": new_row.get("last_timestamp"),
                    "core_limit": new_row.get("core_limit"),
                    "core_used": new_row.get("core_used"),
                    "core_remaining": new_row.get("core_remaining"),
                    "graphql_limit": new_row.get("graphql_limit"),
                    "graphql_used": new_row.get("graphql_used"),
                    "graphql_remaining": new_row.get("graphql_remaining"),
                    "count": 1
                }
                
                old_df.loc[idx] = insert

        out_df = old_df.reset_index(drop=True)
    else:
        
        new_df = new_df.reset_index(drop=True)
        new_df["count"] = 1
        out_df = new_df

   
    out_df.to_csv(SAMPLES_FILE, index=False)
    logging.info(f"Updated/created {len(rows)} rows. File now has {len(out_df)} total rows → {SAMPLES_FILE}")

if __name__ == "__main__":
    main()
