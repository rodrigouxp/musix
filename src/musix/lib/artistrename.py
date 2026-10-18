"""
Renaming an artist in all the files: "X" becomes "Y" in the tags of every track that
has X, and the hashes (artist, albums, tracks) follow.

Two steps, both here:

- ``build_preview`` reads the tags and says what would change. It writes nothing.
- ``start_rename`` does it, in the background, file by file, through the safe
  writer of ``tagwriter.py`` (a failed file does not stop the others).

The tag rules (see ``tagwriter.replace_artist_element``): an artist tag is changed
element by element, never by text; the other artists, their order and the separators
stay; a tag the file did not have is never created; ``ALBUMARTIST`` changes only in
the files whose ``ALBUMARTIST`` has X.
"""

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from musix import settings
from musix.config import UserConfig
from musix.lib.index import reload_stores
from musix.lib.rekey import log_rekey, refresh_track_extras, rekey_hash
from musix.lib.tagwriter import (
    ARTIST_FIELDS,
    SUPPORTED_EXTENSIONS,
    TagChanges,
    TagWriteError,
    read_tags,
    replace_artist_element,
    split_elements,
    write_tags,
)
from musix.lib.trackrename import (
    RenameError,
    _same_file,
    append_journal,
    ensure_album_thumbnails,
    reindex_files,
    safe_rename,
    sanitize_filename,
)
from musix.models.track import Track
from musix.store.artists import ArtistStore
from musix.store.tracks import TrackStore
from musix.utils.hashing import create_hash
from musix.utils.parsers import split_artists

log = logging.getLogger(__name__)

MAX_NAME_LENGTH = 200
# the lists in the preview are cut here (the counts are always complete)
LIST_LIMIT = 200
SAMPLE_COUNT = 20

FEAT_PATTERNS = (
    r"\((?:feat|ft|featuring|with)\.?\s+(.+?)\)",
    r"\[(?:feat|ft|featuring|with)\.?\s+(.+?)\]",
)


def artist_hash(name: str) -> str:
    return create_hash(name, decode=True)


# SECTION: the new name


def validate_new_name(name: str, config: Any) -> str:
    """
    Checks the new name and returns it as it will be written (without spaces
    around it). Raises ``RenameError`` (400) when it can not be used.
    """
    name = (name or "").strip()

    if not name:
        raise RenameError(400, "The name can not be empty")

    if len(name) > MAX_NAME_LENGTH:
        raise RenameError(400, f"The name can have at most {MAX_NAME_LENGTH} characters")

    # the app would read it as more than one artist
    if split_artists(name, config) != [name]:
        separators = " ".join(sorted(s for s in config.artistSeparators if s))
        raise RenameError(
            400,
            "This name would be read as more than one artist (the separators are "
            f"{separators} and the comma). Names like AC/DC need to be in the list of exceptions.",
        )

    return name


# SECTION: the plan of one file


FEAT_RE = [re.compile(p, re.IGNORECASE) for p in FEAT_PATTERNS]


def swap_feat_in_title(title: str, old_hash: str, new_name: str, config: Any) -> str | None:
    """
    Swaps the artist inside the "(feat. ...)" or "[ft. ...]" part of a title.
    Returns the new title, or ``None`` when the part is not there or does not have the artist.
    """
    match = FEAT_RE[0].search(title) or FEAT_RE[1].search(title)

    if not match:
        return None

    group = match.group(1)
    swapped = replace_artist_element([group], old_hash, new_name, config)

    if not swapped or swapped[0] == group:
        return None

    return title[: match.start(1)] + swapped[0] + title[match.end(1) :]


def _has(values: list[str] | None, old_hash: str, config: Any) -> bool:
    return values is not None and any(
        artist_hash(n) == old_hash for n in split_elements(values, config)
    )


@dataclass
class FilePlan:
    """
    What would be done to one file.
    """

    track: Track
    path: Path
    before: Any = None
    changes: TagChanges = field(default_factory=TagChanges)
    new_path: Path | None = None
    new_title: str | None = None
    # what the file has now
    in_artist: bool = False
    in_albumartist: bool = False
    in_artists: bool = False
    in_title: bool = False
    # problems
    error: str | None = None
    unsupported: bool = False
    not_writable: bool = False
    name_conflict: str | None = None
    # the new name was already in the same tag (the two become one)
    collapses: list[str] = field(default_factory=list)
    no_albumartist_tag: bool = False

    @property
    def participant_only(self) -> bool:
        """X is on the track but the album is not X's."""
        return self.in_artist and not self.in_albumartist and not _owner_is(self.track, self._x)

    _x: str = ""

    @property
    def renames_file(self) -> bool:
        return self.new_path is not None and self.new_path.name != self.path.name


