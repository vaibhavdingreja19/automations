import os
import zipfile

def zip_folder(folder_path):
    # Get the absolute path and folder name
    folder_path = os.path.abspath(folder_path)
    folder_name = os.path.basename(folder_path)
    zip_filename = f"{folder_name}.zip"

    # Create the zip file in the current directory
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                abs_file_path = os.path.join(root, file)
                # Add file to zip with relative path
                rel_path = os.path.relpath(abs_file_path, start=folder_path)
                zipf.write(abs_file_path, arcname=os.path.join(folder_name, rel_path))

    print(f"Folder zipped successfully into '{zip_filename}'")

# Example usage:
zip_folder("path/to/your/folder")
