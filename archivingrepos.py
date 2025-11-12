import logging
import time
import pandas as pd
import requests

# ===== CONFIGURATION =====
ORG = "JHDevOps"
EXCEL_FILE = "repos.xlsx"            # first column only; header can be anything
GITHUB_PAT = "PUT_YOUR_PAT_HERE"     # ⚠️ your PAT token here (repo + admin:org)
DRY_RUN = False                      # True = simulate only
MAX_RETRIES = 3
API_URL = "https://api.github.com"
# =========================

class GitHubClient:
    def __init__(self, token, api_url=API_URL):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "repo-lockdown-script/SpyderFix"
        })
        self.api_url = api_url.rstrip("/")

    def _url(self, path): return f"{self.api_url}{path}"

    def _req(self, method, url, **kwargs):
        for attempt in range(1, MAX_RETRIES + 1):
            r = self.session.request(method, url, timeout=60, **kwargs)
            if r.status_code in (429, 502, 503, 504):
                logging.warning("Transient %s on %s %s (attempt %d/%d)", r.status_code, method, url, attempt, MAX_RETRIES)
                time.sleep(min(2 ** attempt, 10))
                continue
            return r
        return r

    # ------- Repo -------
    def get_repo(self, owner, repo):
        r = self._req("GET", self._url(f"/repos/{owner}/{repo}"))
        if r.status_code == 200:
            return r.json()
        logging.error("get_repo %s/%s -> %s %s", owner, repo, r.status_code, r.text)
        return None

    def update_repo(self, owner, repo, payload):
        if DRY_RUN:
            logging.info("[DRY-RUN] PATCH /repos/%s/%s %s", owner, repo, payload)
            return True, 200, {}
        r = self._req("PATCH", self._url(f"/repos/{owner}/{repo}"), json=payload)
        ok = (r.status_code == 200)
        if not ok:
            logging.error("update_repo %s/%s -> %s %s", owner, repo, r.status_code, r.text)
        return ok, r.status_code, (r.json() if "application/json" in r.headers.get("Content-Type","") else {})

    # ------- Collaborators -------
    def list_collaborators(self, owner, repo, page=1):
        r = self._req("GET", self._url(f"/repos/{owner}/{repo}/collaborators"),
                      params={"per_page": 100, "page": page})
        if r.status_code == 200:
            return r.json()
        logging.error("list_collaborators %s/%s -> %s %s", owner, repo, r.status_code, r.text)
        return []

    def get_collab_permission(self, owner, repo, username):
        r = self._req("GET", self._url(f"/repos/{owner}/{repo}/collaborators/{username}/permission"))
        if r.status_code == 200:
            # returns: {"permission":"admin|maintain|...","user":{...}}
            return r.json().get("permission")
        return None

    def remove_collaborator(self, owner, repo, username):
        if DRY_RUN:
            logging.info("[DRY-RUN] DELETE collaborator %s from %s/%s", username, owner, repo)
            return True
        r = self._req("DELETE", self._url(f"/repos/{owner}/{repo}/collaborators/{username}"))
        if r.status_code in (204, 404):  # 404 if already gone
            return True
        logging.error("remove_collaborator %s %s/%s -> %s %s", username, owner, repo, r.status_code, r.text)
        return False

    # ------- Teams -------
    def list_repo_teams(self, owner, repo, page=1):
        r = self._req("GET", self._url(f"/repos/{owner}/{repo}/teams"),
                      params={"per_page": 100, "page": page})
        if r.status_code == 200:
            return r.json()
        logging.error("list_repo_teams %s/%s -> %s %s", owner, repo, r.status_code, r.text)
        return []

    def remove_team_access(self, org, repo_owner, repo, team_slug):
        if DRY_RUN:
            logging.info("[DRY-RUN] DELETE team %s from %s/%s", team_slug, repo_owner, repo)
            return True
        r = self._req("DELETE", self._url(f"/orgs/{org}/teams/{team_slug}/repos/{repo_owner}/{repo}"))
        if r.status_code in (204, 404):
            return True
        logging.error("remove_team_access %s %s/%s -> %s %s", team_slug, repo_owner, repo, r.status_code, r.text)
        return False

    # ------- Invitations (pending access) -------
    def list_repo_invitations(self, owner, repo, page=1):
        r = self._req("GET", self._url(f"/repos/{owner}/{repo}/invitations"),
                      params={"per_page": 100, "page": page})
        if r.status_code == 200:
            return r.json()
        logging.error("list_repo_invitations %s/%s -> %s %s", owner, repo, r.status_code, r.text)
        return []

    def revoke_invitation(self, owner, repo, invitation_id):
        if DRY_RUN:
            logging.info("[DRY-RUN] DELETE invitation %s on %s/%s", invitation_id, owner, repo)
            return True
        r = self._req("DELETE", self._url(f"/repos/{owner}/{repo}/invitations/{invitation_id}"))
        if r.status_code in (204, 404):
            return True
        logging.error("revoke_invitation %s %s/%s -> %s %s", invitation_id, owner, repo, r.status_code, r.text)
        return False


