# 03_teamcity_builds_env_parallel.py
# Parallel TeamCity build fetch -> map to GitHub Apps -> aggregate per app/installation.

import os, time, pathlib, logging, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from dateutil import parser as dtparser
import pandas as pd
import urllib3

# silence InsecureRequestWarning for verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATA_DIR = pathlib.Path("./data"); DATA_DIR.mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(message)s")

TEAMCITY_BASE = os.getenv("TEAMCITY_BASE") or os.getenv("teamcity_base")
TEAMCITY_PAT  = os.getenv("TEAMCITY_PAT")  or os.getenv("teamcity_pat")
DAYS_BACK     = int(os.getenv("TEAMCITY_DAYS_BACK") or 30)

# ---- concurrency tunables ----
CHUNK_DAYS = 3          # set to 1 for more parallelism
N_WORKERS  = 8          # raise if your TC can handle it
TIMEOUT_S  = 60
RETRIES    = 3
SLEEP_BETWEEN_RETRIES_S = 2
# ------------------------------

if not TEAMCITY_BASE or not TEAMCITY_PAT:
    raise SystemExit("Please set TEAMCITY_BASE and TEAMCITY_PAT environment variables.")

FIELDS = (
    "build(id,buildTypeId,status,state,queuedDate,startDate,finishDate,webUrl,"
    "revisions(revision(vcsRootInstance(vcs-root(properties(property(name,value)))))))"
)

def _tc_get(path, params=None):
    headers = {"Authorization": f"Bearer {TEAMCITY_PAT}", "Accept": "application/json"}
    url = f"{TEAMCITY_BASE.rstrip('/')}{path}"
    last_exc = None
    for attempt in range(1, RETRIES+1):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=TIMEOUT_S, verify=False)
            if r.status_code >= 400:
                raise RuntimeError(f"TeamCity GET {path} -> {r.status_code} {r.text[:300]}")
            return r.json()
        except Exception as exc:
            last_exc = exc
            if attempt < RETRIES:
                time.sleep(SLEEP_BETWEEN_RETRIES_S * attempt)
            else:
                raise last_exc

def _parse_tc_time(s):
    if not s: return None
    try: return dtparser.parse(s)
    except Exception: return None

def _extract_repo(build) -> str | None:
    try:
        revs = build.get("revisions", {}).get("revision", [])
        if not revs: return None
        vroot = revs[0].get("vcsRootInstance", {}).get("vcs-root", {})
        props = vroot.get("properties", {}).get("property", [])
        kv = {p.get("name"): p.get("value") for p in props if "name" in p and "value" in p}
        repo_url = (
            kv.get("url") or kv.get("repository_url") or kv.get("repositoryUrl")
            or kv.get("repo_url") or kv.get("gitUrl") or ""
        ).strip()
        if repo_url.endswith(".git"): repo_url = repo_url[:-4]
        if "github.com/" in repo_url:
            tail = repo_url.split("github.com/")[1].strip("/")
            parts = tail.split("/")
            if len(parts) >= 2:
                return "/".join(parts[:2])
    except Exception:
        return None
    return None

def _iso_tc(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S+0000")

def _fetch_chunk(since_dt: datetime, until_dt: datetime) -> list[dict]:
    builds = []
    locator = f"sinceDate:{_iso_tc(since_dt)},untilDate:{_iso_tc(until_dt)},count:1000"
    path = f"/app/rest/builds?locator={locator}&fields={FIELDS}"
    while True:
        data = _tc_get(path)
        chunk_builds = data.get("build", [])
        for b in chunk_builds:
            qd = _parse_tc_time(b.get("queuedDate"))
            sd = _parse_tc_time(b.get("startDate"))
            fd = _parse_tc_time(b.get("finishDate"))
            dur = (fd - sd).total_seconds() if (fd and sd) else None
            builds.append({
                "build_id": b.get("id"),
                "status": b.get("status"),
                "state": b.get("state"),
                "queued_at": qd.isoformat() if qd else None,
                "started_at": sd.isoformat() if sd else None,
                "finished_at": fd.isoformat() if fd else None,
                "duration_s": dur,
                "repo": _extract_repo(b),
            })
        next_href = data.get("nextHref")
        if not next_href: break
        if "fields=" not in next_href:
            join = "&" if "?" in next_href else "?"
            next_href = f"{next_href}{join}fields={FIELDS}"
        if not next_href.startswith("/"):
            next_href = "/" + next_href
        path = next_href
    return builds

def main():
    end_utc = datetime.now(timezone.utc)
    start_utc = end_utc - timedelta(days=DAYS_BACK)

    # Build chunk windows
    chunks = []
    cur = start_utc
    while cur < end_utc:
        nxt = min(cur + timedelta(days=CHUNK_DAYS), end_utc)
        chunks.append((cur, nxt))
        cur = nxt

    logging.info(f"Fetching builds in {len(chunks)} chunks ({CHUNK_DAYS} days each)…")

    all_rows = []
    with ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
        futs = {ex.submit(_fetch_chunk, start_dt, end_dt): (start_dt, end_dt) for (start_dt, end_dt) in chunks}
        for fut in as_completed(futs):
            start_dt, end_dt = futs[fut]
            try:
                rows = fut.result()
                all_rows.extend(rows)
                logging.info(f"  chunk {_iso_tc(start_dt)} → {_iso_tc(end_dt)}: {len(rows)} builds")
            except Exception as err:
                logging.error(f"  chunk {_iso_tc(start_dt)} → {_iso_tc(end_dt)} failed: {err}")

    df = pd.DataFrame(all_rows).drop_duplicates(subset=["build_id"]) if all_rows else pd.DataFrame(
        columns=["build_id","status","state","queued_at","started_at","finished_at","duration_s","repo"]
    )
    raw_path = DATA_DIR / "teamcity_builds_raw.csv"
    df.to_csv(raw_path, index=False)
    logging.info(f"Saved: {raw_path} ({len(df)} unique builds)")

    # Map builds → app via Step 1 mapping
    map_path = DATA_DIR / "repo_app_map.csv"
    if not map_path.exists():
        raise SystemExit("Missing data/repo_app_map.csv from Step 1.")

    repo_map = pd.read_csv(map_path)
    m = repo_map[["repo_full_name", "app_slug", "installation_id"]].drop_duplicates()
    use = df.dropna(subset=["repo"]).merge(m, how="left", left_on="repo", right_on="repo_full_name")

    def _succ(s): return (s == "SUCCESS").sum()
    def _fail(s): return (s == "FAILURE").sum()

    agg = use.groupby(["app_slug", "installation_id"], dropna=False).agg(
        builds=("build_id", "count"),
        successes=("status", _succ),
        failures=("status", _fail),
        avg_duration_s=("duration_s", "mean")
    ).reset_index()

    out_path = DATA_DIR / "builds_by_app.csv"
    agg.to_csv(out_path, index=False)
    logging.info(f"Saved: {out_path}")

if __name__ == "__main__":
    main()
