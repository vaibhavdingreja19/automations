import pandas as pd


INPUT_FILE = "estimated_repo_sizes.xlsx"
SIZE_LIMIT_GB = 70
MAX_REPOS_PER_BATCH = 30

def group_repos_by_size_limit(df, size_col_gb):
    batches = []
    current_batch = []
    current_size = 0

    for _, row in df.iterrows():
        repo_size = row[size_col_gb]
        if (len(current_batch) < MAX_REPOS_PER_BATCH) and (current_size + repo_size <= SIZE_LIMIT_GB):
            current_batch.append(row)
            current_size += repo_size
        else:
            batches.append(current_batch)
            current_batch = [row]
            current_size = repo_size

    if current_batch:
        batches.append(current_batch)
    
    return batches

def main():
    df = pd.read_excel(INPUT_FILE)
    
   
    df["estimated_full_size_gb"] = df["estimated_full_size_kb"] / (1024 * 1024)

    
    df_sorted = df.sort_values(by="estimated_full_size_gb", ascending=False).reset_index(drop=True)

    batches = group_repos_by_size_limit(df_sorted, "estimated_full_size_gb")

    
    with pd.ExcelWriter("repo_batches_under_70GB.xlsx") as writer:
        for i, batch in enumerate(batches):
            batch_df = pd.DataFrame(batch)
            batch_df.to_excel(writer, sheet_name=f"Batch_{i+1}", index=False)

    print(f"{len(batches)} batches created and saved to 'repo_batches_under_70GB.xlsx'.")

if __name__ == "__main__":
    main()