def make_private_if_needed(gh, owner, repo, meta):
    if meta.get("private", False):
        logging.info("Already private.")
        return True

    # Try to force internal/public -> private in one go
    payload = {"private": True, "visibility": "private"}
    ok, status, body = gh.update_repo(owner, repo, payload)
    if ok:
        logging.info("→ Made private")
        return True

    # If policy blocks, log clearly (don’t fail the whole run)
    if status in (403, 422):
        msg = body.get("message") if isinstance(body, dict) else str(body)
        logging.warning("Could not change visibility to private (policy?) for %s/%s: %s", owner, repo, msg)
        return False

    return False


def archive_if_needed(gh, owner, repo, meta):
    if meta.get("archived", False):
        logging.info("Already archived.")
        return True
    ok, _, _ = gh.update_repo(owner, repo, {"archived": True})
    if ok:
        logging.info("→ Archived")
    return ok


def remove_all_collaborators(gh, owner, repo):
    total_removed = 0
    page = 1
    seen = set()
    while True:
        collabs = gh.list_collaborators(owner, repo, page=page)
        if not collabs:
            break
        for c in collabs:
            login = c.get("login")
            if not login or login in seen:
                continue
            seen.add(login)
            perm = gh.get_collab_permission(owner, repo, login)
            logging.info("  collaborator %-25s role=%s", login, perm or "unknown")
            if gh.remove_collaborator(owner, repo, login):
                total_removed += 1
        if len(collabs) < 100:
            break
        page += 1
    if total_removed > 0:
        logging.info("→ Removed %d collaborators", total_removed)
    else:
        logging.info("→ No direct/outside collaborators found")
    return total_removed


def remove_all_teams(gh, owner, repo):
    total_removed = 0
    page = 1
    while True:
        teams = gh.list_repo_teams(owner, repo, page=page)
        if not teams:
            break
        for t in teams:
            slug = t.get("slug")
            perm = t.get("permission") or t.get("permissions")
            logging.info("  team %-25s role=%s", slug, perm if isinstance(perm, str) else "unknown")
            if slug and gh.remove_team_access(ORG, owner, repo, slug):
                total_removed += 1
        if len(teams) < 100:
            break
        page += 1
    if total_removed > 0:
        logging.info("→ Removed %d team mappings", total_removed)
    else:
        logging.info("→ No team mappings on this repo")
    return total_removed


def revoke_all_invitations(gh, owner, repo):
    total_revoked = 0
    page = 1
    while True:
        invs = gh.list_repo_invitations(owner, repo, page=page)
        if not invs:
            break
        for inv in invs:
            inv_id = inv.get("id")
            login = (inv.get("invitee") or {}).get("login")
            logging.info("  pending invite %-25s id=%s", login or "unknown", inv_id)
            if inv_id and gh.revoke_invitation(owner, repo, inv_id):
                total_revoked += 1
        if len(invs) < 100:
            break
        page += 1
    if total_revoked > 0:
        logging.info("→ Revoked %d pending invitations", total_revoked)
    else:
        logging.info("→ No pending invitations")
    return total_revoked


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S")
    gh = GitHubClient(GITHUB_PAT)

    # Read first column; header can be anything
    df = pd.read_excel(EXCEL_FILE, header=0)
    first_col = df.columns[0]
    entries = [str(v).strip() for v in df[first_col].dropna() if str(v).strip()]

    summary = {"processed": 0, "made_private": 0, "archived": 0, "collab_removed": 0, "teams_removed": 0, "inv_revoked": 0, "errors": 0}

    for entry in entries:
        repo = entry.split("/")[-1]  # allow 'repo' or 'something/repo'
        owner = ORG
        logging.info("=== Processing %s/%s ===", owner, repo)

        meta = gh.get_repo(owner, repo)
        if not meta:
            summary["errors"] += 1
            continue

        # 1) make private before archival (internal/public -> private)
        if make_private_if_needed(gh, owner, repo, meta):
            summary["made_private"] += 1

        # 2) archive
        # refresh meta so we see current archived flag if needed
        meta2 = gh.get_repo(owner, repo) or {}
        if archive_if_needed(gh, owner, repo, meta2):
            summary["archived"] += 1

        # 3) remove all collaborators (any role incl. admin/maintain) at repo level
        summary["collab_removed"] += remove_all_collaborators(gh, owner, repo)

        # 4) remove all team mappings (teams often carry admin/maintain)
        summary["teams_removed"] += remove_all_teams(gh, owner, repo)

        # 5) revoke any pending invitations
        summary["inv_revoked"] += revoke_all_invitations(gh, owner, repo)

        summary["processed"] += 1
        logging.info("Done: %s/%s", owner, repo)

    logging.info("==== SUMMARY ====")
    for k, v in summary.items():
        logging.info("%s: %d", k, v)


if __name__ == "__main__":
    main()