def _owner_is(track: Track, old_hash: str) -> bool:
    return any(a["artisthash"] == old_hash for a in track.albumartists)


def plan_file(track: Track, old_hash: str, new_name: str, config: Any) -> FilePlan:
    """
    Reads the tags of a file and works out what to write. Writes nothing.
    """
    new_hash = artist_hash(new_name)
    plan = FilePlan(track=track, path=Path(track.filepath), _x=old_hash)
    suffix = plan.path.suffix

    if suffix.lower() not in SUPPORTED_EXTENSIONS:
        plan.unsupported = True
        plan.error = f"unsupported format: {suffix or plan.path.name}"
        return plan

    if not plan.path.is_file():
        plan.error = "the file is not there any more"
        return plan

    if not os.access(plan.path, os.W_OK):
        plan.not_writable = True
        plan.error = "no permission to write this file"
        return plan

    try:
        before = read_tags(plan.path)
    except TagWriteError as error:
        plan.error = str(error)
        plan.unsupported = "unsupported format" in str(error)
        return plan

    plan.before = before
    changes = TagChanges()

    for name in ARTIST_FIELDS:
        values = getattr(before, name)

        if not _has(values, old_hash, config):
            continue

        setattr(plan, "in_" + name, True)
        setattr(changes, name, replace_artist_element(values, old_hash, new_name, config))

        # the new name was already in the tag, so the two became one
        if new_hash != old_hash and _has(values, new_hash, config):
            plan.collapses.append(name)

    plan.no_albumartist_tag = plan.in_artist and before.albumartist is None

    if config.extractFeaturedArtists and before.title:
        new_title = swap_feat_in_title(before.title, old_hash, new_name, config)

        if new_title is not None:
            plan.in_title = True
            plan.new_title = new_title
            changes.title = new_title
            plan.new_path = plan.path.with_name(sanitize_filename(new_title, suffix))

    plan.changes = changes
    return plan


def candidate_tracks(old_hash: str) -> list[Track]:
    """
    Every file that has the artist: as artist, as album artist or in the title.
    """
    return [
        t
        for t in TrackStore.get_flat_list()
        if old_hash in t.artisthashes or _owner_is(t, old_hash)
    ]


def plan_all(old_hash: str, new_name: str, config: Any) -> list[FilePlan]:
    plans = [plan_file(t, old_hash, new_name, config) for t in candidate_tracks(old_hash)]

    # the files that will be renamed must not take a name that is taken, or that
    # another file of the same job takes
    taken: dict[str, FilePlan] = {}

    for plan in plans:
        if not plan.renames_file or plan.error:
            continue

        key = str(plan.new_path).lower()

        if (plan.new_path.exists() and not _same_file(plan.path, plan.new_path)) or key in taken:
            plan.name_conflict = plan.new_path.name
            continue

        taken[key] = plan

    return plans


# SECTION: preview


def _joined(values: list[str] | None) -> str | None:
    return None if values is None else "; ".join(values)


def _after(plan: FilePlan, name: str) -> str | None:
    value = getattr(plan.changes, name)
    return _joined(value if value is not None else getattr(plan.before, name))


def _sample(plan: FilePlan) -> dict[str, Any]:
    return {
        "filepath": plan.track.filepath,
        "title": plan.track.title.strip(),
        "album": plan.track.album,
        "artist_before": _joined(plan.before.artist) if plan.before else None,
        "artist_after": _after(plan, "artist") if plan.before else None,
        "albumartist_before": _joined(plan.before.albumartist) if plan.before else None,
        "albumartist_after": _after(plan, "albumartist") if plan.before else None,
        "participant": plan.participant_only,
    }


