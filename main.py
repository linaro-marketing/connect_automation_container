#!/usr/bin/env python3

import argparse
import datetime
import os
from slugify import slugify

from social_image_generator import SocialImageGenerator
from sched_data_interface import SchedDataInterface
from connect_json_updater import ConnectJSONUpdater
from jekyll_post_tool import JekyllPostTool
from sched_presentation_tool import SchedPresentationTool

# if args.jekyll_posts:
#     post_tool = JekyllPostTool(
#         "https://linaroconnectsandiego.sched.com", SCHED_API_KEY, "san19/")
#     create_jekyll_posts(post_tool, json_data, "SAN19")
# data_interface = SchedDataInterface(
#     "https://linaroconnectsandiego.sched.com", SCHED_API_KEY, "SAN19")
# json_data = data_interface.getSessionsData()
# print(json_data)
# Determine the results of the args
# Build Jekyll Markdown posts for Connect sessions
# if args.social_images:
#     print("Generating social media share images")
#     social_image_generator = SocialImageGenerator(
#         {"output": "output", "template": "assets/templates/san19-placeholder.jpg"})
#     generate_images(social_image_generator, json_data)
# if args.update_json:
#     json_updater = ConnectJSONUpdater(
#         "static-linaro-org", "connect/san19/presentations/", "connect/san19/videos/", "connect/san19/resources.json")
#     json_updater.update()
# if args.upload_presentations:
#     upload_presentations = SchedPresentationTool(
#         "https://linaroconnectsandiego.sched.com", "san19")


def create_jekyll_posts(post_tool, json_data, connect_code):

    for session in json_data.values():
        session_image = {
            "path": "/assets/images/featured-images/{}/{}.png".format(connect_code.lower(), session["session_id"]),
                    "featured": "true"
        }
        post_frontmatter = {
            "title": session["session_id"] + " - " + session["name"],
            "session_id": session["session_id"],
            "session_speakers": session["speakers"],
            # "description": "{}".format(session["abstract"]).replace("'", ""),
            "image": session_image,
            "tags": session["event_type"],
            "categories": [connect_code],
            "session_track": session["event_type"],
            "tag": "session",
        }
        post_file_name = datetime.datetime.now().strftime(
            "%Y-%m-%d") + "-" + session["session_id"].lower() + ".md"
        # Edit posts if file already exists
        post_tool.write_post(post_frontmatter, "", post_file_name)


def generate_images(social_image_generator, json_data):

    for session in json_data.values():
        for speaker in session["speakers"]:
            speaker_avatar_url = speaker["avatar"]
            if len(speaker_avatar_url) < 3:
                speaker["image"] = "placeholder.jpg"
            else:
                file_name = social_image_generator.grab_photo(
                    speaker_avatar_url, slugify(speaker["name"]))
                speaker["image"] = file_name
        # speakers_list = session["speakers"]
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
                        "image_name": session["speakers"][0]["image"],
                        "circle": "True"
                    }
                ],
                "text": [
                    {
                        "multiline": "True",
                        "centered": "True",
                        "wrap_width": 28,
                        "value": "test",
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
                        "value": session["name"],
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
        # Generate the image for each sesssion
        social_image_generator.create_image(image_options)


class AutomationContainer:
    def __init__(self, args):
        self.args = args
        self.accepted_variables = [
            "bamboo_sched_password", "bamboo_sched_url", "bamboo_connect_uid"]
        self.environment_variables = self.get_environment_variables(
            self.accepted_variables)
        if (self.environment_variables["bamboo_sched_url"] and
            self.environment_variables["bamboo_sched_password"] and
             self.environment_variables["bamboo_connect_uid"]):
            # Instantiate the SchedDataInterface which is used by other modules for the data source
            self.sched_data_interface = SchedDataInterface(
                self.environment_variables["bamboo_sched_url"],
                self.environment_variables["bamboo_sched_password"],
                 self.environment_variables["bamboo_connect_uid"])
            self.main()
        else:
            print(
                "Missing bamboo_sched_url, bamboo_sched_password and bamboo_connect_uid environment variables")

    def main(self):
        """Takes the argparse arguments as input and starts scripts"""

        print("Linaro Connect Automation Container")
        json_data = self.sched_data_interface.getSessionsData()
        print("Data for {} sessions successfully pulled from Sched.com".format(len(json_data)))
        if self.args.upload_video:
            if self.args.uid:
                session_id = self.args.uid
                self.upload_video(session_id)
            else:
                print("Please provide the session id e.g -u BUD20-101")
        if self.args.daily_tasks:
            self.daily_tasks()

    def get_environment_variables(self, accepted_variables):
        """Gets an environment variables that have been set i.e bamboo_sched_password"""
        found_variables = {}
        for variable in accepted_variables:
            variable_check = os.environ.get(variable)
            if variable_check:
                found_variables[variable] = variable_check
        return found_variables

    def upload_video(self, session_id):
        """Handles the upload of a video"""
        print("Uploading video for {} to YouTube".format(session_id))
        print("Uploaded!")

    def daily_tasks(self):
        """Handles the running of daily_tasks"""
        print("Daily Connect Automation Tasks starting...")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Connect Automation")
    parser.add_argument(
        '-u', '--uid', help='Specific the Unique ID for the Linaro Connect event i.e. SAN19')
    parser.add_argument('--upload-video', action='store_true',
                        help='If specified, the video upload method is executed. Requires a -u arg with the session id.')
    parser.add_argument('--daily-tasks', action='store_true',
                        help='If specified, the daily Connect automation tasks are run.')
    args = parser.parse_args()

    AutomationContainer(args)
