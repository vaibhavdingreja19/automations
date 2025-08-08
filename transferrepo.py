import os
import shutil
import subprocess

# === CONFIGURATION ===
GITHUB_PAT = "your_pat_token_here"

# Use HTTPS URLs with PAT for authentication
SOURCE_REPO = "https://{token}@github.com/JHOrg/JH_sasrem_automation.git".format(token=GITHUB_PAT)
DEST_REPO = "https://{token}@github.com/JHOrg/JH_REM_DEVOPS_AUTOMATION.git".format(token=GITHUB_PAT)

SOURCE_FOLDER_NAME = "JH_sasrem_automation"
DEST_FOLDER_NAME = "JH_REM_DEVOPS_AUTOMATION"

FOLDER_TO_MOVE = "sasrem_automations"
DEST_SUBDIR = os.path.join("TeamCity", "powershell", FOLDER_TO_MOVE)

# === CLEANUP OLD CLONES ===
for folder in [SOURCE_FOLDER_NAME, DEST_FOLDER_NAME]:
    if os.path.exists(folder):
        shutil.rmtree(folder)

# === CLONE BOTH REPOS ===
subprocess.run(["git", "clone", SOURCE_REPO, SOURCE_FOLDER_NAME], check=True)
subprocess.run(["git", "clone", DEST_REPO, DEST_FOLDER_NAME], check=True)

# === COPY FOLDER STRUCTURE ===
src_path = os.path.join(SOURCE_FOLDER_NAME, FOLDER_TO_MOVE)
dest_path = os.path.join(DEST_FOLDER_NAME, DEST_SUBDIR)

os.makedirs(os.path.dirname(dest_path), exist_ok=True)
shutil.copytree(src_path, dest_path)

# === GIT COMMIT AND PUSH ===
os.chdir(DEST_FOLDER_NAME)
subprocess.run(["git", "add", DEST_SUBDIR], check=True)
subprocess.run(["git", "commit", "-m", f"Moved {FOLDER_TO_MOVE} from {SOURCE_FOLDER_NAME}"], check=True)
subprocess.run(["git", "push"], check=True)

print("✅ Folder moved and pushed successfully.")