def build_preview(old_hash: str, new_name: str, config: Any) -> dict[str, Any]:
    """
    What a rename would do. Reads tags; writes nothing.
    """
    entry = ArtistStore.artistmap.get(old_hash)
    plans = plan_all(old_hash, new_name, config)
    new_hash = artist_hash(new_name)
    writable = [p for p in plans if not p.error and not p.name_conflict]

    def cut(items: list):
        return items[:LIST_LIMIT]

    in_artist = [p for p in writable if p.in_artist]
    participants = [p for p in in_artist if p.participant_only]
    title_only = [p for p in writable if p.in_title and not p.in_artist]
    unsupported = [p for p in plans if p.unsupported]
    not_writable = [p for p in plans if p.not_writable]
    conflicts = [p for p in plans if p.name_conflict]
    other_errors = [p for p in plans if p.error and not (p.unsupported or p.not_writable)]
    collapsing = [p for p in writable if p.collapses]
    no_albumartist = [p for p in in_artist if p.no_albumartist_tag]
    to_rename = [p for p in writable if p.renames_file]
    to_rewrite = [p for p in writable if p.changes != TagChanges()]

    existing = ArtistStore.artistmap.get(new_hash) if new_hash != old_hash else None

    # the first tracks, and always the ones where the artist only takes part
    samples = [p for p in in_artist if not p.participant_only][:SAMPLE_COUNT]
    sample_set = {id(p) for p in samples}
    samples += [p for p in participants if id(p) not in sample_set][:LIST_LIMIT]

    return {
        "artist": {"artisthash": old_hash, "name": entry.artist.name if entry else None},
        "new_name": new_name,
        "new_artisthash": new_hash,
        "tracks_in_artist_tag": len(in_artist),
        "albums_in_artist_tag": len({p.track.albumhash for p in in_artist}),
        "tracks_as_participant": len(participants),
        "tracks_title_only": len(title_only),
        "files_to_rename": len(to_rename),
        "files_to_rewrite": len(to_rewrite),
        "files_total": len(plans),
        "unsupported_formats": cut(
            [{"filepath": p.track.filepath, "error": p.error} for p in unsupported]
        ),
        "unsupported_count": len(unsupported),
        "name_conflicts": cut(
            [{"filepath": p.track.filepath, "name": p.name_conflict} for p in conflicts]
        ),
        "name_conflicts_count": len(conflicts),
        "not_writable": cut([p.track.filepath for p in not_writable]),
        "not_writable_count": len(not_writable),
        "other_errors": cut([{"filepath": p.track.filepath, "error": p.error} for p in other_errors]),
        "merge": (
            {
                "name": existing.artist.name,
                "artisthash": new_hash,
                "trackcount": len(existing.trackhashes),
            }
            if existing
            else None
        ),
        "samples": [_sample(p) for p in samples],
        "participant_count": len(participants),
        "same_tag_collapses": cut(
            [
                {**_sample(p), "tags": p.collapses}
                for p in collapsing
            ]
        ),
        "same_tag_collapses_count": len(collapsing),
        "no_albumartist": cut([_sample(p) for p in no_albumartist]),
        "no_albumartist_count": len(no_albumartist),
        "warning": (
            f"The tags of {len(to_rewrite)} files will be rewritten"
            + (f" and {len(to_rename)} files will be renamed" if to_rename else "")
            + "."
        ),
    }


# SECTION: the job


class JobState:
    """
    The state of the (only) rename job. Read by ``GET /artist/rename/status``.
    """

    lock = threading.Lock()
    running = False
    old_hash = ""
    old_name = ""
    new_name = ""
    done = 0
    total = 0
    current: str | None = None
    errors: dict[str, str] = {}
    result: dict[str, Any] | None = None
    started = 0.0
    finished = 0.0


def job_status() -> dict[str, Any]:
    return {
        "running": JobState.running,
        "artisthash": JobState.old_hash,
        "old_name": JobState.old_name,
        "new_name": JobState.new_name,
        "done": JobState.done,
        "total": JobState.total,
        "current": JobState.current,
        "errors": dict(JobState.errors),
        "finished": bool(JobState.result) and not JobState.running,
        "new_artisthash": (JobState.result or {}).get("new_artisthash"),
        "result": JobState.result,
    }


def start_rename(old_hash: str, new_name: str, config: Any, wait: bool = False) -> None:
    """
    Starts the rename in a background thread. Raises ``RenameError(409)`` if one is running.
    """
    entry = ArtistStore.artistmap.get(old_hash)

    if entry is None:
        raise RenameError(404, "Artist not found")

    with JobState.lock:
        if JobState.running:
            raise RenameError(409, "Another artist rename is already running")

        JobState.running = True
        JobState.old_hash = old_hash
        JobState.old_name = entry.artist.name
        JobState.new_name = new_name
        JobState.done = 0
        JobState.total = 0
        JobState.current = None
        JobState.errors = {}
        JobState.result = None
        JobState.started = time.time()

    thread = threading.Thread(
        target=_run, args=(old_hash, new_name, config), name="artist-rename", daemon=True
    )
    thread.start()

    if wait:
        thread.join()


