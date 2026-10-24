"""
"Find missing lyrics": looks the lyrics of the songs that have none up online, in the background,
and saves them as .lrc files next to the songs.

It is a job of its own (not a ``BaseJobState`` of the renames): lyrics change no hash, so there is no
reason to hold the renames and the re-index while it runs.
"""

import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

import requests

from musix.lib.lyricsfinder import (
    LrclibProvider,
    LyricsQuery,
    MusixmatchProvider,
    Provider,
    SearchResult,
    find_and_save,
    has_time_tags,
    read_lrc_text,
    recent_misses,
)
from musix.store.tracks import TrackStore

# at most 2 requests a second to the providers, all of them together
REQUEST_INTERVAL = 0.5  # seconds between two requests
# the wait after a "too many requests" or a server error: BACKOFF_BASE * 2 ** n, up to BACKOFF_MAX
BACKOFF_BASE = 4.0
BACKOFF_MAX = 60.0
RETRIES = 3
# this many songs in a row that could not be looked up (no connection) stop the job
NETWORK_FAILURES_TO_ABORT = 3
MAX_ERRORS_KEPT = 200


class RateLimiter:
    """Lets a request go at most once every `interval` seconds (thread safe)."""

    def __init__(self, interval: float, sleep: Callable[[float], Any] = time.sleep):
        self.interval = interval
        self.sleep = sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self.interval

        if delay > 0:
            self.sleep(delay)


class PacedSession:
    """A requests session that goes through a RateLimiter."""

    def __init__(self, session: Any, limiter: RateLimiter):
        self.session = session
        self.limiter = limiter

    def get(self, *args: Any, **kwargs: Any) -> Any:
        self.limiter.wait()
        return self.session.get(*args, **kwargs)


def paced_providers() -> list[Provider]:
    """The providers of the lyrics finder, with their requests paced for a long job."""
    from musix.plugins.lyrics import LyricsProvider

    limiter = RateLimiter(REQUEST_INTERVAL)
    musixmatch = LyricsProvider()
    musixmatch.session = PacedSession(musixmatch.session, limiter)

    return [LrclibProvider(PacedSession(requests.Session(), limiter)), MusixmatchProvider(musixmatch)]


def first_artist_name(track: Any) -> str:
    artists = getattr(track, "artists", None) or []
    return artists[0]["name"] if artists else ""


def has_lyrics(group_tracks: list[Any]) -> bool:
    """A .lrc with text, lyrics in the tags or a .lrc of a duplicate: any of them is enough."""
    for track in group_tracks:
        if read_lrc_text(track.filepath):
            return True

        extra = getattr(track, "extra", None)
        if isinstance(extra, dict) and extra.get("lyrics"):
            return True

        rlrc = _rlrc_text(track.filepath)
        if rlrc:
            return True

    return False


def _rlrc_text(filepath: str) -> str:
    try:
        return Path(filepath).with_suffix(".rlrc").read_text(encoding="utf-8-sig", errors="replace").strip()
    except OSError:
        return ""


def missing_tracks() -> tuple[list[Any], int]:
    """
    The songs without lyrics (one file for each trackhash: the one with the best bitrate) and
    the number of songs of the library. A song that had no lyrics online recently is not a candidate.
    """
    groups = list(TrackStore.trackhashmap.items())
    skip = recent_misses()
    missing = []

    for trackhash, group in groups:
        if trackhash in skip or not group.tracks:
            continue

        if has_lyrics(list(group.tracks)):
            continue

        missing.append(group.get_best())

    return missing, len(groups)


class LyricsBatch:
    def __init__(
        self,
        providers_factory: Callable[[], list[Provider]] = paced_providers,
        sleep: Callable[[float], Any] | None = None,
    ):
        self.providers_factory = providers_factory
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        # how it waits: an event, so that cancelling does not have to wait for the pause
        self._sleep = sleep or (lambda seconds: self._cancel.wait(seconds))
        self._reset()

    def _reset(self) -> None:
        self.running = False
        self.done = 0
        self.total = 0
        self.found_synced = 0
        self.found_plain = 0
        self.not_found = 0
        self.instrumental = 0
        self.errors: OrderedDict[str, str] = OrderedDict()
        self.current: str | None = None
        self.finished = False
        self.cancelled = False
        self.aborted_reason: str | None = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self.running,
                "done": self.done,
                "total": self.total,
                "found_synced": self.found_synced,
                "found_plain": self.found_plain,
                "not_found": self.not_found,
                "instrumental": self.instrumental,
                "errors": dict(self.errors),
                "current": self.current,
                "finished": self.finished,
                "cancelled": self.cancelled,
                "aborted_reason": self.aborted_reason,
            }

    def start(self) -> bool:
        """Starts the job. False when there is one running already."""
        with self._lock:
            if self.running:
                return False

            self._reset()
            self.running = True
            self._cancel.clear()

        tracks, _ = missing_tracks()

        with self._lock:
            self.total = len(tracks)

        self._thread = threading.Thread(target=self._run, args=(tracks,), daemon=True, name="lyrics-batch")
        self._thread.start()
        return True

    def cancel(self) -> bool:
        """Stops after the song in progress. False when nothing is running."""
        with self._lock:
            if not self.running:
                return False

        self._cancel.set()
        return True

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    # # # # # # # # # # # # # # # # # # # #

    def _run(self, tracks: list[Any]) -> None:
        try:
            providers = self.providers_factory()
            network_failures = 0

            for track in tracks:
                if self._cancel.is_set():
                    with self._lock:
                        self.cancelled = True
                    break

                name = f"{first_artist_name(track)} - {track.title}".strip(" -")

                with self._lock:
                    self.current = name

                result = self._look_up(track, providers)

                if result.reason == "network":
                    network_failures += 1
                else:
                    network_failures = 0

                self._count(track, result)

                if network_failures >= NETWORK_FAILURES_TO_ABORT:
                    with self._lock:
                        self.aborted_reason = "network"
                    break
        except Exception as error:  # a bug must not leave the job "running" for ever
            with self._lock:
                self.aborted_reason = f"error: {error}"
        finally:
            with self._lock:
                self.running = False
                self.finished = True
                self.current = None

    def _look_up(self, track: Any, providers: list[Provider]) -> SearchResult:
        query = LyricsQuery(
            trackhash=track.trackhash,
            title=track.title,
            artist=first_artist_name(track),
            album=track.album,
            duration=int(track.duration or 0),
            filepath=track.filepath,
        )

        result = find_and_save(query, providers=providers)

        for attempt in range(RETRIES):
            if not (result.reason == "network" and result.rate_limited) or self._cancel.is_set():
                break

            self._sleep(min(BACKOFF_BASE * 2**attempt, BACKOFF_MAX))

            if self._cancel.is_set():
                break

            result = find_and_save(query, providers=providers)

        return result

    def _count(self, track: Any, result: SearchResult) -> None:
        with self._lock:
            self.done += 1

            if result.reason is None:
                if result.synced or (result.text and has_time_tags(result.text)):
                    self.found_synced += 1
                else:
                    self.found_plain += 1
            elif result.reason == "not_found":
                self.not_found += 1
            elif result.reason == "instrumental":
                self.instrumental += 1
            else:
                # network, write_failed
                self.errors[track.filepath] = result.reason

                while len(self.errors) > MAX_ERRORS_KEPT:
                    self.errors.popitem(last=False)


batch = LyricsBatch()
