import os
import requests
import time

# -----------------------------------------
# CONFIG
# -----------------------------------------

ORG = "JHDevOps"

# Use environment variable OR hard-code if testing locally
TOKEN = os.getenv("GITHUB_PAT")
# TOKEN = "ghp_xxxxxx"  # <-- uncomment for local/testing usage

API = "https://api.github.com"
HEADERS_JSON = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json"
}
HEADERS_YAML = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/yaml"
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
        r = requests.get(url, headers=HEADERS_JSON)

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
# EXPORT A SINGLE RULESET AS YAML
# -----------------------------------------

def export_ruleset_yaml(ruleset_id):
    url = f"{API}/orgs/{ORG}/rulesets/{ruleset_id}"

    r = requests.get(url, headers=HEADERS_YAML)

    if r.status_code != 200:
        print(f"ERROR fetching ruleset {ruleset_id}: HTTP {r.status_code}")
        print(r.text)
        return

    filename = f"ruleset_{ruleset_id}.yaml"

    with open(filename, "wb") as f:
        f.write(r.content)

    print(f"✔ Exported {filename}")


# -----------------------------------------
# MAIN
# -----------------------------------------

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("❌ ERROR: No GitHub PAT set. Set env GITHUB_PAT or hard-code TOKEN.")

    print(f"🔐 GitHub Org: {ORG}")
    print("📥 Collecting ruleset IDs...")

    ids = get_ruleset_ids()

    print(f"📦 Found {len(ids)} rulesets")

    for idx, ruleset_id in enumerate(ids, start=1):
        print(f"[{idx}/{len(ids)}] Exporting ruleset {ruleset_id}...")
        export_ruleset_yaml(ruleset_id)
        time.sleep(1)  # avoid GitHub rate limits (safe + polite)

    print("\n🎉 DONE! All org rulesets exported as YAML.")
