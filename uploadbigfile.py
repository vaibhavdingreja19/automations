import base64
import requests
import os

# ==== USER INPUTS ====
GITHUB_TOKEN = os.getenv("GITHUB_PAT")  # store your PAT in an env variable for safety
REPO = "JHDevOps/gltc_care"             # org/repo
BRANCH = "main"                         # branch where to upload
TARGET_PATH = "uploads/testfile.zip"    # path inside repo
LOCAL_FILE = "/path/to/your/local/file.zip"  # path on your system
COMMIT_MESSAGE = "Add large file via API"

# ==== SCRIPT ====
def upload_file():
    with open(LOCAL_FILE, "rb") as f:
        content = f.read()
    b64_content = base64.b64encode(content).decode("utf-8")

    url = f"https://api.github.com/repos/{REPO}/contents/{TARGET_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    data = {
        "message": COMMIT_MESSAGE,
        "branch": BRANCH,
        "content": b64_content
    }

    response = requests.put(url, headers=headers, json=data)

    if response.status_code in [200, 201]:
        print("✅ File uploaded successfully!")
        print("GitHub URL:", response.json()["content"]["html_url"])
    else:
        print("❌ Upload failed:", response.status_code, response.text)


if __name__ == "__main__":
    upload_file()
