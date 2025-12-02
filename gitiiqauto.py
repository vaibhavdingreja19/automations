import os
import sys
import base64
import argparse
from urllib.parse import urlparse
import requests

API_ROOT = "https://api.github.com"


def github_headers(pat: str):
    return {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github+json",
    }


def parse_repo_from_url(repo_url: str):
    """
    Convert https://github.com/JHDevOps/my-repo.git
    -> owner: JHDevOps, repo: my-repo
    """
    parsed = urlparse(repo_url)
    if "github.com" not in parsed.netloc:
        raise ValueError(f"Not a GitHub URL: {repo_url}")

    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]

    parts = path.split("/")
    if len(parts) != 2:
        raise ValueError(f"Could not parse owner/repo from: {repo_url}")

    owner, repo = parts
    return owner, repo


def get_existing_file_sha(owner, repo, path, branch, pat):
    url = f"{API_ROOT}/repos/{owner}/{repo}/contents/{path}"
    params = {"ref": branch}
    r = requests.get(url, headers=github_headers(pat), params=params)

    if r.status_code == 200:
        return r.json().get("sha")
    elif r.status_code == 404:
        return None
    else:
        raise RuntimeError(
            f"Error getting existing file info: {r.status_code} {r.text}"
        )


def upload_file(owner, repo, branch, local_file, remote_path, pat, message):
    if not os.path.exists(local_file):
        raise FileNotFoundError(f"Local file not found: {local_file}")

    with open(local_file, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode("utf-8")

    sha = get_existing_file_sha(owner, repo, remote_path, branch, pat)

    url = f"{API_ROOT}/repos/{owner}/{repo}/contents/{remote_path}"

    payload = {
        "message": message,
        "content": content_b64,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha  # update existing file

    r = requests.put(url, headers=github_headers(pat), json=payload)

    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Error uploading file: {r.status_code} {r.text}"
        )
    else:
        print(f"File uploaded successfully to {owner}/{repo}@{branch}:{remote_path}")
        print(f"GitHub response: {r.status_code}")


def main():
    parser = argparse.ArgumentParser(
        description="Upload github_acl_access.xlsx to GitHub via API"
    )
    parser.add_argument(
        "--repo-url",
        required=True,
        help="GitHub repo HTTPS URL, e.g. https://github.com/JHDevOps/my-repo.git",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="Branch name to commit to (default: main)",
    )
    parser.add_argument(
        "--local-file",
        default="github_acl_access.xlsx",
        help="Local path to the Excel file (default: github_acl_access.xlsx)",
    )
    parser.add_argument(
        "--remote-path",
        required=True,
        help="Path inside the repo where file should be stored, "
             "e.g. reports/github_acl_access.xlsx",
    )
    parser.add_argument(
        "--commit-message",
        default="Update GitHub ACL access report from TeamCity",
        help="Commit message for the upload",
    )
    args = parser.parse_args()

    pat = os.environ.get("GITHUB_PAT")
    if not pat:
        print("ERROR: GITHUB_PAT environment variable is not set.")
        sys.exit(1)

    owner, repo = parse_repo_from_url(args.repo_url)

    upload_file(
        owner=owner,
        repo=repo,
        branch=args.branch,
        local_file=args.local_file,
        remote_path=args.remote_path,
        pat=pat,
        message=args.commit_message,
    )


if __name__ == "__main__":
    main()
