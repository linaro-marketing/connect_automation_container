#!/usr/bin/env python3

import argparse
import datetime
import os
from slugify import slugify
import subprocess
import frontmatter
import time
import re
import shlex
from social_image_generator import SocialImageGenerator
from sched_data_interface import SchedDataInterface
from connect_json_updater import ConnectJSONUpdater
from jekyll_post_tool import JekyllPostTool
from sched_presentation_tool import SchedPresentationTool
from connect_youtube_uploader import ConnectYoutubeUploader
import vault_auth
from github_automation import GitHubManager

VAULT_URL = "https://login.linaro.org:8200"
VAULT_ROLE = "vault_connect_automation"

class AutomationContainer:
    def __init__(self, args):
        # Define the CDN URL for Connect static resources
        self.cdn_url = "https://static.linaro.org"
        self.responsive_image_widths = [300, 800, 1200]
        self.work_directory = "/app/work_dir/"
        self.github_reviewers = ["kylekirkby", "pcolmer"]
        # Args
        self.args = args
        self.static_bucket = "static-linaro-org"
        self.accepted_variables = [
            "bamboo_sched_password",
            "bamboo_sched_url",
            "bamboo_connect_uid",
            "bamboo_working_directory",
            "bamboo_github_access_password",
            "bamboo_s3_session_id"]
        self.env = self.get_environment_variables(
            self.accepted_variables)
        if (self.env["bamboo_sched_url"] and
            self.env["bamboo_sched_password"] and
                self.env["bamboo_connect_uid"]):
            # Instantiate the SchedDataInterface which is used by other modules for the data source
            self.sched_data_interface = SchedDataInterface(
                self.env["bamboo_sched_url"],
                self.env["bamboo_sched_password"],
                self.env["bamboo_connect_uid"])
            self.json_data = self.sched_data_interface.getSessionsData()
            # Instantiate the ConnectJSONUpdater module
            self.s3_interface = ConnectJSONUpdater(
                "static-linaro-org", "connect/{}/".format(self.env["bamboo_connect_uid"].lower()), self.json_data, self.work_directory)
            # Run the main logic method (daily-tasks or upload-video)
            self.main()
        else:
            print(
                "Missing bamboo_sched_url, bamboo_sched_password and bamboo_connect_uid environment variables")

    def main(self):
        """Takes the argparse arguments as input and starts scripts"""

        print("Linaro Connect Automation Container")
        if self.args.upload_video:
            self.upload_video(
                self.env["bamboo_s3_session_id"])
        elif self.args.daily_tasks:
            self.daily_tasks()
        elif self.args.social_images:
            self.social_media_images()
        elif self.args.upload_presentations:
            self.update_presentations(
                "{}presentations/".format(self.work_directory), "{}other_files/".format(self.work_directory))
        else:
            print("Please provide either the --upload-video or --daily-tasks flag ")

    def get_environment_variables(self, accepted_variables):
        """Gets an environment variables that have been set i.e bamboo_sched_password"""
        found_variables = {}
        for variable in accepted_variables:
            variable_check = os.environ.get(variable)
            if variable_check:
                found_variables[variable] = variable_check
        return found_variables

    def get_vault_secret(self, secret_path):
        secret = vault_auth.get_secret(
            secret_path,
            iam_role=VAULT_ROLE,
            url=VAULT_URL
        )
        return secret["data"]["pw"]

    def get_secret_from_vault(self, vault_path, output_file_name):
        """Used to retrive a secret json file from the linaro-its vault_auth module"""

        secret_output_path = self.work_directory

        secret_output_full_path = secret_output_path + output_file_name

        if not os.path.isfile(secret_output_full_path):
            secret = self.get_vault_secret(vault_path)
            with open(secret_output_full_path, 'w') as file:
                file.write(secret)
        return secret_output_path, output_file_name

    def upload_video(self, session_id):
        """Handles the upload of a video"""
        if (self.env["bamboo_sched_url"] and
            self.env["bamboo_sched_password"] and
            self.env["bamboo_working_directory"] and
            self.env["bamboo_s3_session_id"] and
                self.env["bamboo_connect_uid"]):
            secrets_path, secrets_file_name = self.get_secret_from_vault(
                "secret/misc/connect_google_secret.json", "youtube_secret.json")
            uploader = ConnectYoutubeUploader(secrets_path, secrets_file_name)
            print("Uploading video for {} to YouTube".format(session_id))
            print("Uploaded!")
        else:
            print("You're missing one of the required environment variables bamboo_sched_url, bamboo_sched_password, bamboo_connect_uid, bamboo_youtube_client_secret, bamboo_s3_session_id")

    def run_command(self, command):
        print("Executing: {}".format(command))
        # # Use Shlex to split the command for subprocess to handle stdout correctly.
        split_command = shlex.split(command)

        process = subprocess.Popen(
            split_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output, err = process.communicate()
        decoded_output = output.decode("utf-8")
        print(decoded_output)

    def generate_responsive_images(self, base_image_directory):
        print("Resizing social share images...")

        # For each width in widths, generated new JPEG images
        for width in self.responsive_image_widths:
            print("Resizing images to {} width...".format(str(width)))
            if not os.path.exists(base_image_directory + str(width)):
                os.makedirs(base_image_directory + str(width))
            # Use mogrify to generate JPG images of different sizes
            self.run_command(
                "mogrify -path {1}{0}/ -resize {0} -format jpg {1}*.png".format(str(width), base_image_directory))

    def upload_images_to_s3(self, base_image_directory):
        """Uploads responsive social media images generated images to s3"""

        print("Uploading generated social media share images to s3...")
        print("Syncing original PNG images...")

        self.run_command("aws s3 sync {0} s3://{1}/connect/{2}/images/".format(
            base_image_directory, self.static_bucket, self.env["bamboo_connect_uid"].lower()))

        print("Uploading ImageMagick resized images...")

        for width in self.responsive_image_widths:
            print("Syncing {} width images...".format(width))
            self.run_command(
                "aws s3 sync {0}/{3}/ s3://{1}/connect/{2}/images/{3}/".format(base_image_directory, self.static_bucket, self.env["bamboo_connect_uid"].lower(), width))
            print()
    def update_presentations(self, presentation_directory, other_files_directory):

        """
        This method will download any new presentations from the Sched API using
        the SchedDataInterface and upload these to the static AWS S3 CDN bucket
        """
        self.sched_presentation_tool = SchedPresentationTool(
            presentation_directory, other_files_directory, self.json_data)
        self.sched_presentation_tool.download()
        print("Uploading presentations to s3...")
        if not self.args.no_upload:
            self.run_command(
                "aws s3 sync {0} s3://{1}/connect/{2}/presentations/".format(presentation_directory, self.static_bucket, self.env["bamboo_connect_uid"].lower()))
            print("Uploading other files to s3...")
            self.run_command(
                "aws s3 sync {0} s3://{1}/connect/{2}/other_files/".format(other_files_directory, self.static_bucket, self.env["bamboo_connect_uid"].lower()))

    def daily_tasks(self):
        """Handles the running of daily_tasks"""
        start_time = time.time()
        print("Daily Connect Automation Tasks starting...")
        self.github_manager = self.setup_github_manager()
        print("Creating Jekyll Posts...")
        self.post_tool = JekyllPostTool(
            {"output": "{}website/_posts/{}/sessions/".format(self.work_directory, self.env["bamboo_connect_uid"].lower())}, verbose=True)
        self.update_jekyll_posts()
        print("Creating GitHub pull request with changed Jekyll posts...")
        self.social_media_images()
        print("Updating session presentations...")
        self.update_presentations("{}presentations/".format(self.work_directory), "{}other_files/".format(self.work_directory))
        print("Updating the resources.json file...")
        self.s3_interface.update()
        print("resources.json file updated...")
        end_time = time.time()
        print("Daily tasks complete in {} seconds.".format(end_time-start_time))

    def setup_github_manager(self):
        secret_output_path, output_file_name = self.get_secret_from_vault(
            "secret/misc/linaro-build-github.pem", "linaro-build-github.pem")
        full_ssh_path = secret_output_path + output_file_name
        self.run_command("chmod 400 {}".format(full_ssh_path))
        github_manager = GitHubManager(
            "https://github.com/linaro/connect", self.work_directory, "/app", full_ssh_path, self.env["bamboo_github_access_password"], self.github_reviewers)
        return github_manager

    def update_jekyll_posts(self):

        current_posts = self.get_list_of_files_in_dir_based_on_ext("{}website/_posts/{}/sessions/".format(self.work_directory, self.env["bamboo_connect_uid"].lower()),".md")

        latest_session_ids = list(self.json_data.keys())
        current_session_ids = self.get_current_session_ids_from_posts()

        files_have_been_changed = False

        current_date = datetime.datetime.now().strftime("%y%m%d-%H%M")

        for session in self.json_data.values():
            session_image = {
                "path": "{}/connect/{}/images/{}.png".format(self.cdn_url, self.env["bamboo_connect_uid"].lower(), session["session_id"]),
                "featured": "true"
            }
            try:
                speakers = session["speakers"]
            except Exception:
                speakers = None
            try:
                description = session["description"]
            except Exception:
                description = ""
            # Get the list of speakers in the correct format for the Connect Jekyll website
            new_speakers = []
            if speakers:
                for speaker in speakers:
                    new_speaker = {
                        "speaker_name": speaker["name"],
                        "speaker_position": speaker["position"],
                        "speaker_company": speaker["company"],
                        "speaker_image": speaker["avatar"],
                        "speaker_bio": speaker["about"],
                        "speaker_role": speaker["role"]
                    }
                    new_speakers.append(new_speaker)
            post_frontmatter = {
                "title": session["session_id"] + " - " + session["name"],
                "session_id": session["session_id"],
                "session_speakers": new_speakers,
                "description": description,
                "image": session_image,
                "tags": session["event_type"],
                "categories": [self.env["bamboo_connect_uid"].lower()],
                "session_track": session["event_type"],
                "tag": "session",
            }

            found = False
            changed = False

            lower_case_session_id = session["session_id"].lower()
            changed_post_path = ""
            for current_post_path in current_posts:
                if lower_case_session_id in current_post_path:
                    found = True
                    # Load current front matter
                    with open(current_post_path) as current_post:
                        current_post_obj = frontmatter.loads(current_post.read())
                        # Set the front matter
                        front_matter = current_post_obj.metadata
                        if front_matter != post_frontmatter:
                            changed = True
                            changed_post_path = current_post_path
            if found:
                if changed:
                    files_have_been_changed = True
                    print("Updating post for {}".format(session["session_id"]))
                    post_file_name = current_date + "-" + lower_case_session_id + ".md"
                    # Edit posts if file already exists
                    self.post_tool.write_post(
                        post_frontmatter, "", post_file_name, changed_post_path)
            else:
                files_have_been_changed = True
                print("Writing new post...")
                post_file_name = current_date + "-" + lower_case_session_id + ".md"
                 # Edit posts if file already exists
                self.post_tool.write_post(post_frontmatter, "", post_file_name)

        # Delete sessions that don't exist in latest export
        for current_session_id in current_session_ids:
            if current_session_id not in latest_session_ids:
                files_have_been_changed = True
                file_to_delete = self.get_list_of_files_in_dir_based_on_ext(
                    "{}/website/_posts/{}/sessions/".format(self.work_directory, self.env["bamboo_connect_uid"].lower()), "{}.md".format(current_session_id.lower()))[0]
                self.run_command("rm {}".format(file_to_delete))

        # Commit and create the pull request
        if self.github_manager.repo.is_dirty():
            self.github_manager.create_branch("session-update-{}".format(current_date))
            self.github_manager.commit_and_push("Session update - {}".format(self.github_manager.repo.active_branch.name))
            self.github_manager.create_github_pull_request("Session update for {}".format(current_date), "Session posts updated by the ConnectAutomation container.")
        else:
            print("No changes to push!")


    def get_list_of_files_in_dir_based_on_ext(self, folder, extension):
        file_list = []
        for file in os.listdir(folder):
            if file.endswith(extension):
                file_list.append(os.path.join(folder, file))
        return file_list

    def get_current_session_ids_from_posts(self):
        file_list = self.get_list_of_files_in_dir_based_on_ext(
            "{}/website/_posts/{}/sessions/".format(self.work_directory, self.env["bamboo_connect_uid"].lower()), ".md")

        current_ids = []
        for each in file_list:
            # Get the first item found based on the regex
            try:
                # Get the first item found based on the regex
                                # Check if we should delete
                session_id_regex = re.compile(
                    '{}-[A-Za-z]*[0-9]+k*[0-9]*'.format(self.env["bamboo_connect_uid"].lower()))
                session_id = session_id_regex.findall(each)[0]
                current_ids.append(session_id.upper())
            # If no session ID exists then skip the session and output a warning
            except Exception as e:
                print(e)
        return current_ids

    def social_media_images(self):
        self.social_image_generator = SocialImageGenerator(
            {"output": "{}images/".format(self.work_directory), "template": "{}assets/templates/{}-placeholder.jpg".format(self.work_directory, self.env["bamboo_connect_uid"].lower()), "assets_path": "/app/assets/"})
        print("Generating Social Media Share Images...")
        self.generate_images()
        self.generate_responsive_images("{}images/".format(self.work_directory))
        if self.args.no_upload != True:
            self.upload_images_to_s3("{}images/".format(self.work_directory))

    def generate_images(self):

        for session in self.json_data.values():
            try:
                speaker_avatar_url = session["speakers"][0]["avatar"].replace(
                    ".320x320px.jpg", "")
                if len(speaker_avatar_url) < 3:
                    speaker_image = "placeholder.jpg"
                else:
                    file_name = self.social_image_generator.grab_photo(
                        speaker_avatar_url, slugify(session["speakers"][0]["name"]))
                    speaker_image = file_name
                session_speakers = session["speakers"][0]["name"]
            except Exception:
                print("{} has no speakers".format(session["name"]))
                speaker_image = "placeholder.jpg"
                session_speakers = "TBC"

            # Create the image options dictionary
            image_options = {
                "file_name": session["session_id"],
                "elements": {
                    "images": [
                        {
                            "dimensions": {
                                "x": 300,
                                "y": 300
                            },
                            "position": {
                                "x": 820,
                                "y": 80
                            },
                            "image_name": speaker_image,
                            "circle": "True"
                        }
                    ],
                    "text": [
                        {
                            "multiline": "True",
                            "centered": "True",
                            "wrap_width": 28,
                            "value": session_speakers,
                            "position": {
                                "x": [920, 970],
                                "y": 400
                            },
                            "font": {
                                "size": 32,
                                "family": "fonts/Lato-Regular.ttf",
                                "colour": {
                                    "r": 255,
                                    "g": 255,
                                    "b": 255
                                }
                            }
                        },
                        {
                            "multiline": "False",
                            "centered": "False",
                            "wrap_width": 28,
                            "value": session["session_id"],
                            "position": {
                                "x": 80,
                                "y": 340
                            },
                            "font": {
                                "size": 48,
                                "family": "fonts/Lato-Bold.ttf",
                                "colour": {
                                    "r": 255,
                                    "g": 255,
                                    "b": 255
                                }
                            }
                        },
                        {
                            "multiline": "False",
                            "centered": "False",
                            "wrap_width": 28,
                            "value": session["event_type"],
                            "position": {
                                "x": 80,
                                "y": 400
                            },
                            "font": {
                                "size": 28,
                                "family": "fonts/Lato-Bold.ttf",
                                "colour": {
                                    "r": 255,
                                    "g": 255,
                                    "b": 255
                                }
                            }
                        },
                        {
                            "multiline": "True",
                            "centered": "False",
                            "wrap_width": 28,
                            "value": session["session_title"],
                            "position": {
                                "x": 80,
                                "y": 440
                            },
                            "font": {
                                "size": 48,
                                "family": "fonts/Lato-Bold.ttf",
                                "colour": {
                                    "r": 255,
                                    "g": 255,
                                    "b": 255
                                }
                            }
                        }
                    ],
                }
            }
            # Generate the image
            self.social_image_generator.create_image(image_options)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Connect Automation")
    parser.add_argument('--upload-video', action='store_true',
                        help='If specified, the video upload method is executed. Requires a -u arg with the session id.')
    parser.add_argument('--daily-tasks', action='store_true',
                        help='If specified, the daily Connect automation tasks are run.')
    parser.add_argument('--no-upload', action='store_true',
                        help='If specified, assets are not uploaded to s3.')
    parser.add_argument('--social-images', action='store_true',
                        help='If specified, only the social media share images task is executed.')
    parser.add_argument('--jekyll-posts', action='store_true',
                        help='If specified, only the social media share images task is executed.')
    parser.add_argument('--upload-presentations', action='store_true',
                        help='If specified, only the social media share images task is executed.')
    args = parser.parse_args()
    AutomationContainer(args)
