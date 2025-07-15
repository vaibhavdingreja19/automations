import pandas as pd
import os

def subtract_excel_repos_keep_format(excel_a_path, excel_b_path):
    # Load Excel A (active repos) with all sheets, no type inference
    excel_a = pd.read_excel(excel_a_path, sheet_name=None, header=0, engine='openpyxl')

    # Load Excel B (inactive repos), skip header to just get data
    df_b_raw = pd.read_excel(excel_b_path, header=0, engine='openpyxl')
    
    # Use first column (regardless of header name) for filtering
    inactive_repos = set(df_b_raw.iloc[:, 0].dropna().astype(str).str.strip().str.lower())

    # Prepare to overwrite Excel A
    with pd.ExcelWriter(excel_a_path, engine='openpyxl', mode='w') as writer:
        for sheet_name, df_a in excel_a.items():
            # Split header row and data
            header_row = df_a.iloc[0:1]     # Keep the first row as-is
            data_rows = df_a.iloc[1:]       # Start filtering from second row

            # Compare using first column of data (assume repo name)
            mask = ~data_rows.iloc[:, 0].astype(str).str.strip().str.lower().isin(inactive_repos)

            # Combine header with filtered data
            final_df = pd.concat([header_row, data_rows[mask]])

            # Write to same sheet
            final_df.to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"✅ Inactive repos removed (starting from row 2). File '{os.path.basename(excel_a_path)}' updated.")

# Example usage:
# subtract_excel_repos_keep_format("active_repos.xlsx", "inactive_repos.xlsx")
