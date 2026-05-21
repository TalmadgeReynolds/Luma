#!/usr/bin/env python3
import os
import subprocess
import logging
import re
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Output to console
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'git_branch.log'))  # Output to file
    ]
)
logger = logging.getLogger("GitNewBranch")

# Patterns for sensitive information
SENSITIVE_PATTERNS = [
    (r'password\s*=\s*[\'\"][^\'\"\s]+[\'\"]', 'potential password'),
    (r'api[_-]?key\s*=\s*[\'\"][^\'\"\s]+[\'\"]', 'API key'),
    (r'secret\s*=\s*[\'\"][^\'\"\s]+[\'\"]', 'secret key'),
    (r'access[_-]?token\s*=\s*[\'\"][^\'\"\s]+[\'\"]', 'access token'),
    (r'auth[_-]?token\s*=\s*[\'\"][^\'\"\s]+[\'\"]', 'auth token'),
    (r'bearer\s*[\'\"][^\'\"\s]+[\'\"]', 'bearer token'),
    (r'BEGIN\s+PRIVATE\s+KEY', 'private key'),
    (r'BEGIN\s+RSA\s+PRIVATE\s+KEY', 'RSA private key'),
]

# File size threshold (5MB)
MAX_FILE_SIZE = 5 * 1024 * 1024

def run_command(command):
    """Runs a shell command and returns the output."""
    logger.info(f"Executing command: {command}")
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
        logger.info(f"Command successful: {command}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {command}")
        logger.error(f"Error details: {e.stderr}")
        print(f"❌ Error running command: {command}\n{e.stderr}")
        return None

def get_current_branch():
    """Fetches the current Git branch dynamically."""
    logger.info("Getting current branch...")
    branch = run_command("git rev-parse --abbrev-ref HEAD")
    if branch:
        logger.info(f"Current branch: {branch}")
        return branch
    else:
        logger.warning("Failed to get current branch, defaulting to 'main'")
        return "main"

def check_git_status():
    """Checks the Git status to see if there are changes."""
    logger.info("Checking Git status for changes...")
    print("🔍 Checking for changes...")
    status = run_command("git status --porcelain")
    
    if status:
        file_count = len(status.splitlines())
        logger.info(f"Found {file_count} changed file(s)")
        return status
    else:
        logger.info("No changes found in working directory")
        return None

def create_new_branch():
    """Creates and switches to a new branch with a user-provided name."""
    current_branch = get_current_branch()
    logger.info(f"Current branch: {current_branch}")
    print(f"\n🔀 Current branch: {current_branch}")
    
    # Suggest branch name based on current date
    suggested_name = f"feature-{datetime.now().strftime('%Y%m%d-%H%M')}"
    logger.info(f"Suggesting branch name: {suggested_name}")
    
    new_branch = input(f"👉 Enter new branch name (or press Enter for '{suggested_name}'): ")
    
    if not new_branch.strip():
        logger.info(f"No name provided, using suggested name: {suggested_name}")
        new_branch = suggested_name
        
    # Check if branch already exists
    existing_branches = run_command("git branch")
    if existing_branches and new_branch in existing_branches:
        logger.warning(f"Branch '{new_branch}' already exists")
        use_existing = input(f"⚠️ Branch '{new_branch}' already exists. Use it anyway? (y/n): ").strip().lower()
        if use_existing == 'y':
            # Switch to existing branch
            logger.info(f"Switching to existing branch: {new_branch}")
            print(f"🔄 Switching to branch: {new_branch}")
            result = run_command(f"git checkout {new_branch}")
            if result is not None:
                return new_branch
            else:
                logger.error(f"Failed to switch to branch: {new_branch}")
                return None
        else:
            # Ask for a different name
            return create_new_branch()
    
    # Create and switch to new branch
    logger.info(f"Creating new branch: {new_branch}")
    print(f"🔄 Creating and switching to branch: {new_branch}")
    
    result = run_command(f"git checkout -b {new_branch}")
    if result is not None:
        logger.info(f"Successfully created and switched to branch: {new_branch}")
        return new_branch
    
    logger.error(f"Failed to create/switch to branch: {new_branch}")
    return None

def ensure_all_changes_staged():
    """Make sure there are no unstaged changes remaining."""
    unstaged = run_command("git diff --name-only")
    if unstaged:
        logger.warning(f"Found unstaged changes after git add, attempting to stage them")
        return run_command("git add .")
    return True

