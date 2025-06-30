import pandas as pd

INPUT_FILE = "estimated_repo_sizes.xlsx"
SIZE_LIMIT_GB = 50
TOTAL_REPOS_PER_BATCH = 30


LARGE_THRESHOLD_GB = 1.0
MEDIUM_THRESHOLD_GB = 0.1


LARGE_PERCENT = 0.05
MEDIUM_PERCENT = 0.25
SMALL_PERCENT = 0.70


LARGE_PER_BATCH = int(TOTAL_REPOS_PER_BATCH * LARGE_PERCENT)
MEDIUM_PER_BATCH = int(TOTAL_REPOS_PER_BATCH * MEDIUM_PERCENT)
SMALL_PER_BATCH = TOTAL_REPOS_PER_BATCH - LARGE_PER_BATCH - MEDIUM_PER_BATCH

def form_batches(df, size_col_gb):
    large_repos = df[df[size_col_gb] >= LARGE_THRESHOLD_GB].reset_index(drop=True)
    medium_repos = df[(df[size_col_gb] < LARGE_THRESHOLD_GB) & (df[size_col_gb] >= MEDIUM_THRESHOLD_GB)].reset_index(drop=True)
    small_repos = df[df[size_col_gb] < MEDIUM_THRESHOLD_GB].reset_index(drop=True)

    batches = []

    while not large_repos.empty or not medium_repos.empty or not small_repos.empty:
        current_batch = []
        current_size = 0

        large_count = min(LARGE_PER_BATCH, len(large_repos))
        medium_count = min(MEDIUM_PER_BATCH, len(medium_repos))
        small_count = min(SMALL_PER_BATCH, len(small_repos))

        
        for i in range(large_count):
            row = large_repos.iloc[0]
            if current_size + row[size_col_gb] <= SIZE_LIMIT_GB:
                current_batch.append(row)
                current_size += row[size_col_gb]
            large_repos = large_repos.iloc[1:].reset_index(drop=True)

        
        for i in range(medium_count):
            row = medium_repos.iloc[0]
            if current_size + row[size_col_gb] <= SIZE_LIMIT_GB:
                current_batch.append(row)
                current_size += row[size_col_gb]
            medium_repos = medium_repos.iloc[1:].reset_index(drop=True)

        
        for i in range(small_count):
            row = small_repos.iloc[0]
            if current_size + row[size_col_gb] <= SIZE_LIMIT_GB:
                current_batch.append(row)
                current_size += row[size_col_gb]
            small_repos = small_repos.iloc[1:].reset_index(drop=True)

        
        while len(current_batch) < TOTAL_REPOS_PER_BATCH and current_size < SIZE_LIMIT_GB:
            if not large_repos.empty:
                row = large_repos.iloc[0]
                large_repos = large_repos.iloc[1:].reset_index(drop=True)
            elif not medium_repos.empty:
                row = medium_repos.iloc[0]
                medium_repos = medium_repos.iloc[1:].reset_index(drop=True)
            elif not small_repos.empty:
                row = small_repos.iloc[0]
                small_repos = small_repos.iloc[1:].reset_index(drop=True)
            else:
                break

            if current_size + row[size_col_gb] <= SIZE_LIMIT_GB:
                current_batch.append(row)
                current_size += row[size_col_gb]

        batches.append(current_batch)

    return batches

def main():
    df = pd.read_excel(INPUT_FILE)
    df["estimated_full_size_gb"] = df["estimated_full_size_kb"] / (1024 * 1024)

    batches = form_batches(df, "estimated_full_size_gb")

    with pd.ExcelWriter("repo_batches_under_70GB.xlsx") as writer:
        for i, batch in enumerate(batches):
            batch_df = pd.DataFrame(batch)
            batch_df.to_excel(writer, sheet_name=f"Batch_{i+1}", index=False)

            batch_size = batch_df["estimated_full_size_gb"].sum()
            print(f"[INFO] Batch {i+1}: {len(batch_df)} repos, total size: {batch_size:.2f} GB")

    print(f"[COMPLETE] {len(batches)} batches created and saved to 'repo_batches_under_70GB.xlsx'.")

if __name__ == "__main__":
    main()
