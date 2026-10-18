"""
This module contains functions for the server
"""

import time

from musix.config import UserConfig
from musix.lib.populate import PopulateCancelledError
from musix.utils.generators import get_random_str
from musix.utils.threading import background
from musix.logger import log


# @background
# def run_periodic_scans():
#     """
#     Runs periodic scans.

#     Periodic scans are checks that run every few minutes
#     in the background to do stuff like:
#     - checking for new music
#     - delete deleted entries
#     - downloading artist images, and other data.
#     """
#     # ValidateAlbumThumbs()
#     # ValidatePlaylistThumbs()

#     while UserConfig().enablePeriodicScans:

#         try:
#         except PopulateCancelledError:
#             log.error("'run_periodic_scans': Periodic scan cancelled.")
#             pass

#         time.sleep(UserConfig().scanInterval)
