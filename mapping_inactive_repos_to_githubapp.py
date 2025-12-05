import pandas as pd

# ---------------- CONFIG ----------------
APPS_FILE = "GitHub_Apps_Repositories.xlsx"      # workbook 1 (8 sheets)
INACTIVE_FILE = "inactive_repos_graphql.xlsx"    # workbook 2 (inactive repos)
OUTPUT_FILE = "inactive_repos_with_app.xlsx"     # new file with column 4

# Column name in apps workbook that holds repo full name (e.g. 'JHDevOps/repo')
APPS_REPO_COL = "Repository Name"   # or "RepositoryName" depending on your sheet
# Column name in inactive workbook that holds repo name (e.g. 'repo')
INACTIVE_REPO_COL = "Repository"
# ---------------------------------------


def build_repo_to_app_map():
    """
    Read APPS_FILE and build a mapping:
        repo_name_without_org -> [list of app (sheet) names]
    Example key: 'Amazon_connect'
    Example value: ['JHDevOps_App1', 'JHDevOps_App3']
    """
    xls = pd.ExcelFile(APPS_FILE)
    repo_to_apps = {}

    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)

        # Try to be tolerant about column name
        col_candidates = [APPS_REPO_COL, "RepositoryName", "Repository", "Repository Name"]
        col = None
        for c in col_candidates:
            if c in df.columns:
                col = c
                break

        if col is None:
            print(f"Warning: No repository column found in sheet '{sheet_name}', skipping.")
            continue

        for full_name in df[col].dropna():
            # full_name might be 'JHDevOps/repo_name'
            full_name = str(full_name).strip()
            if "/" in full_name:
                _, repo_name = full_name.split("/", 1)
            else:
                repo_name = full_name

            repo_name = repo_name.strip()

            if not repo_name:
                continue

            repo_to_apps.setdefault(repo_name, set()).add(sheet_name)

    # convert sets to sorted strings like 'App1; App2'
    repo_to_apps_str = {
        repo: "; ".join(sorted(apps))
        for repo, apps in repo_to_apps.items()
    }
    return repo_to_apps_str


def main():
    # Build mapping from repo -> apps
    repo_to_apps = build_repo_to_app_map()
    print(f"Total repos found across apps workbook: {len(repo_to_apps)}")

    # Load inactive repos file
    df_inactive = pd.read_excel(INACTIVE_FILE)

    if INACTIVE_REPO_COL not in df_inactive.columns:
        raise SystemExit(f"Column '{INACTIVE_REPO_COL}' not found in {INACTIVE_FILE}")

    # For each inactive repo row, look up app(s)
    app_column_values = []
    for repo in df_inactive[INACTIVE_REPO_COL]:
        repo_str = str(repo).strip()
        app_column_values.append(repo_to_apps.get(repo_str, ""))

    # Insert new column as 4th column (index 3)
    df_inactive.insert(
        3,  # position (0-based) -> 4th column
        "GitHub App",   # new column name
        app_column_values
    )

    # Save to new file
    df_inactive.to_excel(OUTPUT_FILE, index=False)
    print(f"Done. Saved mapped file to '{OUTPUT_FILE}'")


if __name__ == "__main__":
    main()
