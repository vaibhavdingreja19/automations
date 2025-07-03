import requests
import pandas as pd

# --------- CONFIGURATION ---------
GITHUB_PAT = "YOUR_PAT_HERE"   # Replace with your actual PAT
ORG_NAME = "JHDevOps"
OUTPUT_ALL = "all_repos.xlsx"
OUTPUT_SMALL = "small_repos.xlsx"
OUTPUT_LARGE = "large_repos.xlsx"
SIZE_THRESHOLD_MB = 200
# ----------------------------------

headers = {
    "Authorization": f"token {GITHUB_PAT}",
    "Accept": "application/vnd.github+json"
}

repos = []
page = 1

print("[INFO] Fetching repositories from GitHub...")

while True:
    url = f"https://api.github.com/orgs/{ORG_NAME}/repos?per_page=100&page={page}"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"[ERROR] Failed to fetch repos: {response.status_code} - {response.text}")
        break

    data = response.json()
    if not data:
        break

    for repo in data:
        repos.append({
            "Name": repo['name'],
            "Full Name": repo['full_name'],
            "Private": repo['private'],
            "Size (MB)": round(repo['size'] / 1024, 2),  # Size is in KB by API
            "URL": repo['html_url']
        })

    page += 1

print(f"[INFO] Total repositories fetched: {len(repos)}")

# Create DataFrame
df = pd.DataFrame(repos)

# Save all repos
df.to_excel(OUTPUT_ALL, index=False)
print(f"[INFO] Saved all repos to {OUTPUT_ALL}")

# Split by size
small_df = df[df["Size (MB)"] < SIZE_THRESHOLD_MB]
large_df = df[df["Size (MB)"] >= SIZE_THRESHOLD_MB]

# Save
small_df.to_excel(OUTPUT_SMALL, index=False)
large_df.to_excel(OUTPUT_LARGE, index=False)

print(f"[INFO] Saved {len(small_df)} small repos to {OUTPUT_SMALL}")
print(f"[INFO] Saved {len(large_df)} large repos to {OUTPUT_LARGE}")
print("[INFO] Script completed.")
