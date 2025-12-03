import os
import requests
import time
import json

# -----------------------------------------
# CONFIG
# -----------------------------------------

ORG = "JHDevOps"

# Use environment variable OR hard-code for testing
TOKEN = os.getenv("GITHUB_PAT")
# TOKEN = "ghp_xxxxxxxx"  # uncomment if needed

API = "https://api.github.com"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json"
}


# -----------------------------------------
# GET ALL RULESET IDS
# -----------------------------------------

def get_ruleset_ids():
    """Return a list of all ruleset IDs for the organization."""
    url = f"{API}/orgs/{ORG}/rulesets"
    ids = []

    while url:
        print(f"Requesting: {url}")
        r = requests.get(url, headers=HEADERS)

        if r.status_code != 200:
            print(f"ERROR: HTTP {r.status_code}")
            print(r.text)
            break

        data = r.json()
        for rs in data:
            ids.append(rs["id"])

        # pagination
        next_url = None
        link = r.headers.get("Link", "")
        if 'rel="next"' in link:
            parts = link.split(",")
            for p in parts:
                if 'rel="next"' in p:
                    next_url = p[p.find("<")+1:p.find(">")]
        url = next_url

    return ids


# -----------------------------------------
# EXPORT A SINGLE RULESET AS JSON
# -----------------------------------------

def export_ruleset_json(ruleset_id):
    url = f"{API}/orgs/{ORG}/rulesets/{ruleset_id}"

    r = requests.get(url, headers=HEADERS)

    if r.status_code != 200:
        print(f"ERROR fetching ruleset {ruleset_id}: HTTP {r.status_code}")
        print(r.text)
        return

    data = r.json()

    filename = f"ruleset_{ruleset_id}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"✔ Exported {filename}")


# -----------------------------------------
# MAIN
# -----------------------------------------

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("❌ ERROR: No GitHub PAT set (env GITHUB_PAT).")

    print(f"🔐 GitHub Org: {ORG}")
    print("📥 Collecting ruleset IDs...")

    ids = get_ruleset_ids()
    print(f"📦 Found {len(ids)} rulesets")

    for idx, ruleset_id in enumerate(ids, start=1):
        print(f"[{idx}/{len(ids)}] Exporting ruleset {ruleset_id}...")
        export_ruleset_json(ruleset_id)
        time.sleep(1)  # optional polite delay

    print("\n🎉 DONE! All org rulesets exported as JSON.")
