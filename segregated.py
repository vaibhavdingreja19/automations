import requests
import pandas as pd


GITHUB_TOKEN = ''
ORG_NAME = 'JHDevOps'

headers = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github+json'
}

repos = []
page = 1

while True:
    url = f'https://api.github.com/orgs/{ORG_NAME}/repos?per_page=100&page={page}'
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f'Error: {response.status_code} - {response.json()}')
        break

    data = response.json()
    if not data:
        break

    for repo in data:
        if not repo['archived']:  
            repos.append({
                'Repository Name': repo['name'],
                'Visibility': repo['visibility']  
            })
    
    page += 1


df = pd.DataFrame(repos)
df.to_excel('JHDevOps_active_repos.xlsx', index=False)

print(f"Exported {len(repos)} active repositories to JHDevOps_active_repos.xlsx")
