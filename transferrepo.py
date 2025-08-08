import os
import shutil
import subprocess

# === SET YOUR GITHUB PERSONAL ACCESS TOKEN (PAT) HERE ===
GITHUB_PAT = "your_pat_token_here"  # 👈 Replace this only!

# === NO OTHER CHANGES NEEDED ===
SOURCE_REPO = f"https://{GITHUB_PAT}@github.com/JHDevOps/JH_sasrem_automation.git"
DEST_REPO = f"https://{GITHUB_PAT}@github.com/JHDevOps/JH_REM_DEVOPS_AUTOMATION.git"

SOURCE_FOLDER_NAME = "JH_sasrem_automation"
DEST_FOLDER_NAME = "JH_REM_DEVOPS_AUTOMATION"
FOLDER_TO_MOVE = "sasrem_automations"
DEST_SUBDIR = os.path.join("TeamCity", "powershell", FOLDER_TO_MOVE)

# === CLEAN UP ANY PREVIOUS RUN ===
for folder in [SOURCE_FOLDER_NAME, DEST_FOLDER_NAME]:
    if os.path.exists(folder):
        print(f"🧹 Deleting old folder: {folder}")
        shutil.rmtree(folder)

# === CLONE BOTH REPOS ===
print("🔁 Cloning source repo...")
subprocess.run(["git", "clone", SOURCE_REPO, SOURCE_FOLDER_NAME], check=True)

print("🔁 Cloning destination repo...")
subprocess.run(["git", "clone", DEST_REPO, DEST_FOLDER_NAME], check=True)

# === CHECK IF FOLDER EXISTS ===
src_path = os.path.join(SOURCE_FOLDER_NAME, FOLDER_TO_MOVE)
dest_path = os.path.join(DEST_FOLDER_NAME, DEST_SUBDIR)

if not os.path.exists(src_path):
    raise FileNotFoundError(f"❌ The folder '{FOLDER_TO_MOVE}' does not exist in {SOURCE_FOLDER_NAME}.\nPath checked: {src_path}")

# === COPY FOLDER ===
print(f"📂 Copying {FOLDER_TO_MOVE} to destination repo...")
os.makedirs(os.path.dirname(dest_path), exist_ok=True)
shutil.copytree(src_path, dest_path)

# === COMMIT & PUSH TO DEST REPO ===
print("💾 Committing and pushing to destination repo...")
os.chdir(DEST_FOLDER_NAME)
subprocess.run(["git", "add", DEST_SUBDIR], check=True)
subprocess.run(["git", "commit", "-m", f"Moved {FOLDER_TO_MOVE} from source repo"], check=True)
subprocess.run(["git", "push"], check=True)

print("✅ Done! Folder transferred and pushed to GitHub.")
