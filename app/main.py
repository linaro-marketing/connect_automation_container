#!/usr/bin/env python3

import argparse
import datetime
import json
import os
from slugify import slugify
from jinja2 import utils
import subprocess
import frontmatter
import time
import re
import shlex
import sys
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

import boto3

class AutomationContainer:
    def __init__(self, args):
        # Define the CDN URL for Connect static resources
        self.cdn_url = "https://static.linaro.org"
        self.responsive_image_widths = [300, 800, 1200]
        self.role_arn = "arn:aws:iam::691071635361:role/static-linaro-org-connect_Owner"
        self.role_session_name = "ConnectAutomationContainer"
        self.assume_role(self.role_arn, self.role_session_name)
        self.work_directory = "/app/work_dir/"
        self.github_reviewers = ["kylekirkby", "pcolmer"]
        # Args
        self.args = args
        self.static_bucket = "static-linaro-org"
        self.accepted_variables = [
            "bamboo_sched_password",
            "bamboo_sched_url",
            "bamboo_event_keys",
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

    def assume_role(self, arn, session_name):

        client = boto3.client('sts')
        access = client.assume_role(
            RoleArn=arn,
            RoleSessionName=session_name
            )
        access_key = access["Credentials"]["AccessKeyId"]
        secret_access_key = access["Credentials"]["SecretAccessKey"]
        session_token = access["Credentials"]["SessionToken"]

        os.environ["AWS_ACCESS_KEY_ID"] = access_key
        os.environ["AWS_SECRET_ACCESS_KEY"] = secret_access_key
        os.environ["AWS_SESSION_TOKEN"] = session_token

        return True

    def main(self):
        """Takes the argparse arguments as input and starts scripts"""

        print("Linaro Connect Automation Container")
        if self.args.upload_video:
            self.upload_video(
                self.env["bamboo_s3_session_id"])
        elif self.args.daily_tasks:
            self.daily_tasks()
        elif self.args.update_session:
            self.update_sessions()
        elif self.args.social_images:
            self.social_media_images()
        elif self.args.upload_presentations:
            self.update_presentations(
                "{}presentations/".format(self.work_directory), "{}other_files/".format(self.work_directory))
        else:
            print("Please provide either the --upload-video or --daily-tasks flag ")

    def update_sessions(self):
        """This runs when the flag --update-session is set."""
        start_time = time.time()
        self.event_keys = json.loads(self.env["bamboo_event_keys"])
        for event_key in self.event_keys:
            print(event_key)
        # Updated the Jekyll Posts.
        self.github_manager = self.setup_github_manager()
        print("Updating Jekyll Posts...")
        self.post_tool = JekyllPostTool(
            {"output": "{}website/_posts/{}/sessions/".format(self.work_directory, self.env["bamboo_connect_uid"].lower())}, verbose=True)
        updated_posts = self.update_jekyll_posts()
        if updated_posts:
            created_social_media_images = self.social_media_images()
            if created_social_media_images:
                print("Updating session presentations...")
                updated_presentations = self.update_presentations(
                    "{}presentations/".format(self.work_directory), "{}other_files/".format(self.work_directory))
                if updated_presentations:
                    print("Updating the resources.json file...")
                    updated_resources_json = self.s3_interface.update()
                    if updated_resources_json:
                        print("resources.json file updated...")
                        end_time = time.time()
                        print("Daily tasks complete in {} seconds.".format(end_time - start_time))
                    else:
                        sys.exit(1)
                else:
                    sys.exit(1)
            else:
                sys.exit(1)
        else:
            sys.exit(1)

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
            video_manager = ConnectYoutubeUploader(secrets_path, secrets_file_name)
            video_path = video_manager.download_video("{}/connect/{}/videos/{}.mp4".format(self.cdn_url, self.env["bamboo_connect_uid"].lower(), session_id.lower()),
                             "{}videos/".format(self.work_directory))
            # Get the session data for the given session id
            session_data = self.json_data[session_id.upper()]
            # Create the speakers portion of the YouTube video description
            session_speakers_description = ""
            for speaker in session_data["speakers"]:
                speaker_role = ""
                if speaker["company"] != "" and speaker["position"] != "":
                    speaker_role = f"{speaker['position']} at {speaker['company']}"
                elif speaker["company"] != "":
                    speaker_role = speaker['company']
                elif speaker["position"] != "":
                    speaker_role = speaker['position']
                session_speakers_description += f"{speaker['name']} - {speaker_role} \n {speaker['about']}"
            # Set the session_abstract for the youtube video description
            session_abstract = session_data["description"].replace("<br>","\n").replace("<br/>", "\n")
            # Craft the session url
            connect_website_url = "https://connect.linaro.org/resources/{}/session/{}/".format(
                self.env["bamboo_connect_uid"].lower(), session_id.lower())
            # Format the complete video description
            video_description = """Session Abstract

            {}

            Speakers

            {}

            Visit the Linaro Connect website for the session presentations and more:

            {}
            """.format(session_abstract, session_speakers_description, connect_website_url)
            # Setup the upload payload object
            video_options={
                "file": video_path,
                        "title": session_data["name"],
                        "description": video_description,
                        "tags": "bud20,Open Source,Arm, budapest",
                        "category": "28",
                        "privacyStatus": "private"
            }

            print("Uploading video for {} to YouTube ".format(session_id))
            video_id = video_manager.upload_video(video_options)
            # Set the social media image path

            thumbnail_set = video_manager.set_custom_thumbnail("{}images/{}.png".format(self.work_directory, session_id.upper()), video_id)
            youtube_url = f"https://https://www.youtube.com/watch?v={video_id}"
            print(youtube_url)
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
        if process.returncode != 0:
            print("Error with {} command - exit code({}):".format(command, process.returncode))
            print(err)
            sys.exit(process.returncode)
        else:
            print("Output from '{}' command:".format(command))
            decoded_output = output.decode("utf-8")
            print(decoded_output)

    def generate_responsive_images(self, base_image_directory):
        print("Resizing social share images...")
        try:
            # For each width in widths, generated new JPEG images
            for width in self.responsive_image_widths:
                print("Resizing images to {} width...".format(str(width)))
                if not os.path.exists(base_image_directory + str(width)):
                    os.makedirs(base_image_directory + str(width))
                # Use mogrify to generate JPG images of different sizes
                self.run_command(
                    "mogrify -path {1}{0}/ -resize {0} -format jpg {1}*.png".format(str(width), base_image_directory))
            return True
        except Exception as e:
            print(e)
            return True
    def upload_images_to_s3(self, base_image_directory):
        """Uploads responsive social media images generated images to s3"""

        print("Uploading generated social media share images to s3...")
        print("Syncing original PNG images...")
        try:
            self.run_command("aws s3 sync --include '{3}-*.png' --include '{3}-*.jpg' --exclude '*.png' --exclude '*.jpg' {0} s3://{1}/connect/{2}/images/".format(
                base_image_directory, self.static_bucket, self.env["bamboo_connect_uid"].lower(), self.env["bamboo_connect_uid"]))

            print("Uploading ImageMagick resized images...")

            for width in self.responsive_image_widths:
                print("Syncing {} width images...".format(width))
                self.run_command(
                    "aws s3 sync --include '{4}-*.jpg' --exclude '*.jpg' {0}/{3}/ s3://{1}/connect/{2}/images/{3}/".format(base_image_directory, self.static_bucket, self.env["bamboo_connect_uid"].lower(), width, self.env["bamboo_connect_uid"]))
                print()
            return True
        except Exception as e:
            print(e)
            return False

    def update_presentations(self, presentation_directory, other_files_directory):

        """
        This method will download any new presentations from the Sched API using
        the SchedDataInterface and upload these to the static AWS S3 CDN bucket
        """
        self.sched_presentation_tool = SchedPresentationTool(
            presentation_directory, other_files_directory, self.json_data)
        self.sched_presentation_tool.download()
        print("Uploading presentations to s3...")
        try:
            if not self.args.no_upload:
                self.run_command(
                    "aws s3 sync --exclude '*' --include '{3}-*.pdf'  {0} s3://{1}/connect/{2}/presentations/".format(presentation_directory, self.static_bucket, self.env["bamboo_connect_uid"].lower(), self.env["bamboo_connect_uid"]))
                print("Uploading other files to s3...")
                self.run_command(
                    "aws s3 sync --exclude '*' --include '{3}-*'  {0} s3://{1}/connect/{2}/other_files/".format(other_files_directory, self.static_bucket, self.env["bamboo_connect_uid"].lower(), self.env["bamboo_connect_uid"]))
            return True
        except Exception as e:
            print(e)
            return False

    def daily_tasks(self):
        """Handles the running of daily_tasks"""
        start_time = time.time()
        print("Daily Connect Automation Tasks starting...")
        self.github_manager = self.setup_github_manager()
        print("Creating Jekyll Posts...")
        self.post_tool = JekyllPostTool(
            {"output": "{}website/_posts/{}/sessions/".format(self.work_directory, self.env["bamboo_connect_uid"].lower())}, verbose=True)
        print("Creating Social Media Share Images...")
        created_social_media_images = self.social_media_images()
        if created_social_media_images:
            print("Syncing over share images to website directory...")
            self.run_command("rsync -a --include '{}-*.png' --exclude 'circle_thumbs' --exclude '800' --exclude '300' --exclude '1200' --exclude 'images' --exclude '*.png'  {} {}".format(self.env["bamboo_connect_uid"], "{}images/".format(
                self.work_directory), "{}website/assets/images/featured-images/{}/".format(self.work_directory, self.env["bamboo_connect_uid"].lower())))
            print("Creating GitHub pull request with changed Jekyll posts and images...")
            updated_posts = self.update_jekyll_posts()
            if updated_posts:
                print("Updating session presentations...")
                updated_presentations = self.update_presentations("{}presentations/".format(self.work_directory), "{}other_files/".format(self.work_directory))
                if updated_presentations:
                    print("Updating the resources.json file...")
                    updated_resources_json = self.s3_interface.update()
                    if updated_resources_json:
                        print("resources.json file updated...")
                        print("Invalidating static.linaro.org/connect/{}/* CloudFront cache...".format(self.env["bamboo_connect_uid"]))
                        self.run_command(
                            "aws cloudfront create-invalidation --distribution-id E374OER1SABFCK --paths '/connect/{}/*'".format(self.env["bamboo_connect_uid"]))
                        end_time = time.time()
                        print("Daily tasks complete in {} seconds.".format(end_time - start_time))
                    else:
                        print("Error with updating resources.json.")
                        sys.exit(1)
                else:
                    print("Error with updating presentations.")
                    sys.exit(1)
            else:
                print("Error with updating posts.")
                sys.exit(1)
        else:
            print("Error with creating social media images.")
            sys.exit(1)

    def setup_github_manager(self):
        secret_output_path, output_file_name = self.get_secret_from_vault(
            "secret/misc/linaro-build-github.pem", "linaro-build-github.pem")
        secret = vault_auth.get_secret(
            "secret/github/linaro-build",
            iam_role=VAULT_ROLE,
            url=VAULT_URL
        )
        github_api_access_key =  secret["data"]["pat"]
        print(github_api_access_key)
        full_ssh_path = secret_output_path + output_file_name
        self.run_command("chmod 400 {}".format(full_ssh_path))
        github_manager = GitHubManager(
            "https://github.com/linaro/connect", self.work_directory, full_ssh_path, github_api_access_key, self.github_reviewers, "{}-session-update".format(self.env["bamboo_connect_uid"].lower()))
        return github_manager

    def escape_string(self, string):
        """Prevent XSS attacks"""
        return str(utils.escape(string))

    def update_jekyll_posts(self):

        current_posts = self.get_list_of_files_in_dir_based_on_ext("{}website/_posts/{}/sessions/".format(self.work_directory, self.env["bamboo_connect_uid"].lower()), ".md")

        latest_session_ids = list(self.json_data.keys())
        current_session_ids = self.get_current_session_ids_from_posts()

        files_have_been_changed = False

        current_date = datetime.datetime.now().strftime("%y%m%d-%H%M")

        for session in self.json_data.values():

            session_image = "/assets/images/featured-images/{}/{}.png".format(self.env["bamboo_connect_uid"].lower(), session["session_id"])
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
                        "speaker_name": self.escape_string(speaker["name"]),
                        "speaker_position": self.escape_string(speaker["position"]),
                        "speaker_company": self.escape_string(speaker["company"]),
                        "speaker_image": self.escape_string(speaker["avatar"]),
                        "speaker_bio": self.escape_string("{}".format(speaker["about"])),
                        "speaker_role": self.escape_string(speaker["role"])
                    }
                    new_speakers.append(new_speaker)

            session_slot = {
                "start_time": session["event_start"],
                "end_time": session["event_end"],
            }
            try:
                session_room = session["venue"]
            except KeyError as e:
                session_room = ""


            post_frontmatter = {
                "title": session["name"],
                "session_id": session["session_id"],
                "session_speakers": new_speakers,
                "description": description,
                "image": session_image,
                "session_room": session_room,
                "session_slot": session_slot,
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
                if lower_case_session_id + ".md" in current_post_path:
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
                    post_file_name = datetime.datetime.now().strftime("%Y-%m-%d") + "-" + lower_case_session_id + ".md"
                    # Edit posts if file already exists
                    self.post_tool.write_post(
                        post_frontmatter, "", post_file_name, changed_post_path)
            else:
                files_have_been_changed = True
                print("Not found....")
                print(lower_case_session_id)
                print("Writing new post...")
                post_file_name = datetime.datetime.now().strftime("%Y-%m-%d") + "-" + lower_case_session_id + ".md"
                 # Edit posts if file already exists
                self.post_tool.write_post(post_frontmatter, "", post_file_name)

        # Delete sessions that don't exist in latest export
        for current_session_id in current_session_ids:
            # Check to see if a session has been removed and if so - delete it.
            if current_session_id not in latest_session_ids:
                files_have_been_changed = True
                file_to_delete = self.get_list_of_files_in_dir_based_on_ext(
                    "{}/website/_posts/{}/sessions/".format(self.work_directory, self.env["bamboo_connect_uid"].lower()), "{}.md".format(current_session_id.lower()))[0]
                del_command = "rm {}".format(file_to_delete)
                print(del_command)
                self.run_command(del_command)

        for latest_session_id in latest_session_ids:
            if latest_session_id not in current_session_ids:
                print("New session detected: ".format(latest_session_id))

        # Commit and create the pull request
        if self.github_manager.repo.is_dirty() or len(self.github_manager.repo.untracked_files) > 0:
            created = self.github_manager.create_github_pull_request("Session update for {}".format(current_date), "Session posts updated by the ConnectAutomation container.")
            if created:
                return True
            else:
                return False
        else:
            self.github_manager.run_git_command("git checkout master")
            print("No changes to push!")
            return True


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
            {"output": "{}images/".format(self.work_directory), "template": "/app/assets/templates/{}-placeholder.jpg".format(self.env["bamboo_connect_uid"].lower()), "assets_path": "/app/assets/"})
        print("Generating Social Media Share Images...")
        generated_images = self.generate_images()
        if generated_images:
            generated_responsive_images = self.generate_responsive_images("{}images/".format(self.work_directory))
            if generated_responsive_images:
                if self.args.no_upload != True:
                    uploaded_images_to_s3 = self.upload_images_to_s3("{}images/".format(self.work_directory))
                    if uploaded_images_to_s3:
                        return True
                    else:
                        return False
                return True
            else:
                return False
        else:
            return False


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
                                "y": 140
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
                                "y": 200
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
                                "y": 240
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

        return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Connect Automation")
    parser.add_argument('--upload-video', action='store_true',
                        help='If specified, the video upload method is executed. Requires a -u arg with the session id.')
    parser.add_argument('--daily-tasks', action='store_true',
                        help='If specified, the daily Connect automation tasks are run.')
    parser.add_argument('--update-session', action='store_true',
                        help='If specified, the update_session method task is run.')
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