def check_for_sensitive_info():
    """Checks staged changes for sensitive information and large files."""
    logger.info("Checking for sensitive information in staged changes...")
    print("🔍 Checking for sensitive information...")
    
    # Get list of staged files
    staged_files = run_command("git diff --cached --name-only")
    if not staged_files:
        return True
    
    staged_files_list = staged_files.splitlines()
    warnings = []
    
    # Check each staged file
    for file_path in staged_files_list:
        # Skip if file doesn't exist
        if not os.path.exists(file_path):
            continue
            
        # Check file size
        try:
            file_size = os.path.getsize(file_path)
            if file_size > MAX_FILE_SIZE:
                warnings.append(f"⚠️  Large file detected: {file_path} ({file_size // 1024 // 1024}MB)")
        except OSError:
            logger.warning(f"Could not check size of {file_path}")
            
        # Check for binary files
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                try:
                    content = f.read()
                    
                    # Check for sensitive patterns
                    for pattern, description in SENSITIVE_PATTERNS:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches:
                            warnings.append(f"⚠️  Possible {description} found in {file_path}")
                            break
                except UnicodeDecodeError:
                    # Binary file, skip content check
                    pass
        except OSError:
            logger.warning(f"Could not read {file_path}")
            
    # Check .gitignore for sensitive file patterns
    try:
        with open('.gitignore', 'r') as f:
            gitignore = f.read()
            for file_path in staged_files_list:
                # Check if file should be ignored
                basename = os.path.basename(file_path)
                if basename in gitignore or f"*{os.path.splitext(basename)[1]}" in gitignore:
                    warnings.append(f"⚠️  File '{file_path}' matches a pattern in .gitignore")
    except FileNotFoundError:
        logger.warning("No .gitignore file found")
    
    # If warnings found, ask user what to do
    if warnings:
        print("\n⚠️  POTENTIAL SENSITIVE INFORMATION DETECTED:")
        for warning in warnings:
            print(warning)
            
        choice = input("\n⚠️  Do you want to proceed with the commit? (y/n): ").strip().lower()
        if choice != 'y':
            logger.info("User aborted commit due to sensitive information warnings")
            print("🛑 Commit aborted. Please review the files and try again.")
            return False
            
        logger.info("User chose to proceed despite sensitive information warnings")
        print("⚠️  Proceeding with commit despite warnings...")
    
    return True

def stage_changes():
    """Stages all changes."""
    logger.info("Staging changes...")
    print("📂 Staging all changes...")
    
    # Check if .env file is among the changed files
    status_output = run_command("git status --porcelain")
    if status_output and re.search(r'\s\.env\b', status_output):
        logger.warning("⚠️ .env file detected in changes")
        print("⚠️ WARNING: .env file detected in changes")
        print("   This file may contain sensitive API keys and credentials")
        
        exclude_env = input("❓ Do you want to exclude .env files from commit? (Y/n): ").strip().lower()
        if exclude_env != "n":
            logger.info("Excluding .env file from staging")
            print("👍 Excluding .env file from commit")
            # Add all files except .env
            result = run_command("git add -- . ':!.env'")
        else:
            logger.warning("User chose to include .env file in commit")
            print("⚠️ Including .env file in commit (not recommended)")
            result = run_command("git add .")
    else:
        # No .env file detected, proceed with normal staging
        result = run_command("git add .")
    
    if result is not None:
        logger.info("Successfully staged changes")
        # Verify staging worked by checking git status
        staged = run_command("git status -s")
        if staged:
            logger.info(f"Staged files: \n{staged}")
            
        # Double-check for any remaining unstaged changes
        ensure_all_changes_staged()
        return True
    else:
        logger.error("Failed to stage changes")
        return False

def commit_changes():
    """Commits changes with a user-provided or default message."""
    # Check for sensitive information before committing
    if not check_for_sensitive_info():
        return False
        
    default_msg = f"Update {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    logger.info(f"Preparing to commit with default message: {default_msg}")
    
    commit_message = input(f"📝 Enter commit message (or press Enter for '{default_msg}'): ") or default_msg
    logger.info(f"Using commit message: {commit_message}")
    
    print(f"💾 Committing changes: \"{commit_message}\"")
    result = run_command(f'git commit -m "{commit_message}"')
    
    if result:
        logger.info("Commit successful")
        logger.info(f"Commit details: {result}")
        return True
    else:
        logger.error("Commit failed")
        return False

