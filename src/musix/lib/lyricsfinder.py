"""
Finds the lyrics of a song online and saves them as a ``.lrc`` next to the audio file.

The providers are asked in order (LRCLIB first, Musixmatch as the backup). The first one that has
the lyrics wins; the synced version is preferred, the plain one is accepted.
"""

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import requests

from musix.db.userdata import PluginTable
from musix.settings import Metadata, Paths
from musix.utils.hashing import create_hash
from musix.utils.paths import is_path_within_root_dirs

LRCLIB_URL = "https://lrclib.net/api"
REQUEST_TIMEOUT = 10  # seconds
# LRCLIB answers 503 ("the server is busy") now and then, and the same question works a moment later
SERVER_BUSY_PAUSE = 1.0  # seconds before the one more try
# a lyric of another version of the song (live, extended) is out of time with the audio
DURATION_TOLERANCE = 3  # seconds

MISS_DAYS = 30
INSTRUMENTAL_DAYS = 365


def user_agent() -> str:
    return f"MUSIX/{Metadata.version} (https://github.com/rodrigouxp/musix)"


@dataclass
class LyricsQuery:
    """What is known about the song when the lyrics are asked for."""

    trackhash: str
    title: str
    artist: str
    album: str = ""
    duration: int = 0  # seconds
    filepath: str = ""


@dataclass
class FoundLyrics:
    text: str
    synced: bool
    source: str  # "lrclib" | "musixmatch"


@dataclass
class NotFound:
    # "not_found" | "instrumental" | "network"
    reason: str
    # False when the answer may be different soon (a provider was out of reach): it is not remembered
    cacheable: bool = True
    # a provider said "too many requests" or had a server error: the batch waits and tries again
    rate_limited: bool = False


class ProviderError(Exception):
    """The provider could not be reached or gave an answer that cannot be used."""

    def __init__(self, message: str, rate_limited: bool = False):
        super().__init__(message)
        self.rate_limited = rate_limited


# # # # # # # # # # # # # # # # # # # #
#  Cleaning the title and the artist  #
# # # # # # # # # # # # # # # # # # # #

_IN_BRACKETS = r"\s*[\(\[]\s*(?:{})\s*[\)\]]\s*$"

# Only decoration of a version at the end of the title. What is part of the name
# ("(I Can't Get No) Satisfaction", "Heroes (We Could Be)") is not matched.
_DECORATIONS = [
    re.compile(_IN_BRACKETS.format(r"(?:feat\.?|ft\.?|featuring)\s[^\)\]]*"), re.I),
    re.compile(_IN_BRACKETS.format(r"[^\)\]]*\bremix\b[^\)\]]*"), re.I),
    re.compile(_IN_BRACKETS.format(r"[^\)\]]*\bremaster(?:ed)?\b[^\)\]]*"), re.I),
    re.compile(_IN_BRACKETS.format(r"(?:radio|single|album|mono|stereo)\s+(?:edit|version|mix)"), re.I),
    re.compile(_IN_BRACKETS.format(r"explicit|clean|bonus track"), re.I),
    re.compile(_IN_BRACKETS.format(r"deluxe\b[^\)\]]*"), re.I),
    re.compile(r"\s+-\s+(?:\d{4}\s+)?remaster(?:ed)?(?:\s+\d{4})?\s*$", re.I),
    re.compile(r"\s+-\s+(?:radio|single|album|mono|stereo)\s+(?:edit|version|mix)\s*$", re.I),
    re.compile(r"\s+-\s+[^-]*\bremix\s*$", re.I),
    re.compile(r"\s+(?:feat\.|ft\.|featuring)\s+.+$", re.I),
]


def clean_title(title: str) -> str:
    """
    Takes the decoration of a version off the end of a title ("(feat. X)", "(Remix)",
    "- Remastered 2011"...). It never gives an empty title.
    """
    cleaned = title.strip()

    changed = True
    while changed:
        changed = False

        for pattern in _DECORATIONS:
            shorter = pattern.sub("", cleaned).strip()

            if shorter and shorter != cleaned:
                cleaned = shorter
                changed = True

    return cleaned or title.strip()


_ARTIST_SEPARATOR = re.compile(r"\s+(?:feat\.?|ft\.?|featuring|&)\s+", re.I)


