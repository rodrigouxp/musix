"""
Prepares the server for use.
"""

from dataclasses import asdict
from time import time
import uuid

from musix.config import UserConfig
from musix.lib.crypto import Cryptography
from musix.db.userdata import UserTable
from musix.lib.mapstuff import (
    map_album_colors,
    map_artist_colors,
    map_favorites,
    map_scrobble_data,
    map_trackhash_repairs,
)
from musix.setup.sqlite import setup_sqlite
from musix.store.albums import AlbumStore
from musix.store.artists import ArtistStore
from musix.store.folder import FolderStore
from musix.store.general import GeneralStore
from musix.store.tracks import TrackStore
from musix.utils.generators import get_random_str


def is_uuid4(value: str) -> bool:
    """
    Check if a string is a valid UUID4 used in pre-v3
    """
    try:
        uuid.UUID(value)
    except (ValueError, TypeError):
        return False

    return True


def run_setup():
    """
    Creates the config directory, runs migrations, and loads settings.
    """

    # setup config file
    config = UserConfig()
    config.setup_config_file()

    if config.serverId and is_uuid4(config.serverId):
        # Save legacy serverId to legacy_serverId
        config.legacy_serverId = config.serverId
        config.serverId = ""
        config.write_to_file(asdict(config))

    if not config.serverId or not Cryptography.private_key_exists():
        # Generate new ed25519 keypair
        crypto = Cryptography()

        # Set serverId to the public key
        config.serverId = crypto.public_key
        config.write_to_file(asdict(config))

    setup_sqlite()


def load_into_mem():
    """
    Load all tracks, albums, and artists into memory.
    """
    # INFO: Load all tracks, albums, and artists data into memory
    key = str(time())
    GeneralStore.load_onboarding_data(list(UserTable.get_all()))
    TrackStore.load_all_tracks(get_random_str())
    AlbumStore.load_albums(key)
    ArtistStore.load_artists(key)
    FolderStore.load_filepaths()

    # INFO: Re-key orphaned user data before mapping it
    map_trackhash_repairs()

    map_scrobble_data()
    map_favorites()
    map_artist_colors()
    map_album_colors()