def _apply(plan: FilePlan, old_hash: str, new_name: str, config: Any):
    """
    Writes one file: renames it if the title changed, then writes the tags.
    Raises ``TagWriteError`` or ``OSError`` with the file as it was.
    """
    renamed = False

    if plan.renames_file:
        safe_rename(plan.path, plan.new_path)
        renamed = True

    target = plan.new_path if renamed else plan.path

    try:
        if plan.changes != TagChanges():
            write_tags(target, plan.changes, swap=(old_hash, new_name), config=config)
    except Exception:
        if renamed:
            try:
                safe_rename(target, plan.path)
            except OSError as undo_error:
                log.error(f"Could not undo the rename of {plan.path}: {undo_error}")

        raise


def _run(old_hash: str, new_name: str, config: Any):
    try:
        result = _do_rename(old_hash, new_name, config)
    except Exception as error:
        log.exception("artist rename failed")
        result = {"error": f"{type(error).__name__}: {error}", "new_artisthash": None}
    finally:
        JobState.current = None

    JobState.result = result
    JobState.finished = time.time()
    JobState.running = False


def _do_rename(old_hash: str, new_name: str, config: Any) -> dict[str, Any]:
    new_hash = artist_hash(new_name)
    old_name = JobState.old_name
    plans = plan_all(old_hash, new_name, config)
    JobState.total = len(plans)

    ok: list[FilePlan] = []
    failed: dict[str, str] = {}

    for plan in plans:
        JobState.current = plan.track.filepath

        try:
            if plan.error:
                raise TagWriteError(plan.error)

            if plan.name_conflict:
                raise TagWriteError(f"a file named {plan.name_conflict} already exists in this folder")

            _apply(plan, old_hash, new_name, config)
            ok.append(plan)
            _journal(plan, old_hash, new_hash, old_name, new_name)
        except (TagWriteError, OSError) as error:
            failed[plan.track.filepath] = str(error)
            JobState.errors[plan.track.filepath] = str(error)
        except Exception as error:  # a file must never stop the others
            failed[plan.track.filepath] = f"unexpected error: {error}"
            JobState.errors[plan.track.filepath] = failed[plan.track.filepath]
            log.exception(f"artist rename: {plan.track.filepath}")

        JobState.done += 1

    moved: dict[str, Any] = {}

    if ok:
        moved = _update_hashes(ok, failed, old_hash, new_hash, config)

    return {
        "new_artisthash": new_hash if ok else None,
        "old_artisthash": old_hash,
        "old_name": old_name,
        "new_name": new_name,
        "files_ok": len(ok),
        "files_failed": failed,
        "artist_moved": bool(moved.get("artist_moved")),
        "moved": moved,
        "seconds": round(time.time() - JobState.started, 1),
    }


def _journal(plan: FilePlan, old_hash: str, new_hash: str, old_name: str, new_name: str):
    before = plan.before
    append_journal(
        {
            "action": "rename-artist",
            "artist_old": old_name,
            "artist_new": new_name,
            "filepath_old": plan.path.as_posix(),
            "filepath_new": (plan.new_path or plan.path).as_posix(),
            "title_old": before.title,
            "title_new": plan.new_title or before.title,
            "artist_tag_old": before.artist,
            "artist_tag_new": plan.changes.artist if plan.changes.artist is not None else before.artist,
            "albumartist_tag_old": before.albumartist,
            "albumartist_tag_new": (
                plan.changes.albumartist if plan.changes.albumartist is not None else before.albumartist
            ),
            "artists_tag_old": before.artists,
            "artists_tag_new": plan.changes.artists if plan.changes.artists is not None else before.artists,
        }
    )


def _update_hashes(
    ok: list[FilePlan], failed: dict[str, str], old_hash: str, new_hash: str, config: Any
) -> dict[str, Any]:
    """
    Reads the written files again, moves the data from the old hashes to the new
    ones and loads the stores again.
    """
    old_to_new = {
        p.path.as_posix(): (p.new_path or p.path).as_posix() for p in ok
    }
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

    # a hash is moved only when every file under it was written: otherwise some file
    # still has the old hash and its data has to stay
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

    # the artist moves only when no file is left with the old name
    if not failed and old_hash != new_hash:
        log_rekey("artist", old_hash, new_hash, rekey_hash("artist", old_hash, new_hash))
        moved["artist_moved"] = True

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

    return moved
