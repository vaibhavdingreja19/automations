import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import time

def zip_folder(folder_path, output_dir):
    try:
        folder_name = os.path.basename(folder_path)
        zip_file_path = os.path.join(output_dir, f"{folder_name}.zip")

        print(f"Zipping folder: {folder_path} into {zip_file_path}")

        with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, folder_path)
                    zipf.write(file_path, arcname)

        print(f"Folder {folder_name} zipped successfully.")
    except Exception as e:
        print(f"An error occurred while zipping {folder_path}: {e}")

def zip_folders_in_directory_concurrent(directory_path, num_workers=30, batch_size=200, sleep_seconds=120):
    output_dir = directory_path
    folders_to_zip = [
        os.path.join(directory_path, folder_name)
        for folder_name in os.listdir(directory_path)
        if os.path.isdir(os.path.join(directory_path, folder_name))
    ]

    for i in range(0, len(folders_to_zip), batch_size):
        batch = folders_to_zip[i:i + batch_size]
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            executor.map(zip_folder, batch, [output_dir] * len(batch))
        if i + batch_size < len(folders_to_zip):
            print(f"Sleeping for {sleep_seconds} seconds before next batch...")
            time.sleep(sleep_seconds)

if __name__ == "__main__":
    current_directory = os.getcwd()
    current_day = datetime.now().day
    folder_name = "cloned_repos_odd" if current_day % 2 != 0 else "cloned_repos_even"
    directory_to_zip = os.path.join(current_directory, folder_name)

    if not os.path.exists(directory_to_zip):
        print(f"Directory '{directory_to_zip}' does not exist!")
    else:
        print(f"Zipping folders in the directory: {directory_to_zip}")
        zip_folders_in_directory_concurrent(directory_to_zip, num_workers=30, batch_size=200, sleep_seconds=120)
