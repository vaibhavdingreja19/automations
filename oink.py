import os
import subprocess
import tempfile
import shutil

def run_cmd(cmd, cwd=None, allow_fail=False):
    result = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        if allow_fail:
            print(f"Non-critical warning: {result.stderr.strip()}")
            return ""
        print("Error:", result.stderr)
        raise Exception("Command failed")
    return result.stdout.strip()

def automate_git_merge(pat_token, org, repo, branch_a, branch_b, files_to_exclude):
    repo_url = f"https://{pat_token}@github.com/{org}/{repo}.git"

    temp_dir = tempfile.mkdtemp()
    print(f"Cloning repo into {temp_dir}...")
    run_cmd(f"git clone {repo_url}", cwd=temp_dir)
    repo_path = os.path.join(temp_dir, repo)
    os.chdir(repo_path)

    # Fetch remote branch_a properly
    run_cmd(f"git fetch origin {branch_a}")

    # Checkout target branch_b
    run_cmd(f"git checkout {branch_b}")

    # Merge using origin/branch_a, not local develop!
    remote_branch_a = f"origin/{branch_a}"
    run_cmd(f"git merge {remote_branch_a} --no-ff -m 'Merging {branch_a} into {branch_b} with exclusions'")

    # Post-merge cleanup (remove unwanted files)
    for file in files_to_exclude:
        print(f"Excluding file: {file}")
        # Even if file does not exist, skip silently
        run_cmd(f"git checkout HEAD -- {file}", allow_fail=True)

    # Commit (only if there is something to commit)
    run_cmd(f"git commit -m 'Exclude specified files post-merge' || echo 'Nothing to commit'", allow_fail=True)

    # Push to remote
    run_cmd(f"git push origin {branch_b}")

    print(f"✅ Merge + exclusions complete! Clean push to {branch_b} done.")
    shutil.rmtree(temp_dir)
    print("🧹 Temp cleaned up.")

if __name__ == "__main__":
    pat_token = ""
    org = "JHDevOps"
    repo = "merge_testing_repo"
    branch_a = "develop"
    branch_b = "main"
    files_to_exclude = ["clearingazure.py", "iiqtry.py"]

    automate_git_merge(pat_token, org, repo, branch_a, branch_b, files_to_exclude)
