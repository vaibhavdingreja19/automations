import os
import subprocess
import shutil
import sys
from git import Repo

def merge_branches_excluding_files(pat_token, repo_name, branch1, branch2, exception_files):
    org = "JHDevOps"
    repo_url = f"https://{pat_token}@github.com/{org}/{repo_name}.git"
    clone_dir = f"./{repo_name}_clone"

    # Clean up any existing clone
    if os.path.exists(clone_dir):
        shutil.rmtree(clone_dir)

    print("Cloning repository...")
    repo = Repo.clone_from(repo_url, clone_dir)

    # Set up repo and fetch
    git = repo.git
    git.fetch('--all')
    
    repo.git.checkout(branch1)
    print(f"Checked out to {branch1}.")

    try:
        print(f"Merging {branch2} into {branch1} with no commit...")
        git.merge(branch2, '--no-commit', '--no-ff')
    except Exception as e:
        print(f"Merge conflict or issue: {e}")
        # Optionally handle auto-merging or re-raise
        raise

    # Revert exception files to branch1 state
    for file in exception_files:
        if os.path.exists(os.path.join(clone_dir, file)):
            print(f"Resetting exception file: {file}")
            git.checkout(f"HEAD", "--", file)

    # Finalize merge
    repo.index.commit(f"Merge {branch2} into {branch1} excluding {exception_files}")
    print("Merge committed.")

    print("Pushing changes...")
    origin = repo.remote(name='origin')
    origin.push(branch1)
    print("Push successful.")

    # Cleanup
    shutil.rmtree(clone_dir)

# Example usage
if __name__ == "__main__":
    # These should come from secure input (or args)
    pat_token = "ghp_yourtokenhere"
    repo_name = "your-repo-name"
    branch1 = "main"
    branch2 = "feature-branch"
    exception_files = ["README.md", "config/settings.json"]  # paths relative to repo root

    merge_branches_excluding_files(pat_token, repo_name, branch1, branch2, exception_files)
