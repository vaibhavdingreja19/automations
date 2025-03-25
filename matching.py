import os
import requests
import datetime
import pandas as pd
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# GitHub details
GITHUB_ORG = "JHDevOps"
GITHUB_PAT = os.getenv("GITHUB_PAT")  # Store your GitHub PAT in an environment variable
GITHUB_API_URL = f"https://api.github.com/orgs/{GITHUB_ORG}/repos"

# Azure details
AZURE_STORAGE_ACCOUNT = os.getenv("AZURE_STORAGE_ACCOUNT")  # Your Azure Storage Account Name
AZURE_CONTAINER = "github-backup"
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")

# Determine which folder to use
today = datetime.datetime.today()
folder_name = "cloned_repos_even" if today.day % 2 == 0 else "cloned_repos_odd"

# Authenticate to Azure using SPN
def get_blob_service_client():
    credential_url = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": AZURE_CLIENT_ID,
        "client_secret": AZURE_CLIENT_SECRET,
        "resource": f"https://{AZURE_STORAGE_ACCOUNT}.blob.core.windows.net"
    }
    response = requests.post(credential_url, data=payload)
    response.raise_for_status()
    token = response.json()["access_token"]
    
    return BlobServiceClient(
        f"https://{AZURE_STORAGE_ACCOUNT}.blob.core.windows.net",
        credential=token
    )

# Get list of repositories from GitHub
def get_github_repos():
    headers = {"Authorization": f"token {GITHUB_PAT}"}
    response = requests.get(GITHUB_API_URL, headers=headers)
    response.raise_for_status()
    return [repo["name"] for repo in response.json()]

# Get latest ZIP file for a repo
def get_latest_backup_url(blob_service_client, repo_name):
    container_client = blob_service_client.get_container_client(AZURE_CONTAINER)
    blobs = list(container_client.list_blobs(name_starts_with=f"{folder_name}/{repo_name}"))
    
    if not blobs:
        return "No backup found"
    
    # Sort blobs by last modified date (latest first)
    latest_blob = sorted(blobs, key=lambda b: b.last_modified, reverse=True)[0]
    return f"https://{AZURE_STORAGE_ACCOUNT}.blob.core.windows.net/{AZURE_CONTAINER}/{latest_blob.name}"

# Main logic
def main():
    blob_service_client = get_blob_service_client()
    repos = get_github_repos()
    
    data = []
    for repo in repos:
        backup_url = get_latest_backup_url(blob_service_client, repo)
        data.append([repo, backup_url])

    # Save data to Excel
    df = pd.DataFrame(data, columns=["Repository Name", "Backup URL"])
    df.to_excel("github_backup_report.xlsx", index=False)
    print("Report generated: github_backup_report.xlsx")

if __name__ == "__main__":
    main()
