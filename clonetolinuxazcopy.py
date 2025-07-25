import os
import pandas as pd
import subprocess
import concurrent.futures
import threading
import time
from datetime import datetime
import shutil

INPUT_FILE = "repo_batches_under_70GB.xlsx"
CLONE_WORKERS = 30
ZIP_WORKERS = 10
RETRY_LIMIT = 3
GITHUB_PAT = os.getenv('GITHUB_PAT')
ORG_NAME = "JHDevOps"

AZCOPY_PATH = os.getenv('AZCOPY_PATH')
AZURE_STORAGE_URL = os.getenv('AZURE_STORAGE_URL')
SAS_TOKEN = os.getenv('AZSAS')

date_folder = "odd" if datetime.now().day % 2 != 0 else "even"
if not os.path.exists(date_folder):
    os.makedirs(date_folder)

print_lock = threading.Lock()

# Shared thread pool for zipping
zip_executor = concurrent.futures.ThreadPoolExecutor(max_workers=ZIP_WORKERS)

def clone_and_zip(repo_name):
    repo_url = f"https://{GITHUB_PAT}@github.com/{ORG_NAME}/{repo_name}.git"
    dest_dir = os.path.join(date_folder, repo_name)

    for attempt in range(1, RETRY_LIMIT + 1):
        with print_lock:
            print(f"[INFO] Cloning '{repo_name}' (Attempt {attempt})...", flush=True)

        cmd = ["git", "clone", "--mirror", repo_url, dest_dir]

        try:
            subprocess.run(cmd, check=True)
            with print_lock:
                print(f"[SUCCESS] Cloned '{repo_name}' successfully.", flush=True)
            
            # Immediately submit zipping after successful clone
            zip_executor.submit(zip_repo, repo_name)
            return True
        except subprocess.CalledProcessError:
            with print_lock:
                print(f"[ERROR] Failed to clone '{repo_name}' on attempt {attempt}. Retrying...", flush=True)
            time.sleep(2)

    with print_lock:
        print(f"[SKIPPED] Skipping '{repo_name}' after {RETRY_LIMIT} failed attempts.", flush=True)
    return False

def zip_repo(repo_name):
    repo_path = os.path.join(date_folder, repo_name)
    zip_path = os.path.join(date_folder, f"{repo_name}.zip")

    with print_lock:
        print(f"[INFO] Zipping '{repo_name}'...", flush=True)

    shutil.make_archive(repo_path, 'zip', repo_path)
    shutil.rmtree(repo_path)

    with print_lock:
        print(f"[INFO] Zipped '{repo_name}' and removed original folder.", flush=True)

def upload_zip_files_to_azure():
    try:
        folder_name = date_folder
        current_directory = os.getcwd()
        target_folder = os.path.join(current_directory, folder_name)

        if not os.path.exists(target_folder):
            print(f"[WARNING] Target folder '{target_folder}' does not exist!")
            return

        azure_target_folder = folder_name
        destination_url = f"{AZURE_STORAGE_URL}/{azure_target_folder}?{SAS_TOKEN}"

        print(f"[UPLOAD] Uploading .zip files from '{target_folder}' to Azure folder '{azure_target_folder}'...")

        command = (
            f'"{AZCOPY_PATH}" copy "{os.path.join(target_folder, "*.zip")}" "{destination_url}" --recursive=true'
        )
        
        print(f"[COMMAND] {command}")
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)

        print("[UPLOAD] Upload successful!")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("[ERROR] Error during upload:")
        print(e.stderr)
    except Exception as ex:
        print(f"[ERROR] Unexpected error occurred: {ex}")

def process_batch(batch_df):
    repo_names = batch_df["name"].tolist()

    with concurrent.futures.ThreadPoolExecutor(max_workers=CLONE_WORKERS) as executor:
        executor.map(clone_and_zip, repo_names)

def main():
    with print_lock:
        print(f"[START] Cloning will happen inside '{date_folder}' folder.\n", flush=True)

    xls = pd.ExcelFile(INPUT_FILE, engine='openpyxl')
    for sheet_name in xls.sheet_names:
        with print_lock:
            print(f"[BATCH] Starting clones for '{sheet_name}'...\n", flush=True)

        batch_df = pd.read_excel(INPUT_FILE, sheet_name=sheet_name, engine='openpyxl')
        process_batch(batch_df)

        with print_lock:
            print(f"[UPLOAD] Uploading zipped files to Azure before next batch...\n", flush=True)
        upload_zip_files_to_azure()

        with print_lock:
            print(f"[WAIT] Sleeping for 5 minutes before next batch...\n", flush=True)
        time.sleep(300)

    # Wait for all pending zips to complete
    zip_executor.shutdown(wait=True)

    with print_lock:
        print(f"[COMPLETE] All batches processed.", flush=True)

if __name__ == "__main__":
    main()
