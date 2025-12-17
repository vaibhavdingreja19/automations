import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ORG = "JHDevOps"
TOKEN = ""

REPOS = [
    "repo-one",
    "repo-two",
    "repo-three",
]

MODE = "team"      
TEAM_SLUG = ""     
# USERNAME = ""      

PERMISSION = "pull"
MAX_WORKERS = 8
DRY_RUN = False

session = requests.Session()
session.headers.update({
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
})

def put_request(url, payload=None):
    retries = 5
    for attempt in range(retries):
        response = session.put(url, json=payload)

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

    return response

def give_team_access(repo):
    url = f"https://api.github.com/orgs/{ORG}/teams/{TEAM_SLUG}/repos/{ORG}/{repo}"
    payload = {"permission": PERMISSION}

    if DRY_RUN:
        return repo, True, "dry run"

    response = put_request(url, payload)
    success = response.status_code in (201, 204)
    return repo, success, f"{response.status_code} {response.text}"

def give_user_access(repo):
    url = f"https://api.github.com/repos/{ORG}/{repo}/collaborators/{USERNAME}"
    payload = {"permission": PERMISSION}

    if DRY_RUN:
        return repo, True, "dry run"

    response = put_request(url, payload)
    success = response.status_code in (201, 202, 204)
    return repo, success, f"{response.status_code} {response.text}"

def main():
    if MODE == "team" and not TEAM_SLUG:
        raise ValueError("TEAM_SLUG is required when MODE is team")

    if MODE == "user" and not USERNAME:
        raise ValueError("USERNAME is required when MODE is user")

    action = give_team_access if MODE == "team" else give_user_access

    print("organization:", ORG)
    print("mode:", MODE)
    print("permission:", PERMISSION)
    print("repositories:", len(REPOS))
    print("-" * 50)

    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(action, repo) for repo in REPOS]
        for future in as_completed(futures):
            results.append(future.result())

    success_count = 0
    for repo, success, message in sorted(results):
        print(repo, "->", message[:300])
        if success:
            success_count += 1

    print("-" * 50)
    print("completed:", success_count, "/", len(REPOS))

if __name__ == "__main__":
    main()
