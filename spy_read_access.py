import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

ORG = "JHDevOps"
TOKEN = ""

TEAM_SLUG = ""

PERMISSION = "pull"
MAX_WORKERS = 8
DRY_RUN = False

REPOS_TEXT = """
repo-one
repo-two
repo-three
"""

def load_repos(text):
    repos = []
    seen = set()
    for line in text.splitlines():
        name = line.strip()
        if not name:
            continue
        if name not in seen:
            repos.append(name)
            seen.add(name)
    return repos

def put_request(session, url, payload=None):
    last_response = None
    for attempt in range(5):
        response = session.put(url, json=payload)
        last_response = response

        if response.status_code == 403 and "rate limit" in response.text.lower():
            reset = response.headers.get("X-RateLimit-Reset")
            wait_time = 30
            if reset and reset.isdigit():
                wait_time = max(1, int(reset) - int(time.time()) + 2)
            time.sleep(wait_time)
            continue

        if response.status_code in (500, 502, 503, 504):
            time.sleep(2 ** attempt)
            continue

        return response

    return last_response

def grant_team_read(session, repo):
    url = f"https://api.github.com/orgs/{ORG}/teams/{TEAM_SLUG}/repos/{ORG}/{repo}"
    payload = {"permission": PERMISSION}

    if DRY_RUN:
        return repo, True, "dry run"

    response = put_request(session, url, payload)
    success = response.status_code in (201, 204)
    message = f"{response.status_code} {response.text}".strip()
    return repo, success, message

def main():
    if not TOKEN:
        raise ValueError("TOKEN is empty")

    if not TEAM_SLUG:
        raise ValueError("TEAM_SLUG is empty")

    repos = load_repos(REPOS_TEXT)

    if not repos:
        raise ValueError("No repositories provided")

    session = requests.Session()
    session.headers.update({
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })

    print("organization:", ORG)
    print("team:", TEAM_SLUG)
    print("permission:", PERMISSION)
    print("repositories:", len(repos))
    print("-" * 50)

    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(grant_team_read, session, repo) for repo in repos]
        for future in as_completed(futures):
            results.append(future.result())

    success_count = 0
    for repo, success, message in sorted(results):
        print(repo, "->", message[:300])
        if success:
            success_count += 1

    print("-" * 50)
    print("completed:", success_count, "/", len(repos))

if __name__ == "__main__":
    main()
