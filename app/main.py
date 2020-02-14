#!/usr/bin/env python3

import argparse
import datetime
import os
from slugify import slugify
import subprocess
import time
import shlex
from social_image_generator import SocialImageGenerator
from sched_data_interface import SchedDataInterface
from connect_json_updater import ConnectJSONUpdater
from jekyll_post_tool import JekyllPostTool
from sched_presentation_tool import SchedPresentationTool
from connect_youtube_uploader import ConnectYoutubeUploader
import vault_auth
from github_manager import GitHubManager

VAULT_URL = "https://login.linaro.org:8200"
VAULT_ROLE = "vault_connect_automation"

class AutomationContainer:
    def __init__(self, args):
        # Define the CDN URL for Connect static resources
        self.cdn_url = "https://static.linaro.org"
        self.responsive_image_widths = [300, 800, 1200]
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
                "static-linaro-org", "connect/{}/".format(self.env["bamboo_connect_uid"].lower()), self.json_data)
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
        else:
            print("Please provide either the --upload-video or --daily-tasks flag ")

    def upload_files_to_s3(self, folder, s3_prefix):
        """Upload the files in the specified folder to s3"""
        for filename in os.listdir(folder):
            if filename.endswith(".png"):
                print("*", end="", flush=True)
                self.s3_interface.upload_file_to_s3(
                    os.path.join(folder, filename), s3_prefix + filename)

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

        secret_output_path = "{}/".format(
            self.env["bamboo_working_directory"])

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

    def daily_tasks(self):
        """Handles the running of daily_tasks"""
        start_time = time.time()
        print("Daily Connect Automation Tasks starting...")

        print("Creating Jekyll Posts...")
        self.post_tool = JekyllPostTool(
            {"output": "work_dir/website/_posts/{}/sessions/".format(self.env["bamboo_connect_uid"].lower())}, verbose=True)
        self.update_jekyll_posts()
        print("Creating GitHub pull request with changed Jekyll posts...")
        self.social_image_generator = SocialImageGenerator(
            {"output": "work_dir/images/", "template": "assets/templates/bud20-placeholder.jpg"})
        print("Generating Social Media Share Images...")
        self.generate_images()
        self.generate_responsive_images("/app/work_dir/images/")
        if self.args.no_upload != True:
            self.upload_images_to_s3("/app/work_dir/images/")
        # print("Downloading presentations from sched...")
        # print("Uploading presentations to s3...")
        # print("Updating the resources.json file...")
        end_time = time.time()
        print("Daily tasks complete in {} seconds.".format(end_time-start_time))

    def update_jekyll_posts(self):

        secret_output_path, output_file_name = self.get_secret_from_vault(
            "secret/misc/linaro-build-github.pem", "linaro-build-github.pem")
        full_ssh_path = secret_output_path + output_file_name
        self.run_command("chmod 400 {}".format(full_ssh_path))
        github_manager = GitHubManager(
            "https://github.com/linaro/connect", self.env["bamboo_working_directory"],"/app", full_ssh_path, self.env["bamboo_github_access_password"])
        github_manager.clone_repo()
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
            post_file_name = session["session_id"].lower() + ".md"
            # Edit posts if file already exists
            self.post_tool.write_post(post_frontmatter, "", post_file_name)

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
    args = parser.parse_args()
    AutomationContainer(args)
