#!/usr/bin/env python3

import argparse
from social_image_generator import SocialImageGenerator
from sched_data_interface import SchedDataInterface

def main(args):
    """Takes the argparse arguments as input and starts scripts"""

    print("Linaro Connect Automation Container")

    # Determine the results of the args


class AutomationContainer:
    def __init__(self):
        # Instatiate the ScehdDataInterface which is used by other modules for the data source
        self.sched_data = SchedDataInterface()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Connect Automation")
    parser.add_argument('-s', '--sched-url', help='Specify the Sched.com URL')
    parser.add_argument('-u', '--uid', help='Specific the Unique ID for the Linaro Connect event i.e. SAN19')
    parser.add_argument('--social-images', action='store_true',
                        help='If specified then the Social Media Share images are generated.')
    parser.add_argument('--update-json', action='store_true',
                        help='If specified the Resources.json file is updated in S3')
    parser.add_argument('-o', '--output', nargs='?', default=None,
                        help='Specify the output directory for storing images and other output')
    args = parser.parse_args()

    main(args)
