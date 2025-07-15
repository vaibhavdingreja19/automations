import pandas as pd
import os

def subtract_excel_repos_keep_format(excel_a_path, excel_b_path):
    # Load Excel A (active repos) with all sheets
    excel_a = pd.read_excel(excel_a_path, sheet_name=None, engine='openpyxl')

    # Load Excel B (inactive repos) - assume one sheet, one column 'repo_name'
    df_b = pd.read_excel(excel_b_path, engine='openpyxl')
    inactive_repos = set(df_b['repo_name'].str.strip().str.lower())

    # Prepare to overwrite Excel A (same file name and path)
    with pd.ExcelWriter(excel_a_path, engine='openpyxl', mode='w') as writer:
        for sheet_name, df_a in excel_a.items():
            # Remove inactive repos
            df_result = df_a[~df_a['repo_name'].str.strip().str.lower().isin(inactive_repos)]
            df_result.to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"✅ Inactive repos removed. File '{os.path.basename(excel_a_path)}' updated successfully.")

# Example usage:
subtract_excel_repos_keep_format("active_repos.xlsx", "inactive_repos.xlsx")