def first_artist(artist: str) -> str:
    """
    A single artist name with a " feat. " or " & " in it: what comes before the first separator.
    """
    first = _ARTIST_SEPARATOR.split(artist.strip(), maxsplit=1)[0].strip()
    return first or artist.strip()


# # # # # # # # # # # # # # # # # # # #
#            Providers                #
# # # # # # # # # # # # # # # # # # # #


class Provider(Protocol):
    name: str

    def lookup(self, query: LyricsQuery) -> FoundLyrics | NotFound:
        """Gives the lyrics, or why there are none. Raises ProviderError when it could not ask."""
        ...


def _text(value: Any) -> str:
    return value if isinstance(value, str) and value.strip() else ""


class LrclibProvider:
    name = "lrclib"

    def __init__(self, session: Any = None, base_url: str = LRCLIB_URL):
        self.session = session if session is not None else requests.Session()
        self.base_url = base_url

    def _get_response(self, endpoint: str, params: dict[str, Any]) -> Any:
        try:
            return self.session.get(
                f"{self.base_url}/{endpoint}",
                params=params,
                headers={"User-Agent": user_agent()},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as e:
            raise ProviderError(str(e))

    def _request(self, endpoint: str, params: dict[str, Any]) -> Any:
        response = self._get_response(endpoint, params)

        if response.status_code >= 500:
            time.sleep(SERVER_BUSY_PAUSE)
            response = self._get_response(endpoint, params)

        if response.status_code == 404:
            return None

        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderError(f"LRCLIB answered {response.status_code}", rate_limited=True)

        if response.status_code != 200:
            raise ProviderError(f"LRCLIB answered {response.status_code}")

        try:
            return response.json()
        except ValueError:
            raise ProviderError("LRCLIB sent an answer that is not JSON")

    @staticmethod
    def _from_item(item: Any) -> FoundLyrics | NotFound | None:
        """What an entry of LRCLIB gives: None when it has no lyrics."""
        if not isinstance(item, dict):
            return None

        if item.get("instrumental"):
            return NotFound("instrumental")

        synced = _text(item.get("syncedLyrics"))
        if synced:
            return FoundLyrics(synced, True, "lrclib")

        plain = _text(item.get("plainLyrics"))
        if plain:
            return FoundLyrics(plain, False, "lrclib")

        return None

    def _get(self, title: str, artist: str, album: str, duration: int) -> FoundLyrics | NotFound | None:
        params: dict[str, Any] = {"track_name": title, "artist_name": artist}

        if album:
            params["album_name"] = album
        if duration:
            params["duration"] = duration

        return self._from_item(self._request("get", params))

    def _search(self, title: str, artist: str, duration: int) -> FoundLyrics | NotFound | None:
        items = self._request("search", {"track_name": title, "artist_name": artist})

        if not isinstance(items, list):
            return None

        candidates = []

        for item in items:
            if not isinstance(item, dict):
                continue

            item_duration = item.get("duration")
            diff = 0.0

            if duration:
                if not isinstance(item_duration, (int, float)):
                    continue

                diff = abs(item_duration - duration)
                if diff > DURATION_TOLERANCE:
                    continue

            result = self._from_item(item)
            if result is None:
                continue

            # the synced ones first, then the closest in duration
            candidates.append((not (isinstance(result, FoundLyrics) and result.synced), diff, result))

        if not candidates:
            return None

        candidates.sort(key=lambda c: (c[0], c[1]))
        return candidates[0][2]

    def lookup(self, query: LyricsQuery) -> FoundLyrics | NotFound:
        if not query.title.strip() or not query.artist.strip():
            return NotFound("not_found")

        title = clean_title(query.title)
        artist = first_artist(query.artist)
        error: ProviderError | None = None

        def attempt(step):
            # a step that could not be answered (the server is busy) does not end the others
            nonlocal error

            try:
                return step()
            except ProviderError as e:
                error = e
                return None

        # 1. the data as the track has them
        result = attempt(lambda: self._get(query.title, query.artist, query.album, query.duration))

        # 2. the clean title and the first artist (no album)
        if result is None and (title, artist) != (query.title, query.artist):
            result = attempt(lambda: self._get(title, artist, "", query.duration))

        # 3. a search, taking only the lyrics that are in time with the audio
        if result is None:
            result = attempt(lambda: self._search(title, artist, query.duration))

        if result is not None:
            return result

        # nothing found, and a step could not be asked: that is not a final "no"
        if error is not None:
            raise error

        return NotFound("not_found")


class MusixmatchProvider:
    """The Musixmatch of the lyrics plugin, as a provider (only synced lyrics)."""

    name = "musixmatch"

    def __init__(self, provider: Any = None):
        if provider is None:
            from musix.plugins.lyrics import LyricsProvider

            provider = LyricsProvider()

        self.provider = provider

    def lookup(self, query: LyricsQuery) -> FoundLyrics | NotFound:
        if not query.title.strip() or not query.artist.strip():
            return NotFound("not_found")

        self.provider.network_error = False
        title = clean_title(query.title)
        artist = first_artist(query.artist)

        try:
            candidates = self.provider.get_lrc(title, artist)
        except Exception as e:
            raise ProviderError(str(e))

        if self.provider.network_error:
            raise ProviderError("Musixmatch could not be reached")

        if not candidates:
            return NotFound("not_found")

        chosen = candidates[0]
        for candidate in candidates:
            if create_hash(candidate["title"]) == create_hash(query.title) and create_hash(
                candidate["album"]
            ) == create_hash(query.album):
                chosen = candidate

        try:
            lrc = self.provider.get_lrc_by_id(chosen["track_id"])
        except Exception as e:
            raise ProviderError(str(e))

        if self.provider.network_error:
            raise ProviderError("Musixmatch could not be reached")

        if not _text(lrc):
            return NotFound("not_found")

        return FoundLyrics(lrc, True, "musixmatch")


def default_providers() -> list[Provider]:
    return [LrclibProvider(), MusixmatchProvider()]


def find_lyrics(query: LyricsQuery, providers: list[Provider] | None = None) -> FoundLyrics | NotFound:
    """
    Goes through the providers in order and gives the first lyrics found. Without lyrics, it says why:
    "instrumental" (a provider knows the song has no lyrics), "network" (every provider failed to answer)
    or "not_found" (they answered and have nothing; not remembered if one of them could not be reached).
    """
    if providers is None:
        providers = default_providers()

    failed = 0
    rate_limited = False

    for provider in providers:
        try:
            result = provider.lookup(query)
        except ProviderError as error:
            failed += 1
            rate_limited = rate_limited or error.rate_limited
            continue
        except Exception:
            failed += 1
            continue

        if isinstance(result, FoundLyrics):
            return result

        if result.reason == "instrumental":
            return result

    if providers and failed == len(providers):
        return NotFound("network", cacheable=False, rate_limited=rate_limited)

    # one of them could not be asked: it is not a final "no"
    return NotFound("not_found", cacheable=failed == 0)


# # # # # # # # # # # # # # # # # # # #
#       The "not found" memory        #
# # # # # # # # # # # # # # # # # # # #

_misses_lock = threading.Lock()
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def _misses_path() -> Path:
    return Paths().lyrics_plugins_path / "misses.json"


def _read_misses() -> dict[str, dict[str, str]]:
    try:
        data = json.loads(_misses_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

    return data if isinstance(data, dict) else {}


def _write_misses(misses: dict[str, dict[str, str]]) -> None:
    path = _misses_path()
    tmp = path.with_name(path.name + ".tmp")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(misses), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        # remembering is an optimization: never a reason to fail
        tmp.unlink(missing_ok=True)


def _fresh_reason(entry: Any, now: datetime) -> str | None:
    """The reason of an entry of the memory, if it has not expired."""
    if not isinstance(entry, dict):
        return None

    reason = entry.get("reason")
    days = {"not_found": MISS_DAYS, "instrumental": INSTRUMENTAL_DAYS}.get(reason)

    try:
        date = datetime.strptime(str(entry.get("date")), _DATE_FORMAT)
    except ValueError:
        return None

    if days is None or now - date >= timedelta(days=days):
        return None

    return reason


def get_miss(trackhash: str, now: datetime | None = None) -> str | None:
    """The reason the track had no lyrics, if that answer is still fresh; else None."""
    now = now or datetime.now()

    with _misses_lock:
        entry = _read_misses().get(trackhash)

    return _fresh_reason(entry, now)


def record_miss(trackhash: str, reason: str, now: datetime | None = None) -> None:
    if reason not in ("not_found", "instrumental"):
        return

    now = now or datetime.now()

    with _misses_lock:
        misses = _read_misses()
        misses[trackhash] = {"reason": reason, "date": now.strftime(_DATE_FORMAT)}
        _write_misses(misses)


def clear_miss(trackhash: str) -> None:
    with _misses_lock:
        misses = _read_misses()

        if misses.pop(trackhash, None) is not None:
            _write_misses(misses)


def recent_misses(now: datetime | None = None) -> set[str]:
    """The trackhashes whose "no lyrics" answer is still fresh."""
    now = now or datetime.now()

    with _misses_lock:
        misses = _read_misses()

    return {h for h, entry in misses.items() if _fresh_reason(entry, now) is not None}


# # # # # # # # # # # # # # # # # # # #
#        Saving the .lrc file         #
# # # # # # # # # # # # # # # # # # # #


def lrc_path(filepath: str) -> Path:
    return Path(filepath).with_suffix(".lrc")


def read_lrc_text(filepath: str) -> str:
    """The text of the .lrc next to the audio ("" when there is none or it is empty)."""
    try:
        return lrc_path(filepath).read_text(encoding="utf-8-sig", errors="replace").strip()
    except OSError:
        return ""


def has_time_tags(text: str) -> bool:
    return re.search(r"^\s*\[\d+:\d+(?:\.\d+)?\]", text, re.M) is not None


def save_lyrics(filepath: str, lyrics: FoundLyrics, replace_unsynced: bool = False) -> str | None:
    """
    Saves the lyrics as the .lrc of the audio file. Gives None when saved, or why not:
    "exists" (a .lrc with text is there and was kept) or "write_failed".

    An empty .lrc counts as none. A .lrc with text is never replaced, except a plain one by a
    synced one when `replace_unsynced` is on (the lyrics that are being improved).
    """
    if not filepath or not is_path_within_root_dirs(filepath):
        return "write_failed"

    target = lrc_path(filepath)
    existing = read_lrc_text(filepath)

    if existing and not (replace_unsynced and lyrics.synced and not has_time_tags(existing)):
        return "exists"

    text = lyrics.text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"

    tmp = target.with_name(f".{target.name}.tmp")

    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as file:
            file.write(text)

        os.replace(tmp, target)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass

        return "write_failed"

    return None


# # # # # # # # # # # # # # # # # # # #
#    Find and save (used by the API    #
#    and by the batch job)             #
# # # # # # # # # # # # # # # # # # # #


@dataclass
class SearchResult:
    trackhash: str
    text: str | None = None  # the lyrics, when found (whatever the kind)
    synced: bool = False
    source: str | None = None
    reason: str | None = None  # not_found | instrumental | network | write_failed
    rate_limited: bool = False
    detail: str | None = None  # the path that could not be written


def lyrics_plugin_on() -> bool:
    plugin = PluginTable.get_by_name("lyrics_finder")
    return bool(plugin and int(plugin.active))


def find_and_save(
    query: LyricsQuery,
    *,
    use_cache: bool = True,
    replace_unsynced: bool = False,
    providers: list[Provider] | None = None,
) -> SearchResult:
    """
    Looks the lyrics up online and saves them. `use_cache` makes it skip a song that was looked up
    recently without success (the buttons that the user presses by hand do not use it).
    """
    result = SearchResult(query.trackhash)

    if use_cache:
        miss = get_miss(query.trackhash)

        if miss is not None:
            result.reason = miss
            return result

    if not query.filepath or not is_path_within_root_dirs(query.filepath):
        result.reason = "write_failed"
        result.detail = query.filepath
        return result

    found = find_lyrics(query, providers)

    if isinstance(found, NotFound):
        result.reason = found.reason
        result.rate_limited = found.rate_limited

        if found.cacheable:
            record_miss(query.trackhash, found.reason)

        return result

    failure = save_lyrics(query.filepath, found, replace_unsynced)

    if failure == "write_failed":
        result.reason = "write_failed"
        result.detail = lrc_path(query.filepath).as_posix()
        return result

    clear_miss(query.trackhash)
    result.text = found.text
    result.synced = found.synced
    result.source = found.source

    if failure == "exists":
        # a lyric that must not be replaced is there already: nothing was written
        result.text = read_lrc_text(query.filepath)
        result.synced = has_time_tags(result.text)
        result.source = None

    return result
