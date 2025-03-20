import os
import subprocess
import tempfile
import shutil

def run_cmd(cmd, cwd=None):
    result = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print("Error:", result.stderr)
        raise Exception("Command failed")
    return result.stdout.strip()

def file_exists_in_branch(branch, file_path, repo_path):
    # Cross-platform check for file existence inside a branch
    try:
        output = run_cmd(f"git ls-tree -r --name-only {branch}", cwd=repo_path)
        files = output.splitlines()
        return file_path in files
    except:
        return False

def automate_git_merge(pat_token, org, repo, branch_a, branch_b, files_to_exclude):
    repo_url = f"https://{pat_token}@github.com/{org}/{repo}.git"
    
    # Step 1: Clone repo into a temp directory
    temp_dir = tempfile.mkdtemp()
    print(f"Cloning repo into {temp_dir}...")
    run_cmd(f"git clone {repo_url}", cwd=temp_dir)
    repo_path = os.path.join(temp_dir, repo)
    os.chdir(repo_path)

    # Step 2: Fetch the source branch (develop)
    run_cmd(f"git fetch origin {branch_a}")

    # Step 3: Checkout target branch (main)
    run_cmd(f"git checkout {branch_b}")

    # Step 4: Check exclusions intelligently
    attr_file = os.path.join(repo_path, '.gitattributes')
    exclusion_for_gitattributes = []

    print("Checking exclusions for merge...")
    for file_path in files_to_exclude:
        exists_in_a = file_exists_in_branch(f"origin/{branch_a}", file_path, repo_path)
        exists_in_b = file_exists_in_branch(branch_b, file_path, repo_path)
        if exists_in_a and exists_in_b:
            print(f"{file_path} exists in BOTH {branch_a} and {branch_b}, will use merge=ours rule.")
            exclusion_for_gitattributes.append(file_path)
        elif exists_in_a and not exists_in_b:
            print(f"{file_path} exists ONLY in {branch_a}, will revert after merge.")
        else:
            print(f"{file_path} does not exist in {branch_a}, skipping.")

    # Step 5: Write .gitattributes if needed
    if exclusion_for_gitattributes:
        with open(attr_file, 'a') as f:
            for file_path in exclusion_for_gitattributes:
                f.write(f"{file_path} merge=ours\n")
        run_cmd(f"git add .gitattributes")
        run_cmd(f"git commit -m 'Add merge=ours rules for specific files'")

    # Step 6: Configure merge driver
    run_cmd("git config merge.ours.driver true")

    # Step 7: Merge origin/develop into main
    run_cmd(f"git merge origin/{branch_a} --no-ff -m 'Merging {branch_a} into {branch_b} with exclusions'")

    # Step 8: Post-merge revert for "only-in-develop" files
    files_to_revert = [file for file in files_to_exclude if file_exists_in_branch(f"origin/{branch_a}", file, repo_path) and not file_exists_in_branch(branch_b, file, repo_path)]
    if files_to_revert:
        files_to_revert_str = " ".join(files_to_revert)
        run_cmd(f"git checkout HEAD -- {files_to_revert_str}")
        run_cmd(f"git commit -m 'Revert files introduced from {branch_a}'")
        print(f"Reverted files: {files_to_revert}")
    else:
        print("No files needed to be reverted post-merge.")

    # Step 9: Push back to remote
    run_cmd(f"git push origin {branch_b}")

    print(f"Merge completed, exclusions handled, and pushed to {branch_b} on remote.")
    
    # Step 10: Cleanup
    shutil.rmtree(temp_dir)
    print("Temporary directory cleaned up.")

# Example usage
if __name__ == "__main__":
    pat_token = ""  # Your real token
    org = "JHDevOps"
    repo = "merge_testing_repo"
    branch_a = "develop"
    branch_b = "main"
    files_to_exclude = ["clearingazure.py", "iiqtry.py"]  # Files to exclude from merge

    automate_git_merge(pat_token, org, repo, branch_a, branch_b, files_to_exclude)
