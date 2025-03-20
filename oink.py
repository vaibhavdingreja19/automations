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
    # Check if file exists in a given branch
    try:
        run_cmd(f"git ls-tree -r --name-only {branch} | grep '^{file_path}$'", cwd=repo_path)
        return True
    except:
        return False

def automate_git_merge(pat_token, org, repo, branch_a, branch_b, files_to_exclude):
    repo_url = f"https://{pat_token}@github.com/{org}/{repo}.git"
    
    # Clone to a temp directory
    temp_dir = tempfile.mkdtemp()
    print(f"Cloning repo into {temp_dir}...")
    run_cmd(f"git clone {repo_url}", cwd=temp_dir)
    repo_path = os.path.join(temp_dir, repo)
    os.chdir(repo_path)

    # Checkout target branch (B)
    run_cmd(f"git checkout {branch_b}")

    attr_file = os.path.join(repo_path, '.gitattributes')
    exclusion_for_gitattributes = []

    print("Checking exclusions for merge...")

    # Check where files exist and decide action
    for file_path in files_to_exclude:
        exists_in_a = file_exists_in_branch(branch_a, file_path, repo_path)
        exists_in_b = file_exists_in_branch(branch_b, file_path, repo_path)
        if exists_in_a and exists_in_b:
            print(f"{file_path} exists in BOTH {branch_a} and {branch_b}, will use merge=ours rule.")
            exclusion_for_gitattributes.append(file_path)
        elif exists_in_a and not exists_in_b:
            print(f"{file_path} exists ONLY in {branch_a}, will revert after merge.")
        else:
            print(f"{file_path} does not exist in {branch_a}, skipping.")

    # Write merge=ours rules only for files existing in both branches
    if exclusion_for_gitattributes:
        with open(attr_file, 'a') as f:
            for file_path in exclusion_for_gitattributes:
                f.write(f"{file_path} merge=ours\n")
        run_cmd(f"git add .gitattributes")
        run_cmd(f"git commit -m 'Add merge=ours rules for specific files'")

    # Configure merge driver (one-time config)
    run_cmd("git config merge.ours.driver true")

    # Merge branch A into branch B
    run_cmd(f"git merge {branch_a} --no-ff -m 'Merging {branch_a} into {branch_b} with exclusions'")

    # Post-merge: revert files that were found only in branch A (develop)
    files_to_revert = [file for file in files_to_exclude if file_exists_in_branch(branch_a, file, repo_path) and not file_exists_in_branch(branch_b, file, repo_path)]
    if files_to_revert:
        files_to_revert_str = " ".join(files_to_revert)
        run_cmd(f"git checkout HEAD -- {files_to_revert_str}")
        run_cmd(f"git commit -m 'Revert files introduced from {branch_a}'")
        print(f"Reverted files: {files_to_revert}")
    else:
        print("No files needed to be reverted post-merge.")

    # Push changes back to remote
    run_cmd(f"git push origin {branch_b}")

    print(f"Merge completed, exclusions handled, and pushed to {branch_b} on remote.")
    
    # Cleanup temp directory
    shutil.rmtree(temp_dir)
    print("Temporary directory cleaned up.")

# Example usage
if __name__ == "__main__":
    pat_token = "ghp_xxx"  # replace with your token
    org = "JHDevOps"
    repo = "merge_testing_repo"
    branch_a = "develop"
    branch_b = "main"
    files_to_exclude = ["clearingazure.py", "iiqtry.py"]  # Files to exclude from merge

    automate_git_merge(pat_token, org, repo, branch_a, branch_b, files_to_exclude)
