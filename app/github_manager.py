from git import Repo
import vault_auth
import os
import subprocess
from datetime import datetime, timezone
import requests


class GitHubManager:

    def __init__(self, repo_url, working_directory, path_to_ssh_key, auth_token):

        self.github_repo = repo_url
        self.github_repo_key = self.github_repo.lstrip("https://github.com/")
        self.working_dir = working_directory
        self.ssh_key_path = path_to_ssh_key
        self.auth_token = auth_token
        self.error = False
        self.reviewers = ["kylekirkby", "pcolmer"]

    def run_command(self, command):
        result = subprocess.run(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            self.error = True
            print("ERROR: '%s'" % command)
            print(result.stdout.decode("utf-8"))
            print(result.stderr.decode("utf-8"))

    def run_git_command(self, command):
        """ Run a git command on the repo """
        git_cmd = 'ssh-add "%s"; %s' % (self.ssh_key_path, command)
        full_cmd = "ssh-agent bash -c '%s'" % git_cmd
        self.run_command(full_cmd)


    def create_branch(self, repo, branch_name):
        # Name the branch after the date and time
        #

        branch = repo.create_head(branch_name)
        branch.checkout()
        print("Checked out {}".format(branch_name))

    def clone_repo(self):
        """Clones or pulls the repo specified in the constructor"""
        repo_dir = "{}/website".format(self.working_dir)
        if os.path.isdir(repo_dir):
            os.chdir(repo_dir)
            print("Pulling repository...")
            self.run_git_command("git pull")
        else:
            # Make sure we are in the working directory
            os.chdir(self.working_dir)
            print("Cloning website repository")
            self.run_git_command("git clone {}".format(self.github_repo))
        return Repo(repo_dir)

    def create_github_pull_request(self, branch, title, body):
        """ Create a GitHub pull request with the latest Connect Jekyll posts"""


        if not self.error:
            self.check_logo_status()
            self.check_repo_status(repo)
        self.clean_up_repo(repo)

        data = {
            "title": title,
            "body": body,
            "head": repo.active_branch.name,
            "base": "master"
        }

        headers = {'Authorization': 'token {}'.format(self.auth_token)}
        url = "https://api.github.com/repos/{}/pulls".format(
            self.github_repo_key)
        result = requests.post(url, json=data, headers=headers)

        if result.status_code != 201:
            print("ERROR: Failed to create pull request")
            print(result.text)
            self.error = True
        else:
            json = result.json()
            print("Pull request created: {}".format(json["html_url"]))
            data = {
                "reviewers": self.reviewers
            }
            url = "https://api.github.com/repos/{}/pulls/{}/requested_reviewers".format(json["number"], self.github_repo_key)

            result = requests.post(url, json=data, headers=headers)

            if result.status_code != 201:
                print("ERROR: Failed to add reviewers to the pull request")
                print(result.text)
                self.error = True


if __name__ == "__main__":
    gh_man = GitHubManager()
