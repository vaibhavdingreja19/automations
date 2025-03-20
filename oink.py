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
    
    # Clone to a temp directory
    temp_dir = tempfile.mkdtemp()
    print(f"Cloning repo into {temp_dir}...")
    run_cmd(f"git clone {repo_url}", cwd=temp_dir)
    repo_path = os.path.join(temp_dir, repo)

    os.chdir(repo_path)

    # Checkout target branch (B)
    run_cmd(f"git checkout {branch_b}")

    # Create or update .gitattributes
    attr_file = os.path.join(repo_path, '.gitattributes')
    with open(attr_file, 'a') as f:
        for file_path in files_to_exclude:
            f.write(f"{file_path} merge=ours\n")
    run_cmd(f"git add .gitattributes")
    run_cmd(f"git commit -m 'Add merge=ours rules for specific files'")

    # Configure merge driver
    run_cmd("git config merge.ours.driver true")

    # Merge branch A into branch B
    run_cmd(f"git merge {branch_a} --no-ff -m 'Merging {branch_a} into {branch_b} with exclusions'")

    # Push changes back to remote
    run_cmd(f"git push origin {branch_b}")

    print(f"Merge completed and pushed to {branch_b} on remote!")

    # Cleanup temp directory
    shutil.rmtree(temp_dir)
    print("Temporary directory cleaned up.")

# Example usage
if __name__ == "__main__":
    # Replace below with your actual inputs or read them dynamically
    pat_token = "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"
    org = "JHDevOps"
    repo = "merge_testing_repo"
    branch_a = "develop"
    branch_b = "main"
    files_to_exclude = ["clearingazure.py", "siiqtry.py"]  # Example files

    automate_git_merge(pat_token, org, repo, branch_a, branch_b, files_to_exclude)
