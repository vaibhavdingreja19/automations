import os
import pandas as pd
import subprocess
import concurrent.futures
import threading
import time
from datetime import datetime
import shutil


INPUT_FILE = "repo_batches_under_70GB.xlsx"
MAX_WORKERS = 30
RETRY_LIMIT = 3
GITHUB_PAT = os.getenv('GITHUB_PAT')
ORG_NAME = "JHDevOps"



date_folder = "odd" if datetime.now().day % 2 != 0 else "even"
if not os.path.exists(date_folder):
    os.makedirs(date_folder)


print_lock = threading.Lock()

def clone_repo(repo_name):
    repo_url = f"https://{GITHUB_PAT}@github.com/{ORG_NAME}/{repo_name}.git"
    dest_dir = os.path.join(date_folder, repo_name)

    for attempt in range(1, RETRY_LIMIT + 1):
        with print_lock:
            print(f"[INFO] Cloning '{repo_name}' (Attempt {attempt})...")

        cmd = ["git", "clone", "--mirror", repo_url, dest_dir]

        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with print_lock:
                print(f"[SUCCESS] Cloned '{repo_name}' successfully.")
            return True
        except subprocess.CalledProcessError:
            with print_lock:
                print(f"[ERROR] Failed to clone '{repo_name}' on attempt {attempt}. Retrying...")
            time.sleep(2)

    with print_lock:
        print(f"[SKIPPED] Skipping '{repo_name}' after {RETRY_LIMIT} failed attempts.")
    return False

def zip_repo(repo_name):
    repo_path = os.path.join(date_folder, repo_name)
    zip_path = os.path.join(date_folder, f"{repo_name}.zip")

    with print_lock:
        print(f"[INFO] Zipping '{repo_name}'...")

    shutil.make_archive(repo_path, 'zip', repo_path)
    shutil.rmtree(repo_path)

    with print_lock:
        print(f"[INFO] Zipped '{repo_name}' and removed original folder.")

def zip_all_repos_parallel(repo_names):
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        executor.map(zip_repo, repo_names)

def process_batch(batch_df):
    repo_names = batch_df["name"].tolist()

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        executor.map(clone_repo, repo_names)

    zip_all_repos_parallel(repo_names)

def main():
    with print_lock:
        print(f"[START] Cloning will happen inside '{date_folder}' folder.\n")

    xls = pd.ExcelFile(INPUT_FILE, engine='openpyxl')
    for sheet_name in xls.sheet_names:
        with print_lock:
            print(f"[BATCH] Starting clones for '{sheet_name}'...")

        batch_df = pd.read_excel(INPUT_FILE, sheet_name=sheet_name, engine='openpyxl')
        process_batch(batch_df)

        with print_lock:
            print(f"[WAIT] Sleeping for 5 minutes before next batch...\n")
        time.sleep(300)

    with print_lock:
        print(f"[COMPLETE] All batches processed.")

if __name__ == "__main__":
    main()
