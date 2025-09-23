# push_with_lfs.py
import os, shutil, subprocess, tempfile, sys
from pathlib import Path

# --------- inputs ----------
REPO = "JHDevOps/DIME_LIFE"                     # org/repo
BRANCH = "feature/VINTF-8836"                   # branch to push to
TARGET_PATH_IN_REPO = "JHIM_LIFE/UNIX/CODE/SCRIPTS/MarketoAdapterMagiclink.jar"
LOCAL_FILE = r"C:\Users\dingrva\teamcity_automation\MarketoAdapterMagiclink.jar"

# Use SSH by default. If you prefer PAT over HTTPS, set:
# REMOTE = f"https://<TOKEN>@github.com/{REPO}.git"
REMOTE = f"git@github.com:{REPO}.git"
COMMIT_MESSAGE = f"Add {Path(TARGET_PATH_IN_REPO).name} via LFS"

# --------- helpers ----------
def run(cmd, cwd=None):
    print(f"$ {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stdout)
        print(res.stderr)
        sys.exit(res.returncode)
    return res.stdout.strip()

# --------- main ----------
def main():
    if not Path(LOCAL_FILE).exists():
        print(f"Local file not found: {LOCAL_FILE}")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp, "repo")
        # 1) clone the repo and checkout the branch
        run(["git", "clone", "--branch", BRANCH, "--depth", "1", REMOTE, str(repo_dir)])

        # 2) ensure git lfs is installed & initialized
        run(["git", "lfs", "install"], cwd=repo_dir)

        # 3) track the file type in LFS (by extension)
        ext = Path(LOCAL_FILE).suffix or Path(TARGET_PATH_IN_REPO).suffix
        if ext:
            pattern = f"*{ext}"
            run(["git", "lfs", "track", pattern], cwd=repo_dir)
        else:
            # fallback: track this exact path
            run(["git", "lfs", "track", TARGET_PATH_IN_REPO], cwd=repo_dir)

        # 4) copy file into target path
        dest = repo_dir / TARGET_PATH_IN_REPO
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(LOCAL_FILE, dest)

        # 5) add, commit, push
        run(["git", "add", ".gitattributes", TARGET_PATH_IN_REPO], cwd=repo_dir)
        # create branch if it didn't exist (clone would fail if it didn't; but safe guard)
        run(["git", "checkout", "-B", BRANCH], cwd=repo_dir)
        run(["git", "commit", "-m", COMMIT_MESSAGE], cwd=repo_dir)
        run(["git", "push", "origin", BRANCH], cwd=repo_dir)

        print("✅ Pushed via Git LFS successfully.")

if __name__ == "__main__":
    main()
