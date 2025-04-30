import os
import subprocess
import shutil
from git import Repo, GitCommandError

def merge_branches_excluding_files(pat_token, repo_name, branch1, branch2, exception_files):
    org = "JHDevOps"
    repo_url = f"https://{pat_token}@github.com/{org}/{repo_name}.git"
    clone_dir = f"./{repo_name}_clone"

    # Clean up any existing clone
    if os.path.exists(clone_dir):
        shutil.rmtree(clone_dir)

    print("Cloning repository...")
    repo = Repo.clone_from(repo_url, clone_dir)

    git = repo.git
    git.fetch('--all')

    repo.git.checkout(branch1)
    print(f"Checked out to {branch1}.")

    try:
        print(f"Merging {branch2} into {branch1} with no commit...")
        git.merge(branch2, '--no-commit', '--no-ff')
    except GitCommandError as e:
        print("Merge conflict detected. Attempting to auto-resolve for exception files only...")

        # Resolve conflicts only for exception files
        for file in exception_files:
            try:
                print(f"Handling exception file: {file}")
                git.checkout('--ours', file)  # Keep version from branch1
                git.add(file)
            except GitCommandError:
                print(f"Warning: Could not auto-resolve {file}. Manual fix might be needed.")

        # Now attempt to commit
        try:
            repo.index.commit(f"Auto-merge {branch2} into {branch1}, excluding {exception_files}")
            print("Merge committed successfully.")
        except Exception as commit_error:
            print(f"Failed to commit merge: {commit_error}")
            raise

    print("Pushing merged branch...")
    origin = repo.remote(name='origin')
    origin.push(branch1)
    print("Push complete.")

    # Cleanup
    shutil.rmtree(clone_dir)
    print("Local clone cleaned up.")

# ------------------ Example Usage ------------------

if __name__ == "__main__":
    pat_token = "ghp_your_token_here"
    repo_name = "your-repo-name"
    branch1 = "main"
    branch2 = "feature-branch"
    exception_files = ["clearingazure.py", "README.md"]  # Files to be excluded from merge

    merge_branches_excluding_files(pat_token, repo_name, branch1, branch2, exception_files)
