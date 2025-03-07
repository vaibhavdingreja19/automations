import requests
import re
import pandas as pd

# GitHub organization and personal access token
ORG_NAME = "JHDevOps"
GITHUB_PAT = ""  # Replace with your PAT

# GitHub API headers
HEADERS = {
    "Authorization": f"token {GITHUB_PAT}",
    "Accept": "application/vnd.github.v3+json"
}

# Common secret patterns (AWS, Azure, etc.)
SECRET_PATTERNS = [
    # AWS Secrets
    r"(AWS|aws)_?(SECRET|secret|ACCESS|access|KEY|key)[=: ]+['\"]?[A-Za-z0-9/+=]{16,}",
    # General API keys
    r"(API|api|CLIENT|client|SECRET|secret|TOKEN|token|KEY|key)[=: ]+['\"]?[A-Za-z0-9/+=-]{16,}",
    # Passwords
    r"(PASSWORD|password|PASS|pass|PWD|pwd)[=: ]+['\"]?[A-Za-z0-9/+=]{8,}",
    # GitHub Token
    r"ghp_[A-Za-z0-9]{36}",
    # Stripe Secret Key
    r"sk_live_[0-9a-zA-Z]{24}",
    # Google API Key
    r"AIza[0-9A-Za-z-_]{35}",
    # Facebook Access Token
    r"EAACEdEose0cBA[0-9A-Za-z]+",
    
    # Azure Secrets
    r"AZURE_SUBSCRIPTION_KEY[=: ]+['\"]?[0-9a-f]{32}['\"]?",
    r"(?:AccountKey=|azure_storage_key=|AZURE_STORAGE_KEY[=: ]+)['\"]?[A-Za-z0-9+/=]{88}['\"]?",
    r"sv=[0-9]{4}-[0-9]{2}-[0-9]{2}&ss=[a-z]+&srt=[a-z]+&sp=[a-z]+&se=[0-9]+T[0-9]+Z&st=[0-9]+T[0-9]+Z&spr=https&sig=[a-zA-Z0-9%]+",
    r"AI[a-zA-Z0-9]{32,}",
    r"(AZURE|azure|AAD|aad|CLIENT|client)_?(SECRET|secret)[=: ]+['\"]?[A-Za-z0-9/+=-]{16,}['\"]?",
]

# Function to fetch all repositories in the organization
def get_all_repos():
    repos = []
    url = f"https://api.github.com/orgs/{ORG_NAME}/repos?per_page=100"
    
    while url:
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            print(f"Error fetching repositories: {response.json()}")
            return []
        
        repos.extend(response.json())
        url = response.links.get('next', {}).get('url')  # Pagination handling

    return repos

# Function to scan a file for secrets
def check_for_secrets(file_content):
    for pattern in SECRET_PATTERNS:
        if re.search(pattern, file_content):
            return True
    return False

def get_default_branch(repo_name):
    """Fetch the default branch of the repository."""
    url = f"https://api.github.com/repos/{ORG_NAME}/{repo_name}"
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        return response.json().get("default_branch", "main")  # Default to 'main' if not found
    else:
        print(f"⚠️ Could not fetch default branch for {repo_name}. Skipping.")
        return None

def scan_repos(start_index=0, end_index=100):
    repos = get_all_repos()
    results = []

    total_repos = len(repos)
    if start_index >= total_repos:
        print(f"No repositories found in the range {start_index}-{end_index}.")
        return []

    end_index = min(end_index, total_repos)  # Avoid out-of-range issues
    repos_to_scan = repos[start_index:end_index]

    for repo in repos_to_scan:
        repo_name = repo["name"]
        print(f"Scanning {repo_name}...")

        # Get default branch dynamically
        default_branch = get_default_branch(repo_name)
        if not default_branch:
            continue  # Skip this repo if default branch not found

        # Get all files from repo using the GitHub API
        tree_url = f"https://api.github.com/repos/{ORG_NAME}/{repo_name}/git/trees/{default_branch}?recursive=1"
        tree_response = requests.get(tree_url, headers=HEADERS)

        if tree_response.status_code != 200:
            print(f"❌ Skipping {repo_name}: Could not fetch file tree. HTTP {tree_response.status_code}")
            continue

        files = tree_response.json().get("tree", [])

        for file in files:
            if file["type"] != "blob":  # Skip directories
                continue
            
            file_path = file["path"]
            file_url = f"https://raw.githubusercontent.com/{ORG_NAME}/{repo_name}/{default_branch}/{file_path}"
            
            file_response = requests.get(file_url, headers=HEADERS)
            if file_response.status_code != 200:
                continue  # Skip if file not accessible
            
            file_content = file_response.text
            if check_for_secrets(file_content):
                print(f"⚠️ Secret found in {repo_name}/{file_path}")
                results.append([repo_name, file_path])

    return results

# Run the scan and save results to Excel
def save_to_excel(start_index=0, end_index=100):
    results = scan_repos(start_index, end_index)
    if results:
        df = pd.DataFrame(results, columns=["Repository", "File Path"])
        file_name = f"exposed_secrets_{start_index}-{end_index}.xlsx"
        df.to_excel(file_name, index=False)
        print(f"\n✅ Scan complete. Results saved to {file_name}.")
    else:
        print("\n🎉 No secrets found in any repositories!")

# Execute the script with user-defined range
if __name__ == "__main__":
    try:
        start = int(input("Enter start index: "))
        end = int(input("Enter end index: "))
        save_to_excel(start, end)
    except ValueError:
        print("❌ Invalid input. Please enter valid numbers.")
