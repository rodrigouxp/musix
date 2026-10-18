import gc
import logging
from time import time

from musix.db.libdata import TrackTable
from musix.lib.tagger import IndexTracks
from musix.lib.populate import CordinateMedia
from musix.lib.recipes.recents import RecentlyAdded

from musix.store.albums import AlbumStore
from musix.store.tracks import TrackStore
from musix.store.folder import FolderStore
from musix.store.artists import ArtistStore
from musix.store.general import GeneralStore

from musix.lib.mapstuff import (
    map_favorites,
    map_album_colors,
    map_scrobble_data,
    map_artist_colors,
    map_trackhash_repairs,
)
from musix.utils.threading import background

log = logging.getLogger(__name__)


def prepare_full_scan():
    """
    Prepares the server state for a full scan.

    Drops the tracks db table.
    Resets in-memory stores.
    Does NOT remove scrobbles, favorites, playlists, collections, and other user data.
    """

    TrackTable.reset()
    TrackStore.reset()
    ArtistStore.reset()
    AlbumStore.reset()
    FolderStore.reset()

    GeneralStore.start_full_scan()


def reload_stores():
    """
    Loads the tracks, albums and artists from the database into memory again,
    and maps the user data (colours, plays, favorites) onto them.

    This is the part of ``index_everything`` that follows the reading of the files.
    """
    key = str(time())
    TrackStore.load_all_tracks(key)
    AlbumStore.load_albums(key)
    ArtistStore.load_artists(key)
    FolderStore.load_filepaths()

    # NOTE: Rebuild recently added items on the homepage store
    RecentlyAdded()

    # map colors
    map_album_colors()
    map_artist_colors()

    # INFO: Re-key orphaned user data before mapping it
    map_trackhash_repairs()

    map_scrobble_data()
    map_favorites()


@background
def index_everything(full_scan: bool = False):
    """
    Indexes everything.

    :param full_scan: Whether to perform a full scan of the root directories.
    """

    if full_scan:
        prepare_full_scan()

    IndexTracks()
    reload_stores()

    CordinateMedia(instance_key=str(time()), overwrite_track_thumbnails=full_scan)
    GeneralStore.end_full_scan()

    gc.collect()
    log.info("Indexing completed")
