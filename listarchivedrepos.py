# -*- coding: utf-8 -*-
"""
List all archived repositories in a GitHub org and export to Excel.

Requirements:
    pip install requests pandas openpyxl
Works in Spyder: paste/run, then enter your PAT when prompted.
"""

import math
import time
import requests
import pandas as pd
from getpass import getpass

ORG = "JHDevOps"
OUTPUT_XLSX = f"{ORG}_archived_repos.xlsx"

API_BASE = "https://api.github.com"


def gh_get(session, url, params=None, retries=3):
    """GET with basic retry + rate limit handling."""
    for attempt in range(1, retries + 1):
        r = session.get(url, params=params, timeout=30)

        # Rate limit handling
        if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
            reset = int(r.headers.get("X-RateLimit-Reset", "0"))
            sleep_for = max(0, reset - int(time.time())) + 2
            print(f"[Rate limit] Sleeping {sleep_for}s until reset...")
            time.sleep(sleep_for)
            continue

        # Transient errors
        if r.status_code in (502, 503, 504):
            backoff = 2 ** attempt
            print(f"[Transient {r.status_code}] retrying in {backoff}s...")
            time.sleep(backoff)
            continue

        r.raise_for_status()
        return r

    raise RuntimeError(f"Failed after {retries} retries: {url}")


def fetch_all_org_repos(org, session):
    """
    Fetch all repos from org (public/private/internal if PAT allows).
    Uses REST pagination with per_page=100.
    """
    repos = []
    page = 1
    per_page = 100

    while True:
        url = f"{API_BASE}/orgs/{org}/repos"
        params = {"type": "all", "per_page": per_page, "page": page}
        r = gh_get(session, url, params=params)
        batch = r.json()

        if not batch:
            break

        repos.extend(batch)
        print(f"Fetched page {page} ({len(batch)} repos)")
        page += 1

    return repos


def main():
    print("GitHub Org:", ORG)
    pat = getpass("Paste your GitHub PAT (input hidden): ").strip()
    if not pat:
        raise ValueError("No PAT provided.")

    session = requests.Session()
    session.headers.update({
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github+json",
        # Optional, but helps GitHub identify your client:
        "User-Agent": "JHDevOps-archived-repo-exporter"
    })

    # Quick auth check (and shows who you authenticated as)
    me = gh_get(session, f"{API_BASE}/user").json()
    print("Authenticated as:", me.get("login"))

    all_repos = fetch_all_org_repos(ORG, session)

    archived = [repo for repo in all_repos if repo.get("archived") is True]
    print(f"\nTotal repos: {len(all_repos)}")
    print(f"Archived repos: {len(archived)}")

    rows = []
    for repo in archived:
        rows.append({
            "name": repo.get("name"),
            "full_name": repo.get("full_name"),
            "visibility": repo.get("visibility"),      # public/private/internal (when available)
            "private": repo.get("private"),
            "archived": repo.get("archived"),
            "disabled": repo.get("disabled"),
            "fork": repo.get("fork"),
            "default_branch": repo.get("default_branch"),
            "created_at": repo.get("created_at"),
            "updated_at": repo.get("updated_at"),
            "pushed_at": repo.get("pushed_at"),
            "size_kb": repo.get("size"),
            "open_issues_count": repo.get("open_issues_count"),
            "license": (repo.get("license") or {}).get("spdx_id"),
            "html_url": repo.get("html_url"),
            "description": repo.get("description"),
        })

    df = pd.DataFrame(rows)

    # Sort nicely (optional)
    if not df.empty and "updated_at" in df.columns:
        df = df.sort_values(by=["updated_at", "full_name"], ascending=[False, True])

    # Export to Excel
    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="archived_repos", index=False)

        # Auto-fit-ish column widths (simple heuristic)
        ws = writer.sheets["archived_repos"]
        for col_cells in ws.columns:
            max_len = 0
            col_letter = col_cells[0].column_letter
            for cell in col_cells:
                val = "" if cell.value is None else str(cell.value)
                max_len = max(max_len, len(val))
            ws.column_dimensions[col_letter].width = min(60, max(12, max_len + 2))

    print(f"\nSaved: {OUTPUT_XLSX}")


if __name__ == "__main__":
    main()
