import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_ORG = "JHDevOps"
DEFAULT_PERMISSION = "pull"
DEFAULT_WORKERS = 8

def load_repos_from_multiline(text):
    repos = []
    seen = set()
    for line in (text or "").splitlines():
        name = line.strip()
        if not name or name.startswith("#"):
            continue
        if name not in seen:
            repos.append(name)
            seen.add(name)
    return repos

def put_request(session, url, payload=None, retries=5):
    last = None
    for attempt in range(retries):
        r = session.put(url, json=payload)
        last = r

        if r.status_code == 403 and "rate limit" in r.text.lower():
            reset = r.headers.get("X-RateLimit-Reset")
            wait_time = 30
            if reset and reset.isdigit():
                wait_time = max(1, int(reset) - int(time.time()) + 2)
            time.sleep(wait_time)
            continue

        if r.status_code in (500, 502, 503, 504):
            time.sleep(2 ** attempt)
            continue

        return r

    return last

def grant_team_access(session, org, team_slug, repo, permission):
    url = f"https://api.github.com/orgs/{org}/teams/{team_slug}/repos/{org}/{repo}"
    payload = {"permission": permission}
    r = put_request(session, url, payload=payload)

    ok = r.status_code in (201, 204)
    body = (r.text or "").strip()
    if len(body) > 400:
        body = body[:400] + "..."
    return repo, ok, f"{r.status_code} {body}"

def main():
    org = os.getenv("GH_ORG", DEFAULT_ORG).strip()
    token = os.getenv("GH_TOKEN", "").strip()
    team_slug = os.getenv("GH_TEAM_SLUG", "").strip()

    permission = os.getenv("GH_PERMISSION", DEFAULT_PERMISSION).strip()
    workers = int(os.getenv("GH_WORKERS", str(DEFAULT_WORKERS)))
    dry_run = os.getenv("DRY_RUN", "false").strip().lower() in ("1", "true", "yes")

    repos_text = os.getenv("REPOS", "")
    repos = load_repos_from_multiline(repos_text)

    if not token:
        raise ValueError("Missing GH_TOKEN (set env.GH_TOKEN in TeamCity)")
    if not team_slug:
        raise ValueError("Missing GH_TEAM_SLUG (set env.GH_TEAM_SLUG in TeamCity)")
    if not repos:
        raise ValueError("No repos found. Set env.REPOS as multi-line: one repo name per line")

    session = requests.Session()
    session.headers.update({
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })

    print("org:", org)
    print("team:", team_slug)
    print("permission:", permission)
    print("repos:", len(repos))
    print("dry_run:", dry_run)
    print("-" * 60)

    results = []

    if dry_run:
        for repo in repos:
            print(repo, "->", "dry run")
        print("-" * 60)
        print("completed:", len(repos), "/", len(repos))
        return

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(grant_team_access, session, org, team_slug, repo, permission) for repo in repos]
        for fut in as_completed(futures):
            results.append(fut.result())

    ok_count = 0
    for repo, ok, msg in sorted(results, key=lambda x: x[0].lower()):
        print(repo, "->", msg)
        if ok:
            ok_count += 1

    print("-" * 60)
    print("completed:", ok_count, "/", len(repos))

if __name__ == "__main__":
    main()
