import requests
import openpyxl
import time


GITHUB_TOKEN = "ghp_your_personal_access_token_here"  # replace with your PAT
ORG_NAME = "JHDevOps"
EXCEL_FILE_PATH = "repos.xlsx"  # path to your Excel file


headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}



def read_repo_names(file_path):
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active
    return [cell.value for cell in ws[2] if cell.value]

def remove_individual_collaborators(repo):
    url = f"https://api.github.com/repos/{ORG_NAME}/{repo}/collaborators"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"Failed to list collaborators for {repo}: {resp.text}")
        return

    for collab in resp.json():
        username = collab["login"]
        del_url = f"https://api.github.com/repos/{ORG_NAME}/{repo}/collaborators/{username}"
        del_resp = requests.delete(del_url, headers=headers)
        if del_resp.status_code in [204, 404]:
            print(f"Removed individual: {username} from {repo}")
        else:
            print(f"Failed to remove {username} from {repo}: {del_resp.text}")

def remove_teams(repo):
    url = f"https://api.github.com/orgs/{ORG_NAME}/teams"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"Failed to list teams: {resp.text}")
        return

    for team in resp.json():
        team_slug = team["slug"]
        check_url = f"https://api.github.com/orgs/{ORG_NAME}/teams/{team_slug}/repos/{ORG_NAME}/{repo}"
        check_resp = requests.get(check_url, headers=headers)
        if check_resp.status_code == 204:
            del_url = f"https://api.github.com/orgs/{ORG_NAME}/teams/{team_slug}/repos/{ORG_NAME}/{repo}"
            del_resp = requests.delete(del_url, headers=headers)
            if del_resp.status_code == 204:
                print(f"Removed team: {team_slug} from {repo}")
            else:
                print(f"Failed to remove team {team_slug} from {repo}: {del_resp.text}")

def archive_repo(repo):
    url = f"https://api.github.com/repos/{ORG_NAME}/{repo}"
    payload = {"archived": True}
    resp = requests.patch(url, headers=headers, json=payload)
    if resp.status_code == 200:
        print(f"Archived repo: {repo}")
    else:
        print(f"Failed to archive {repo}: {resp.text}")


def main():
    repos = read_repo_names(EXCEL_FILE_PATH)
    print(f"Found {len(repos)} repos in Excel row 2.")

    for repo in repos:
        print(f"\nProcessing repo: {repo}")
        remove_individual_collaborators(repo)
        remove_teams(repo)
        archive_repo(repo)
        time.sleep(1)  # avoid hitting rate limits

if __name__ == "__main__":
    main()
