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

    def run_git_command(self, command, in_repo_directory=True):
        """ Run a git command on the repo """
        if in_repo_directory:
            os.chdir(self.repo_dir)
        git_cmd = 'ssh-add "{}"; {}'.format(self.ssh_key_path, command)
        full_cmd = "ssh-agent bash -c '{}'".format(git_cmd)
        print("running {}".format(full_cmd))
        self.run_command(full_cmd)
        if in_repo_directory:
            os.chdir(self.working_dir)

    def setup_repo(self):
        """Clones or pulls the repo specified in the constructor"""
        if not os.path.isdir(self.repo_dir):
            # Make sure we are in the working directory
            os.chdir(self.working_dir)
            print("Cloning repository...")
            print("Running git clone {}".format(self.github_repo))
            self.run_git_command(
                "git clone git@github.com:{}.git website".format(
                    self.github_repo_key), in_repo_directory=False)
            os.chdir(self.working_dir)
        print("Pulling repository...")
        self.run_git_command("git checkout master")
        self.run_git_command("git pull")
        # Once the repo is cloned / pulled then instantiate a new Repo Object
        repo = Repo(self.repo_dir)
        print("Verifying branch exists...")
        # Get a list of branch names
        repo_heads_names = [h.name for h in repo.branches]
        # Loop over currnet branches to check if 
        if self.change_branch in repo_heads_names:
            print("Branch found...")
            self.run_git_command("git checkout {}".format(self.change_branch))
            # Pull the latest changes once we've checked out the change branch.
            self.run_git_command("git pull origin {}".format(self.change_branch))
        else:
            print("Creating branch...")
            self.run_git_command("git checkout -b {}".format(self.change_branch))
        # Return the repo object
        return repo

    def create_update_pull_request(self, title, body, commit_message):
        """ Create a GitHub pull request with the latest Connect Jekyll posts"""
        # Only use run_git_command when we need the SSH key involved.
        print("Committing and pushing latest changes to remote head: {}".format(self.repo.active_branch.name))
        self.run_repo_command("git add --all")
        self.run_repo_command(
            "git commit -m '{}'".format(commit_message))
        self.run_git_command(
            "git push --set-upstream origin {}".format(self.repo.active_branch.name))

        headers = {'Authorization': 'token {}'.format(self.auth_token)}
        # Pull request API URL
        url = "https://api.github.com/repos/{}/pulls".format(
            self.github_repo_key)
        # Get the current pull requests to check a PR is not already open
        current_pull_requests = requests.get(url, headers=headers)
        if current_pull_requests.status_code != 200:
            print("ERROR: Failed to get list of current pull requests")
            print(current_pull_requests.text)
            self.error = True
            return False
        else:
            print("Current pull requests:")
            json = current_pull_requests.json()
            pull_open = False
            for pull in json:
                if pull["head"]["ref"] == self.repo.active_branch.name:
                    pull_open = True 
        if not pull_open:
            data = {
                "title": title,
                "body": body,
                "head": self.repo.active_branch.name,
                "base": "master"
            }
            result = requests.post(url, json=data, headers=headers)
            if result.status_code != 201:
                print("ERROR: Failed to create pull request")
                print(result.text)
                self.error = True
                return False
            else:
                json = result.json()
                print("Pull request created: {}".format(json["html_url"]))
                data = {
                    "reviewers": self.reviewers
                }
                url = "https://api.github.com/repos/{0}/pulls/{1}/requested_reviewers".format(
                    self.github_repo_key, json["number"])
                result = requests.post(url, json=data, headers=headers)
                if result.status_code != 201:
                    print("ERROR: Failed to add reviewers to the pull request")
                    print(result.text)
                    self.error = True
                    return False

        # Fix for https://stackoverflow.com/questions/36984371/your-configuration-specifies-to-merge-with-the-branch-name-from-the-remote-bu
        # Remove the local branch so that git pull doesn't complain that the remote head doesn't exist if the branch is deleted.
        last_active_branch = self.repo.active_branch.name
        print("Checking out master...")
        self.run_repo_command("git checkout master")
        print("Deleting local update branch...")
        self.run_repo_command("git branch -D {}".format(last_active_branch))
        return True
