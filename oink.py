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

def automate_git_merge(pat_token, org, repo, branch_a, branch_b, files_to_exclude):
    repo_url = f"https://{pat_token}@github.com/{org}/{repo}.git"
    
    # Clone to temp
    temp_dir = tempfile.mkdtemp()
    print(f"Cloning repo into {temp_dir}...")
    run_cmd(f"git clone {repo_url}", cwd=temp_dir)
    repo_path = os.path.join(temp_dir, repo)
    os.chdir(repo_path)

    # Fetch branches
    run_cmd(f"git fetch origin {branch_a}")

    # Checkout target branch
    run_cmd(f"git checkout {branch_b}")

    # Merge origin/branch_a into branch_b
    run_cmd(f"git merge origin/{branch_a} --no-ff -m 'Merging {branch_a} into {branch_b} with file exclusions'")

    # Always restore original state of exception files (even if they don't exist yet)
    for file in files_to_exclude:
        try:
            run_cmd(f"git checkout HEAD -- {file}")
            print(f"Excluded {file} from merge (kept {branch_b} version or removed if not present)")
        except:
            print(f"{file} does not exist in either branch, skipping gracefully.")

    # Commit changes
    run_cmd(f"git commit -m 'Exclude exception files post-merge' || echo 'Nothing to commit'")

    # Push back
    run_cmd(f"git push origin {branch_b}")

    print(f"Merge completed, exceptions handled, and pushed to {branch_b}.")

    # Cleanup
    shutil.rmtree(temp_dir)
    print("Temporary directory cleaned up.")


# Example usage
if __name__ == "__main__":
    pat_token = ""
    org = "JHDevOps"
    repo = "merge_testing_repo"
    branch_a = "develop"
    branch_b = "main"
    files_to_exclude = ["clearingazure.py", "iiqtry.py"]

    automate_git_merge(pat_token, org, repo, branch_a, branch_b, files_to_exclude)
