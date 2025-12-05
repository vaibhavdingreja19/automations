import os
import requests
import pandas as pd
import urllib3

# -------- SSL WARNING (optional) --------
# Disable "InsecureRequestWarning" for verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# ---------------------------------------

# ---------------- CONFIG ----------------

# TeamCity setup
TEAMCITY_URL = os.getenv("TC_URL", "https://teamcity.jhancock.com")
TEAMCITY_PAT = os.getenv("TC_PAT", "")  # or hard-code below

# TEAMCITY_PAT = "YOUR_TEAMCITY_PAT_HERE"  # <-- optional: for local testing

# Excel with inactive repos + GitHub App column
INACTIVE_FILE = "inactive_repos_with_app.xlsx"

# Output file with VCS mapping
OUTPUT_FILE = "inactive_repos_vcs_map.xlsx"

# Column names in INACTIVE_FILE
COL_REPO = "Repository"
COL_APP = "GitHub App"

# Disable SSL verification for TeamCity (self-signed cert)
VERIFY_SSL = False
# ----------------------------------------


def teamcity_headers():
    if not TEAMCITY_PAT:
        raise SystemExit("TeamCity PAT missing. Set env TC_PAT or hard-code TEAMCITY_PAT.")
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {TEAMCITY_PAT}",
    }


def get_all_vcs_roots():
    """
    Fetch all VCS roots from TeamCity in one call, including their URL property.
    Returns a list of dicts: {id, name, url}.
    """
    url = (
        f"{TEAMCITY_URL}/app/rest/vcs-roots"
        "?fields=vcs-root(id,name,properties(property(name,value)))"
    )
    print(f"Fetching VCS roots from: {url}")
    r = requests.get(url, headers=teamcity_headers(), verify=VERIFY_SSL)
    r.raise_for_status()

    data = r.json()

    # TeamCity JSON can use "vcs-root" or "vcsRoot" depending on version
    roots_raw = data.get("vcs-root") or data.get("vcsRoot") or []

    roots = []
    for root in roots_raw:
        vcs_id = root.get("id")
        name = root.get("name", "")
        url_val = ""

        props = root.get("properties", {}).get("property", [])
        for p in props:
            if p.get("name") == "url":
                url_val = p.get("value", "")
                break

        roots.append(
            {
                "id": vcs_id,
                "name": name,
                "url": url_val,
            }
        )

    print(f"Total VCS roots fetched: {len(roots)}")
    return roots


def main():
    # 1. Load inactive repos that are in at least one GitHub App
    df = pd.read_excel(INACTIVE_FILE)

    if COL_REPO not in df.columns or COL_APP not in df.columns:
        raise SystemExit(
            f"Columns '{COL_REPO}' and/or '{COL_APP}' not found in {INACTIVE_FILE}"
        )

    df_target = df[df[COL_APP].notna() & (df[COL_APP] != "")]
    target_repos = sorted(df_target[COL_REPO].dropna().astype(str).unique())

    print(f"Target repos (in GitHub Apps): {len(target_repos)}")

    if not target_repos:
        print("No repos with GitHub App mapping found. Nothing to do.")
        return

    # 2. Fetch all VCS roots once
    vcs_roots = get_all_vcs_roots()

    # 3. For each target repo, find matching VCS roots by URL
    rows = []
    for repo in target_repos:
        repo_lower = repo.lower()
        print(f"Looking for VCS roots using repo: {repo}")

        for root in vcs_roots:
            url = (root.get("url") or "").lower()
            if not url:
                continue

            # Simple matching rule: look for "/<repo>" in the URL
            # e.g. https://github.com/JHDevOps/Amazon_connect.git
            if f"/{repo_lower}" in url:
                rows.append(
                    {
                        "Repository": repo,
                        "VCS Root ID": root.get("id"),
                        "VCS Root Name": root.get("name"),
                        "VCS URL": root.get("url"),
                    }
                )

    if not rows:
        print("No matching VCS roots found for the target repos.")
    else:
        out_df = pd.DataFrame(rows)
        out_df.to_excel(OUTPUT_FILE, index=False)
        print(f"\nDone. Saved VCS mapping to '{OUTPUT_FILE}'")


if __name__ == "__main__":
    main()
