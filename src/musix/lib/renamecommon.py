"""
What the renamers of an artist (``artistrename.py``) and of an album
(``albumrename.py``) share:

- the state of the (only) job, and the lock that lets one job run at a time in the whole
  app, whatever its kind;
- the thread that runs a job in the background;
- ``update_hashes``: after the files were written, reads them again, moves everything
  the app keeps under a hash (favorites, plays, collections, thumbnails...) to the new
  hash and loads the stores again.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from musix.lib.index import reload_stores
from musix.lib.rekey import log_rekey, refresh_track_extras, rekey_hash
from musix.lib.trackrename import RenameError, ensure_album_thumbnails, reindex_files
from musix.models.track import Track
from musix.store.tracks import TrackStore

log = logging.getLogger(__name__)


# SECTION: the job


class BaseJobState:
    """
    The state of a rename job. Each kind of rename has its own subclass (the status of
    the job is read from it), but they all share ``lock``, and ``begin`` refuses to
    start while a job of any kind is running.
    """

    lock = threading.Lock()
    running = False
    done = 0
    total = 0
    current: str | None = None
    errors: dict[str, str] = {}
    result: dict[str, Any] | None = None
    started = 0.0
    finished = 0.0

    # how the job is called in the message of the 409
    kind = "rename"

    @classmethod
    def begin(cls):
        """
        Marks the job as running and clears the last one. Raises ``RenameError(409)`` when
        a rename (of any kind) is already running. Subclasses set their own fields after.
        """
        with BaseJobState.lock:
            for state in BaseJobState.__subclasses__():
                if state.running:
                    raise RenameError(409, f"Another {state.kind} rename is already running")

            cls.running = True
            cls.done = 0
            cls.total = 0
            cls.current = None
            cls.errors = {}
            cls.result = None
            cls.started = time.time()

    @classmethod
    def finish(cls, result: dict[str, Any]):
        cls.current = None
        cls.result = result
        cls.finished = time.time()
        cls.running = False


def run_in_background(
    state: type[BaseJobState], work: Callable[[], dict[str, Any]], name: str, wait: bool = False
):
    """
    Runs ``work`` (which returns the result of the job) in a thread and stores what it
    returns in ``state``. An error that escapes is logged and becomes the result.
    """

    def run():
        try:
            result = work()
        except Exception as error:
            log.exception(f"{name} failed")
            result = {"error": f"{type(error).__name__}: {error}"}

        state.finish(result)

    thread = threading.Thread(target=run, name=name, daemon=True)
    thread.start()

    if wait:
        thread.join()


# SECTION: the hashes


class WrittenFile(Protocol):
    """
    A file that was written (an ``artistrename.FilePlan``, an ``albumrename.AlbumFilePlan``).
    """

    track: Track
    path: Any
    new_path: Any


@dataclass
class HashUpdate:
    # how many tracks and albums were moved, plus what ``after_moved`` added
    moved: dict[str, Any] = field(default_factory=dict)
    # old album hash -> the hashes its written files got
    album_map: dict[str, list[str]] = field(default_factory=dict)


def update_hashes(
    ok: list[WrittenFile],
    after_moved: Callable[[dict[str, Any]], None] | None = None,
) -> HashUpdate:
    """
    Reads the written files again, moves the data from the old hashes to the new ones
    and loads the stores again.

    A hash is moved only when every file under it was written: otherwise some file still
    has the old hash and its data has to stay.

    :param after_moved: called with what was moved, before the stores are loaded again
        (the artist rename moves the artist here)
    """
    old_to_new = {p.path.as_posix(): (p.new_path or p.path).as_posix() for p in ok}
    new_tracks = reindex_files(old_to_new)

    # old hash -> the new hashes its files got, and how many of its files were written
    track_map: dict[str, set[str]] = {}
    album_map: dict[str, set[str]] = {}
    written_per_track: dict[str, int] = {}
    written_per_album: dict[str, int] = {}

    for plan in ok:
        new_track = new_tracks.get((plan.new_path or plan.path).as_posix())

        if new_track is None:
            continue

        old = plan.track
        track_map.setdefault(old.trackhash, set()).add(new_track.trackhash)
        album_map.setdefault(old.albumhash, set()).add(new_track.albumhash)
        written_per_track[old.trackhash] = written_per_track.get(old.trackhash, 0) + 1
        written_per_album[old.albumhash] = written_per_album.get(old.albumhash, 0) + 1

    moved: dict[str, Any] = {"tracks": 0, "albums": 0}

    for old, news in track_map.items():
        group = TrackStore.trackhashmap.get(old)
        total = len(group.tracks) if group else written_per_track[old]

        if len(news) == 1 and written_per_track[old] == total:
            (new,) = news

            if new != old:
                log_rekey("track", old, new, rekey_hash("track", old, new))
                moved["tracks"] += 1

    from musix.store.albums import AlbumStore

    for old, news in album_map.items():
        entry = AlbumStore.albummap.get(old)
        total = len(
            [
                t
                for th in (entry.trackhashes if entry else [])
                for t in (TrackStore.trackhashmap[th].tracks if th in TrackStore.trackhashmap else [])
                if t.albumhash == old
            ]
        ) or written_per_album[old]

        if len(news) == 1 and written_per_album[old] == total:
            (new,) = news

            if new != old:
                log_rekey("album", old, new, rekey_hash("album", old, new))
                moved["albums"] += 1

    if after_moved is not None:
        after_moved(moved)

    ensure_album_thumbnails(list(new_tracks.values()))
    reload_stores()

    try:
        from musix.lib.recipes.recents import RecentlyPlayed

        RecentlyPlayed()
    except Exception as error:
        log.warning(f"Could not rebuild the recently played row: {error}")

    for trackhash in {t.trackhash for t in new_tracks.values()}:
        try:
            refresh_track_extras(trackhash)
        except Exception as error:
            log.warning(f"Could not refresh the extra info of {trackhash}: {error}")

    return HashUpdate(moved, {old: sorted(news) for old, news in album_map.items()})
