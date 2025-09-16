import os, time, pathlib, logging, requests, jwt, json
from datetime import datetime, timezone, timedelta
import pandas as pd

ORG = "JHDevOps"
NUM_APPS = 7
DATA_DIR = pathlib.Path("./data"); DATA_DIR.mkdir(exist_ok=True)
AGG_FILE = DATA_DIR / "api_usage_aggregates.json"
SUMMARY_CSV = DATA_DIR / "api_usage_30d_summary.csv"
GITHUB_API = "https://api.github.com"
logging.basicConfig(level=logging.INFO, format="%(message)s")

APPS = []
for i in range(1, NUM_APPS + 1):
    app_id = os.getenv(f"appid{i}")
    rsakey = os.getenv(f"rsakey{i}")
    if not app_id or not rsakey:
        continue
    APPS.append({"slug": f"app-{i}", "app_id": int(app_id), "private_key_pem": rsakey})

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

def _as_int(v):
    try:
        return int(v)
    except Exception:
        return 0

def load_aggs():
    if AGG_FILE.exists():
        try:
            with open(AGG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_aggs(obj):
    with open(AGG_FILE, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)

def prune_daily_counts(daily_counts):
    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=29)  # keep 30 days including today
    keys = list(daily_counts.keys())
    for k in keys:
        try:
            d = datetime.strptime(k, "%Y-%m-%d").date()
            if d < cutoff:
                daily_counts.pop(k, None)
        except Exception:
            daily_counts.pop(k, None)

def main():
    ts = datetime.now(timezone.utc).isoformat()
    today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    aggs = load_aggs()
    summary_rows = []

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
            if acct != ORG:
                continue
            try:
                inst_token = create_installation_token(app_jwt, inst_id)
                resources = get_rate_limit(inst_token)
            except Exception as e:
                logging.warning(f"[{slug}] inst {inst_id} failed: {e}")
                continue

            core = resources.get("core", {}) or {}
            used = _as_int(core.get("used", 0))
            limit = _as_int(core.get("limit", 0))

            key = f"{slug}|{inst_id}"
            record = aggs.get(key, {
                "app_slug": slug,
                "installation_id": int(inst_id),
                "last_core_used": None,
                "last_core_limit": None,
                "last_ts": None,
                "last_hour_count": 0,
                "daily_counts": {},
                "total_calls_alltime": 0
            })

            prev_used = record.get("last_core_used")
            prev_limit = record.get("last_core_limit")

            if prev_used is None:
                delta = used
            else:
                if used >= prev_used:
                    delta = used - prev_used
                else:
                    if prev_limit:
                        try:
                            delta = (prev_limit - prev_used) + used
                            if delta < 0:
                                delta = used
                        except Exception:
                            delta = used
                    else:
                        delta = used

            if delta < 0:
                delta = 0

            record["last_hour_count"] = int(delta)
            record["last_core_used"] = int(used)
            record["last_core_limit"] = int(limit)
            record["last_ts"] = ts

            dc = record.get("daily_counts") or {}
            dc[today_key] = int(dc.get(today_key, 0)) + int(delta)
            prune_daily_counts(dc)
            record["daily_counts"] = dc
            record["total_calls_alltime"] = int(record.get("total_calls_alltime", 0)) + int(delta)
            last_30d_total = sum(int(v) for v in dc.values())

            aggs[key] = record

            summary_rows.append({
                "app_slug": slug,
                "installation_id": inst_id,
                "last_timestamp": ts,
                "last_hour_count": int(delta),
                "today_total": int(dc.get(today_key, 0)),
                "last_30d_total": int(last_30d_total)
            })

    save_aggs(aggs)

    if summary_rows:
        df = pd.DataFrame(summary_rows)
        df.to_csv(SUMMARY_CSV, index=False)
        logging.info(f"Wrote summary for {len(df)} rows → {SUMMARY_CSV}")
        logging.info(df.to_string(index=False))
    else:
        logging.info("No rows collected.")

if __name__ == "__main__":
    main()
