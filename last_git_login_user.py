import requests
from datetime import datetime, timezone

# ---------- CONFIG ----------
ORG = "JHDevOps"
USERNAME = "hardcoded-username"   # <- put the target login here (their GitHub username)
TOKEN = "ghp_yourPATtoken"        # <- PAT with admin:org
# ----------------------------

API_HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

BASE_URL = f"https://api.github.com/orgs/{ORG}/audit-log"

def parse_github_time(value):
    """
    Accepts ISO 8601 string, epoch seconds, or epoch milliseconds.
    Returns a timezone-aware UTC datetime.
    """
    if value is None:
        return None
    # int/float -> epoch; GitHub often uses milliseconds
    if isinstance(value, (int, float)):
        # Heuristic: treat >= 10^12 as ms, else seconds
        if value >= 1_000_000_000_000:
            return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
        else:
            return datetime.fromtimestamp(value, tz=timezone.utc)
    # str -> ISO 8601
    if isinstance(value, str):
        # Normalize trailing Z to +00:00
        iso = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(iso)
        except Exception:
            return None
    return None

def get_latest_login(org: str, username: str):
    """
    Returns (dt, raw_event, source_action) for the user's latest login-like activity
    or (None, None, None) if not found.
    """
    # Try successful login first
    search_phrases = [
        f"actor:{username} action:user.login",
        # Uncomment these if you want to consider other auth events as a fallback:
        f"actor:{username} action:user.failed_login",
        f"actor:{username} action:github_app_authentication",
    ]

    for phrase in search_phrases:
        params = {
            "phrase": phrase,
            "per_page": 1,    # newest first, 1 result
            "order": "desc",
            "include": "all"  # include web & API events
        }
        resp = requests.get(BASE_URL, headers=API_HEADERS, params=params, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"GitHub API error {resp.status_code}: {resp.text}")

        events = resp.json()
        if not events:
            continue

        ev = events[0]
        # Prefer '@timestamp'; also try 'created_at' if present
        ts = ev.get("@timestamp") or ev.get("created_at") or ev.get("timestamp")
        dt = parse_github_time(ts)
        if dt:
            return dt, ev, phrase

    return None, None, None

if __name__ == "__main__":
    try:
        dt, ev, source = get_latest_login(ORG, USERNAME)
        if dt:
            print(f"Latest login time for '{USERNAME}' (UTC): {dt.isoformat()}")
            # Optional: print event id and actor for audit trail
            print(f"From search: {source}")
            print(f"Event ID: {ev.get('_id', 'n/a')}")
        else:
            print(f"No login events found for '{USERNAME}' in org '{ORG}' "
                  "(within your org's audit log retention window).")
            print("Tip: Ensure the PAT has 'admin:org' and you are an org owner.")
    except Exception as e:
        print(f"Failed: {e}")
