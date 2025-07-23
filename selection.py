import pandas as pd

# === Load Excel files ===
full_df = pd.read_excel('repo_access_report.xlsx')          # All repos with collaborators
selected_df = pd.read_excel('selected_repos.xlsx')          # Only list of repos to keep

# === Normalize repo names ===
selected_repos = selected_df.iloc[:, 0].dropna().str.strip().str.lower().tolist()
full_df['Repository'] = full_df['Repository'].str.strip().str.lower()

# === Filter only matching repos ===
filtered_df = full_df[full_df['Repository'].isin(selected_repos)]

# === Save to new file ===
filtered_df.to_excel('filtered_repo_access.xlsx', index=False)

print("✅ Saved: filtered_repo_access.xlsx")
