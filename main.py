#!/usr/bin/env python3

import argparse
import datetime
from slugify import slugify

from social_image_generator import SocialImageGenerator
from sched_data_interface import SchedDataInterface
from connect_json_updater import ConnectJSONUpdater
from jekyll_post_tool import JekyllPostTool
from sched_presentation_tool import SchedPresentationTool
from secrets import SCHED_API_KEY


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
            "elements" : {
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
                            "x": [920,970],
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
        # Instatiate the ScehdDataInterfa   ce which is used by other modules for the data source
        self.sched_data = SchedDataInterface("https://linaroconnectsandiego.sched.com", SCHED_API_KEY, "SAN19")
        self.args = args
        self.main(args)

    def main(self, args):
        """Takes the argparse arguments as input and starts scripts"""

        print("Linaro Connect Automation Container")

        data_interface = SchedDataInterface(
            "https://linaroconnectsandiego.sched.com", SCHED_API_KEY, "SAN19")
        json_data = data_interface.getSessionsData()
        print(json_data)
        # Determine the results of the args
        # Build Jekyll Markdown posts for Connect sessions
        print(args)
        if args.jekyll_posts:
            post_tool = JekyllPostTool(
                "https://linaroconnectsandiego.sched.com", SCHED_API_KEY, "san19/")
            create_jekyll_posts(post_tool, json_data, "SAN19")
        if args.social_images:
            print("Generating social media share images")
            social_image_generator = SocialImageGenerator(
                {"output": "output", "template": "assets/templates/san19-placeholder.jpg"})
            generate_images(social_image_generator, json_data)
        if args.update_json:
            json_updater = ConnectJSONUpdater(
                "static-linaro-org", "connect/san19/presentations/", "connect/san19/videos/", "connect/san19/resources.json")
            json_updater.update()
        if args.upload_presentations:
            upload_presentations = SchedPresentationTool(
                "https://linaroconnectsandiego.sched.com", "san19")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Connect Automation")
    parser.add_argument('-s', '--sched-url', help='Specify the Sched.com URL')
    parser.add_argument('-u', '--uid', help='Specific the Unique ID for the Linaro Connect event i.e. SAN19')
    parser.add_argument('--social-images', action='store_true',
                        help='If specified then the Social Media Share images are generated.')
    parser.add_argument('--upload-presentations', action='store_true',
                        help='If specified then presentations are uploaded.')
    parser.add_argument('--jekyll-posts', action='store_true',
                        help='If specified Jekyll Posts are generated based on the Sched session data.')
    parser.add_argument('--update-json', action='store_true',
                        help='If specified the Resources.json file is updated in S3')
    parser.add_argument('-o', '--output', nargs='?', default=None,
                        help='Specify the output directory for storing images and other output')
    args = parser.parse_args()

    AutomationContainer(args)
