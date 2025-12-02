import requests
from openpyxl import Workbook

# ----------------- CONFIG -----------------
PAT = "PUT_YOUR_PAT_HERE"          # <<< HARD-CODE YOUR PAT HERE
ORG_NAME = "JHDevOps"
OUTPUT_FILE = "github_acl_access.xlsx"
# -------------------------------------------

API_ROOT = "https://api.github.com"

# Permission ranking
PERMISSION_RANK = {
    "read": 1,
    "triage": 2,
    "write": 3,
    "maintain": 4,
    "admin": 5
}

RANK_TO_NAME = {
    1: "Read",
    2: "Triage",
    3: "Write",
    4: "Maintain",
    5: "Admin"
}

def gh_headers():
    return {
        "Authorization": f"token {PAT}",
        "Accept": "application/vnd.github+json"
    }

def paginated(url):
    """Handles GitHub API pagination."""
    results = []
    params = {"per_page": 100}

    while url:
        r = requests.get(url, headers=gh_headers(), params=params)
        if r.status_code != 200:
            print("Error:", r.text)
            break

        results.extend(r.json())

        link = r.headers.get("Link", "")
        next_url = None
        if "rel=\"next\"" in link:
            parts = link.split(",")
            for p in parts:
                if 'rel="next"' in p:
                    next_url = p[p.find("<")+1 : p.find(">")]
                    break

        url = next_url
        params = {}

    return results

def get_all_teams():
    return paginated(f"{API_ROOT}/orgs/{ORG_NAME}/teams")

def get_team_repos(team_slug):
    return paginated(f"{API_ROOT}/orgs/{ORG_NAME}/teams/{team_slug}/repos")

def find_highest_permission_and_count(team_slug):
    """Return (highest_permission_name, repo_count) for a team."""
    repos = get_team_repos(team_slug)
    highest = 0

    for repo in repos:
        # Newer GitHub API: role_name
        role = repo.get("role_name")

        if role:
            perm = role.lower()
        else:
            # Legacy permissions
            perms = repo.get("permissions", {})
            if perms.get("admin"):
                perm = "admin"
            elif perms.get("maintain"):
                perm = "maintain"
            elif perms.get("push"):
                perm = "write"
            elif perms.get("triage"):
                perm = "triage"
            elif perms.get("pull"):
                perm = "read"
            else:
                continue

        rank = PERMISSION_RANK.get(perm, 0)
        if rank > highest:
            highest = rank

    if highest == 0:
        highest_perm_name = ""
    else:
        highest_perm_name = RANK_TO_NAME[highest]

    repo_count = len(repos)
    return highest_perm_name, repo_count

def main():
    print("Fetching teams...")
    teams = get_all_teams()
    print(f"Total teams found: {len(teams)}")

    wb = Workbook()
    ws = wb.active
    ws.title = "ACL"

    # Header
    ws.append(["Domain", "GroupName", "Description", "AccessLevel"])

    for t in teams:
        name = t.get("name")
        slug = t.get("slug")

        print(f"Processing: {name}...")

        highest_perm, repo_count = find_highest_permission_and_count(slug)

        # Build description for column 3
        # "Members of this ACL is having access to X repo(s). To be used for <HighestPerm> kind of role."
        repo_word = "repo" if repo_count == 1 else "repos"
        if highest_perm:
            description = (
                f"Members of this ACL is having access to {repo_count} {repo_word}. "
                f"To be used for {highest_perm} kind of role."
            )
        else:
            description = (
                f"Members of this ACL is having access to {repo_count} {repo_word}."
            )

        ws.append([
            "MFCGD",      # Domain
            name,         # GroupName (team name)
            description,  # Description (new format)
            highest_perm  # AccessLevel
        ])

    wb.save(OUTPUT_FILE)
    print(f"\nExcel generated: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
