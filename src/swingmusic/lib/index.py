import gc
import logging
from time import time

from swingmusic.db.libdata import TrackTable
from swingmusic.lib.tagger import IndexTracks
from swingmusic.lib.populate import CordinateMedia
from swingmusic.lib.recipes.recents import RecentlyAdded

from swingmusic.store.albums import AlbumStore
from swingmusic.store.tracks import TrackStore
from swingmusic.store.folder import FolderStore
from swingmusic.store.artists import ArtistStore
from swingmusic.store.general import GeneralStore

from swingmusic.lib.mapstuff import (
    map_favorites,
    map_album_colors,
    map_scrobble_data,
    map_artist_colors,
    map_trackhash_repairs,
)
from swingmusic.utils.threading import background

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


@background
def index_everything(full_scan: bool = False):
    """
    Indexes everything.

    :param full_scan: Whether to perform a full scan of the root directories.
    """

    if full_scan:
        prepare_full_scan()

    IndexTracks()

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

    CordinateMedia(instance_key=str(time()), overwrite_track_thumbnails=full_scan)
    GeneralStore.end_full_scan()

    gc.collect()
    log.info("Indexing completed")