def push_branch():
    """Pushes the branch to the remote repository."""
    branch = get_current_branch()
    logger.info(f"Pushing branch {branch} to remote...")
    print(f"🚀 Pushing to GitHub ({branch})...")
    
    # Run git push but capture output even if it fails
    process = subprocess.run(f"git push origin {branch}", shell=True, text=True, capture_output=True)
    
    # Check for success
    if process.returncode == 0:
        logger.info(f"Successfully pushed changes to {branch}")
        if process.stdout:
            logger.info(f"Push details: {process.stdout}")
        print(f"✅ Successfully pushed changes to {branch}")
        return True
    
    # Handle different error cases
    error_output = process.stderr
    
    # Log the complete error for debugging
    logger.error(f"Push error details: {error_output}")
    
    # Check for "up-to-date" message
    if "Everything up-to-date" in error_output:
        logger.info(f"Branch {branch} is already up to date with remote")
        print(f"✅ Branch '{branch}' is already up to date with remote")
        return True
    
    # Check for no upstream branch
    if "no upstream branch" in error_output or "set the upstream" in error_output:
        logger.info("No upstream branch exists yet, attempting to set upstream")
        print(f"📌 First time pushing this branch. Setting upstream...")
        set_upstream_result = run_command(f"git push --set-upstream origin {branch}")
        if set_upstream_result is not None:
            logger.info(f"Successfully set upstream and pushed branch {branch}")
            print(f"✅ Successfully created and pushed branch '{branch}'")
            return True
        else:
            logger.error("Failed to set upstream branch")
            return False
    
    # Handle other push errors with details
    logger.error(f"Failed to push changes to {branch}")
    print(f"❌ Push failed with the following error:")
    print(f"   {error_output.strip()}")
    
    # Provide some common solutions
    print("\n🔧 COMMON SOLUTIONS:")
    print("  1. Check your internet connection")
    print("  2. Ensure you have the right permissions on the repository")
    print("  3. Try pulling latest changes first with: git pull origin main")
    print("  4. Check if the remote repository URL is correct: git remote -v")
    
    return False

def create_pull_request():
    """Asks the user if they want to create a pull request and provides instructions."""
    branch = get_current_branch()
    
    create_pr = input("\n📤 Do you want to create a pull request for this branch? (y/n): ").strip().lower()
    if create_pr == 'y':
        # Determine the default remote and repo URL
        remote_url = run_command("git remote get-url origin")
        if not remote_url:
            logger.error("Could not determine remote repository URL")
            return
            
        # Extract the repository URL in GitHub format
        github_url = None
        if "github.com" in remote_url:
            # Handle SSH URLs like git@github.com:username/repo.git
            if remote_url.startswith("git@github.com:"):
                repo_path = remote_url.split('git@github.com:')[1].rstrip('.git')
                github_url = f"https://github.com/{repo_path}/pull/new/{branch}"
            # Handle HTTPS URLs like https://github.com/username/repo.git
            elif remote_url.startswith("https://github.com/"):
                repo_path = remote_url.split('https://github.com/')[1].rstrip('.git')
                github_url = f"https://github.com/{repo_path}/pull/new/{branch}"
        
        if github_url:
            print(f"\n🔗 Create a pull request by visiting this URL:")
            print(f"   {github_url}")
        else:
            print(f"\n🔗 Create a pull request by visiting your repository's website and creating a PR from branch: {branch}")

def main():
    """Main function to push changes to a new branch."""
    logger.info("=== GIT NEW BRANCH SCRIPT STARTED ===")
    print("\n🚀 GIT NEW BRANCH SCRIPT 🚀")
    print("============================")

    # Check if there are changes before proceeding
    changes = check_git_status()
    if not changes:
        logger.info("No changes detected, checking if we should proceed anyway")
        print("⚠️ No changes detected in the working directory.")
        proceed = input("❓ Do you want to create a new branch anyway? (y/n): ").strip().lower()
        if proceed != 'y':
            logger.info("User chose not to proceed without changes")
            print("✅ Exiting script.")
            return
    else:
        file_count = len(changes.splitlines())
        print(f"📄 Found {file_count} changed file(s)")
        logger.info(f"Changes detected in {file_count} file(s)")
    
    # Create new branch
    branch = create_new_branch()
    if not branch:
        logger.error("Branch creation failed, exiting script")
        print("❌ Branch creation failed. Exiting.")
        return
    
    logger.info(f"Using branch: {branch}")
    
    # If we have changes, stage and commit them
    if changes:
        # Ask if user wants to enable safety checks
        safe_mode = input("🔒 Enable safe mode to check for sensitive info? (Y/n): ").strip().lower()
        safe_mode_enabled = safe_mode != 'n'
        
        if safe_mode_enabled:
            logger.info("Safe mode enabled - will check for sensitive information")
        else:
            logger.info("Safe mode disabled - skipping sensitive information check")
            global check_for_sensitive_info
            check_for_sensitive_info = lambda: True
            
        # Stage and commit changes
        if not stage_changes():
            logger.error("Failed to stage changes, exiting script")
            print("❌ Failed to stage changes. Exiting.")
            return
            
        if not commit_changes():
            logger.error("Failed to commit changes, exiting script")
            print("❌ Failed to commit changes. Exiting.")
            return
    
    # Push the branch
    if not push_branch():
        logger.error("Failed to push branch, but branch was created locally")
        print("⚠️ Branch was created locally, but push to remote failed.")
        return
        
    # Ask if user wants to create a PR
    create_pull_request()
    
    logger.info("=== GIT NEW BRANCH SCRIPT COMPLETED SUCCESSFULLY ===")
    print(f"\n✅ SUCCESS! Branch '{branch}' was created and pushed 🎉")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ Script interrupted by user")
        logger.warning("Script interrupted by user (CTRL+C)")
    except Exception as e:
        logger.exception("Unexpected error occurred")
        print(f"❌ Unexpected error: {str(e)}")