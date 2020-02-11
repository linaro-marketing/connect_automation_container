from git import Repo

class GitHubManager():
    def __init__(self):
        pass

    def create_github_pull_request(self, connect_code):
        """ Create a GitHub pull request with the latest Connect Jekyll posts"""

        init_pkf()  # what is this?
        repo = clone_repo()
        create_branch(repo)
        update(repo)
        if not got_error:
            check_logo_status()
            check_repo_status(repo)
        clean_up_repo(repo)

        now = datetime.now()
        data = {
            "title": "{} session post update for {}".format(connect_code, now.strftime("%d-%m-%y")),
            "body": "Automated pull request",
            "head": repo.active_branch.name,
            "base": "master"
        }

        token = os.getenv("bamboo_github_access_password")
        headers = {'Authorization': 'token %s' % token}
        url = "https://api.github.com/repos/Linaro/website/pulls"
        result = requests.post(url, json=data, headers=headers)
        if result.status_code != 201:
            print("ERROR: Failed to create pull request")
            print(result.text)
            got_error = True
        else:
            json = result.json()
            print("Pull request created: %s" % json["html_url"])
            # Request that Kyle reviews this PR
            data = {
                "reviewers": [
                    "kylekirkby"
                ]
            }
            url = (
                "https://api.github.com/repos/Linaro/website/pulls/"
                "%s/requested_reviewers"
            ) % json["number"]
            result = requests.post(url, json=data, headers=headers)
            if result.status_code != 201:
                print("ERROR: Failed to add review to the pull request")
                print(result.text)
                got_error = True
