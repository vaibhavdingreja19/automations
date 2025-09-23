import base64
import requests
import os

# ==== USER INPUTS ====
GITHUB_TOKEN = os.getenv("GITHUB_PAT")  # store token in env var
REPO = "JHDevOps/DIME_LIFE"             # org/repo
BRANCH = "feature/VINTF-8836"           # branch
TARGET_PATH = "JHIM_LIFE/UNIX/CODE/SCRIPTS/MarketoAdapterMagiclink.jar"  
LOCAL_FILE = "MarketoAdapterMagiclink.jar"
COMMIT_MESSAGE = "Add large file via API"

# ==== SCRIPT ====
def upload_file():
    with open(LOCAL_FILE, "rb") as f:
        content = f.read()
    b64_content = base64.b64encode(content).decode("utf-8")

    url = f"https://api.github.com/repos/{REPO}/contents/{TARGET_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    # Step 1: Check if file already exists
    response = requests.get(url, headers=headers, params={"ref": BRANCH})
    if response.status_code == 200:
        sha = response.json()["sha"]
        print(f"ℹ️ File already exists in repo. Updating it (sha={sha})...")
    else:
        sha = None
        print("ℹ️ File does not exist. Creating new one...")

    # Step 2: Upload (create or update)
    data = {
        "message": COMMIT_MESSAGE,
        "branch": BRANCH,
        "content": b64_content,
    }
    if sha:
        data["sha"] = sha  # required for updating

    put_response = requests.put(url, headers=headers, json=data)

    if put_response.status_code in [200, 201]:
        print("✅ File uploaded successfully!")
        print("GitHub URL:", put_response.json()["content"]["html_url"])
    else:
        print("❌ Upload failed:", put_response.status_code, put_response.text)


if __name__ == "__main__":
    upload_file()
