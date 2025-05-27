import os
import shutil
import zipfile
import subprocess
import concurrent.futures
import pandas as pd
from pathlib import Path
from datetime import datetime


EXCEL_FILE = "repo_batches_under_70GB.xlsx"
GITHUB_PAT = os.getenv()
ORG_NAME = "JHDevOps"
MAX_WORKERS = 30  

today = datetime.today().day
base_dir_name = "cloned_repos_odd" if today % 2 != 0 else "cloned_repos_even"
BASE_DIR = Path(base_dir_name)
BASE_DIR.mkdir(parents=True, exist_ok=True)


def clone_repo(repo_name, batch_dir):
    clone_path = batch_dir / repo_name
    repo_url = f"https://{GITHUB_PAT}@github.com/{ORG_NAME}/{repo_name}.git"
    print(f"🔄 START clone: {repo_name}")
    try:
        result = subprocess.run(
            ["git", "clone", "--mirror", repo_url, str(clone_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=2000  
        )
        print(f"✅ DONE clone: {repo_name}")
        return repo_name, True
    except subprocess.TimeoutExpired:
        print(f"⏱️ TIMEOUT cloning {repo_name}")
        return repo_name, False
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR cloning {repo_name}\nSTDERR:\n{e.stderr.decode(errors='ignore')}")
        return repo_name, False


def zip_repo_folder(repo_name, batch_dir):
    repo_path = batch_dir / repo_name
    zip_path = batch_dir / f"{repo_name}.zip"
    print(f"📦 START zip: {repo_name}")
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(repo_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, repo_path)
                    zipf.write(full_path, arcname=os.path.join(repo_name, rel_path))
        print(f"✅ DONE zip: {repo_name}")
        return repo_name, True
    except Exception as e:
        print(f"❌ ERROR zipping {repo_name}: {e}")
        return repo_name, False


def delete_folder(repo_name, batch_dir):
    repo_path = batch_dir / repo_name
    print(f"🧹 START delete: {repo_name}")
    try:
        shutil.rmtree(repo_path, ignore_errors=True)
        print(f"✅ DONE delete: {repo_name}")
        return repo_name, True
    except Exception as e:
        print(f"❌ ERROR deleting {repo_name}: {e}")
        return repo_name, False


def process_batch(sheet_name):
    print(f"\n🚀 Processing {sheet_name}...")
    df = pd.read_excel(EXCEL_FILE, sheet_name=sheet_name)
    repo_names = df["name"].tolist()

    batch_dir = BASE_DIR  

    
    print(f"🔁 Cloning {len(repo_names)} repos...")
    failed_repos = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(executor.map(lambda r: clone_repo(r, batch_dir), repo_names))

    
    failed_repos = [name for name, success in results if not success]

    
    if failed_repos:
        print(f"⚠️ {len(failed_repos)} repos failed to clone. Retrying one-by-one...")
        still_failed = []
        for repo in failed_repos:
            _, success = clone_repo(repo, batch_dir)
            if not success:
                still_failed.append(repo)

        if still_failed:
            print(f"❌ Failed to clone the following repos after retry: {still_failed}")
        else:
            print(f"✅ All previously failed repos cloned successfully on retry.")

    else:
        print(f"✅ All {len(repo_names)} repos cloned successfully.")

    
    print(f"📦 Zipping cloned repos...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        list(executor.map(lambda r: zip_repo_folder(r, batch_dir), repo_names))

    
    print(f"🧹 Deleting original cloned folders...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        list(executor.map(lambda r: delete_folder(r, batch_dir), repo_names))

    print(f"✅ Finished {sheet_name}\n")


def main():
    xls = pd.ExcelFile(EXCEL_FILE)
    sheet_names = xls.sheet_names

    print(f"📁 Base directory for this run: {BASE_DIR.resolve()}")
    for sheet in sheet_names:
        process_batch(sheet)


if __name__ == "__main__":
    main()
