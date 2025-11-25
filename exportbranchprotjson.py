import requests
import json

# ==== CONFIGURE THESE ====
PAT = "YOUR_PAT_HERE"
ORG = "JHDevOps"
REPO = "your-repo-name"
BRANCH = "main"      # change if needed
OUTPUT_FILE = f"{REPO}_{BRANCH}_protection.json"
# ==========================

url = f"https://api.github.com/repos/{ORG}/{REPO}/branches/{BRANCH}/protection"

headers = {
    "Authorization": f"token {PAT}",
    "Accept": "application/vnd.github.v3+json"
}

response = requests.get(url, headers=headers)

if response.status_code == 200:
    data = response.json()

    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=4)

    print(f"[✔] Branch protection exported to: {OUTPUT_FILE}")

elif response.status_code == 404:
    print("[!] Branch not protected or repo/branch not found.")
    print("    GitHub returns 404 if branch has no protection.")
else:
    print(f"[!] Error: {response.status_code}")
    print(response.text)
