import sys
from git import Repo
import vault_auth
import os
import subprocess
from datetime import datetime, timezone
import requests
class GitHubManager:

    def __init__(self, repo_url, working_directory, path_to_ssh_key, auth_token, reviewers, changes_branch_name):

        self.github_repo = repo_url
        self.change_branch = changes_branch_name
        self.github_repo_key = self.github_repo.lstrip("https://github.com/")
        self.working_dir = working_directory
        self.ssh_key_path = path_to_ssh_key
        self.auth_token = auth_token
        self.error = False
        self.branch_created = False
        self.reviewers = reviewers
        self.repo_output_name = "website"
        self.repo_dir = "{}/{}".format(self.working_dir, self.repo_output_name)
        self.repo = self.setup_repo()

    def run_command(self, command):
        result = subprocess.run(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            self.error = True
            print("ERROR: '%s'" % command)
            print(result.stdout.decode("utf-8"))
            print(result.stderr.decode("utf-8"))
            sys.exit(result.returncode)

    def run_repo_command(self, command):
        """Runs a command inside the repo directory"""
        os.chdir(self.repo_dir)
        self.run_command(command)
        os.chdir(self.working_dir)

    def run_git_command(self, command):
        """ Run a git command on the repo """
        # Make sure we are in the repo directory.
        os.chdir(self.repo_dir)
        git_cmd = 'ssh-add "{}"; {}'.format(self.ssh_key_path, command)
        full_cmd = "ssh-agent bash -c '{}'".format(git_cmd)
        print("running {}".format(full_cmd))
        self.run_command(full_cmd)
        # Change back into the working directory
        os.chdir(self.working_dir)

    def setup_repo(self):
        """
        1. Clone the repo if it doesn't already exist.
        2. If it exists:
            - Ensure we are on the master first.
            - Delete any local version of the change branch.
            - Make sure the local change branch is up to date with the remote version if it exists
            - If not then checkout a new clean branch off of master
        """
        # Check to see if the repo directory exists.
        if not os.path.isdir(self.repo_dir):
            # Make sure we are in the working directory.
            print("Cloning repo...")
            self.run_git_command("git clone git@github.com:{}.git website".format(self.github_repo_key))
        else:
            # Repo is already cloned so make sure we are on the master branch
            self.run_git_command("git checkout master")
            # Fetch latest version of branches
            print("Fetch latest changes...")
            self.run_git_command("git fetch")
        # Instanitate a new Repo object
        repo = Repo(self.repo_dir)
        # Get a list of branch names
        repo_heads_names = [h.name for h in repo.branches]
        print("Verifying branch exists...")
        if self.change_branch in repo_heads_names:
            print("{} has been found.".format(self.change_branch))
            # Change branch exists so let's delete and fetch any upstream changes.
            try:
                self.run_git_command("git branch -D {}".format(self.change_branch))
                print("Local {} branch has been deleted.".format(self.change_branch))
            except Exception as e:
                pass
            print("Checking out {}.".format(self.change_branch))
            self.run_git_command("git checkout -b {}".format(self.change_branch))
            print("Pulling any upstream changes.")
            self.run_git_command("git pull origin {}".format(self.change_branch))
        else:
            print("Creating branch...")
            self.run_git_command("git checkout -b {}".format(self.change_branch))
        
        return repo

    def commit_and_push_changes(self, commit_message):
        """
        Commits and pushes any local changes that have been made.
        If changes have been pushed successfully, then reutnr True.
        Else return false
        """
        try:
            self.run_repo_command("git add --all")
            self.run_repo_command("git commit -m '{}'".format(commit_message))
            print("Pushing local changes to origin/{}".format(self.change_branch))
            self.run_git_command("git push origin {}".format(self.repo.active_branch.name))
            return True
        except Exception as e:
            print("An exception occured when committing and pushing changes!")
            print(e)
            return False

    def create_pull_request(self, title, description):
        """
        Creates a new pull request if one doesn't already exist.
        """
        # Set Authorization header for API call
        headers = {'Authorization': 'token {}'.format(self.auth_token)}
        # Pull request API URL
        url = "https://api.github.com/repos/{}/pulls".format(self.github_repo_key)
        # Get the current pull requests to check a PR is not already open
        current_pull_requests = requests.get(url, headers=headers)
        # Check that the status code returned is not erroneous
        if current_pull_requests.status_code != 200:
            print("ERROR: Failed to get list of current pull requests")
            print(current_pull_requests.text)
            self.error = True
            return False
        # Request successfully returned a JSON object
        else:
            json = current_pull_requests.json()
            # Loop over the pull requests checking for self.change_branch
            pull_open = False
            for pull in json:
                if pull["head"]["ref"] == self.repo.active_branch.name:
                    pull_open = True 
            # Create a new pull request since one is not currently open
            if not pull_open:
                # Set the data payload
                data = {
                    "title": title,
                    "body": body,
                    "head": self.repo.active_branch.name,
                    "base": "master"
                }
                # Post the data to the GitHub API
                result = requests.post(url, json=data, headers=headers)
                # Check for an erroneous response
                if result.status_code != 201:
                    print("ERROR: Failed to create pull request")
                    print(result.text)
                    self.error = True
                    return False
                # Pull Request has been created successfully.
                else:
                    # Get the returned JSON data
                    json = result.json()
                    print("Pull request created: {}".format(json["html_url"]))
                    # Set the reviewers data payload.
                    data = {
                        "reviewers": self.reviewers
                    }
                    # API URL for adding reviewers.
                    url = "https://api.github.com/repos/{0}/pulls/{1}/requested_reviewers".format(
                        self.github_repo_key, json["number"])
                    # Submit request to add reviewers
                    result = requests.post(url, json=data, headers=headers)
                    if result.status_code != 201:
                        print("ERROR: Failed to add reviewers to the pull request")
                        print(result.text)
                        self.error = True
                        return False
                    else:
                        print("Reviewers ({}) have been added succesfully!".format(self.reviewers))