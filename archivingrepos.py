import logging
import time
import pandas as pd
import requests

# ===== CONFIGURATION =====
ORG = "JHDevOps"
EXCEL_FILE = "repos.xlsx"     # put your Excel file in same folder
GITHUB_PAT = "PUT_YOUR_PAT_HERE"  # ⚠️ your PAT token here
DRY_RUN = False               # change to True for testing only
MAX_RETRIES = 3
# =========================

DEFAULT_API_URL = "https://api.github.com"

# ---- GitHub API client ----
class GitHubClient:
    def __init__(self, token, api_url=DEFAULT_API_URL):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "repo-lockdown-script/SpyderVersion"
        })
        self.api_url = api_url.rstrip("/")

    def _url(self, path): return f"{self.api_url}{path}"

    def _request(self, method, url, **kwargs):
        for attempt in range(1, MAX_RETRIES + 1):
            resp = self.session.request(method, url, timeout=60, **kwargs)
            if resp.status_code in (429, 502, 503, 504):
                logging.warning("Retry %s for %s %s", attempt, method, url)
                time.sleep(2 ** attempt)
                continue
            return resp
        return resp

    def get_repo(self, owner, repo):
        r = self._request("GET", self._url(f"/repos/{owner}/{repo}"))
        return r.json() if r.status_code == 200 else None

    def update_repo(self, owner, repo, payload):
        if DRY_RUN:
            logging.info("[DRY-RUN] PATCH %s/%s %s", owner, repo, payload)
            return True
        r = self._request("PATCH", self._url(f"/repos/{owner}/{repo}"), json=payload)
        return r.status_code == 200

    def list_collaborators(self, owner, repo):
        r = self._request("GET", self._url(f"/repos/{owner}/{repo}/collaborators"), params={"per_page": 100})
        return r.json() if r.status_code == 200 else []

    def remove_collaborator(self, owner, repo, username):
        if DRY_RUN:
            logging.info("[DRY-RUN] Remove collaborator %s from %s/%s", username, owner, repo)
            return True
        r = self._request("DELETE", self._url(f"/repos/{owner}/{repo}/collaborators/{username}"))
        return r.status_code in (204, 404)

    def list_repo_teams(self, owner, repo):
        r = self._request("GET", self._url(f"/repos/{owner}/{repo}/teams"), params={"per_page": 100})
        return r.json() if r.status_code == 200 else []

    def remove_team_access(self, org, repo_owner, repo, team_slug):
        if DRY_RUN:
            logging.info("[DRY-RUN] Remove team %s from %s/%s", team_slug, repo_owner, repo)
            return True
        r = self._request("DELETE", self._url(f"/orgs/{org}/teams/{team_slug}/repos/{repo_owner}/{repo}"))
        return r.status_code in (204, 404)


# ---- main logic ----
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S")
    gh = GitHubClient(GITHUB_PAT)

    df = pd.read_excel(EXCEL_FILE, header=0)
    repo_col = df.columns[0]
    repos = [str(v).strip() for v in df[repo_col].dropna() if str(v).strip()]

    summary = {"processed": 0, "archived": 0, "private": 0, "collabs": 0, "teams": 0}

    for entry in repos:
        repo = entry.split("/")[-1]  # support "repo" or "org/repo"
        owner = ORG
        logging.info("=== Processing %s/%s ===", owner, repo)

        meta = gh.get_repo(owner, repo)
        if not meta:
            logging.error("Failed to fetch repo %s/%s", owner, repo)
            continue

        # make private
        if not meta.get("private", False):
            if gh.update_repo(owner, repo, {"private": True}):
                summary["private"] += 1
                logging.info("→ Made private")

        # archive
        if not meta.get("archived", False):
            if gh.update_repo(owner, repo, {"archived": True}):
                summary["archived"] += 1
                logging.info("→ Archived")

        # remove collaborators
        collabs = gh.list_collaborators(owner, repo)
        for c in collabs:
            if gh.remove_collaborator(owner, repo, c["login"]):
                summary["collabs"] += 1
        logging.info("→ Removed %d collaborators", len(collabs))

        # remove teams
        teams = gh.list_repo_teams(owner, repo)
        for t in teams:
            gh.remove_team_access(ORG, owner, repo, t["slug"])
            summary["teams"] += 1
        logging.info("→ Removed %d teams", len(teams))

        summary["processed"] += 1
        logging.info("Done: %s/%s", owner, repo)

    logging.info("==== SUMMARY ====")
    for k, v in summary.items():
        logging.info("%s: %d", k, v)


if __name__ == "__main__":
    main()
