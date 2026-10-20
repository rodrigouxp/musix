"""
Renaming an album in all its files: the album tag of every track of the album becomes the
new title, and the hashes (album, tracks) follow.

Two steps, both here (the same as in ``artistrename.py``, which this follows):

- ``build_preview`` reads the tags and says what would change. It writes nothing.
- ``start_rename`` does it, in the background, file by file, through the safe
  writer of ``tagwriter.py`` (a failed file does not stop the others).

The rules: only the album tag (``ALBUM``) is written, in the files of this album and no
other (two albums with the same title and different artists are different albums); a
file that has no album tag is not changed (the tag is never created); no file or folder is
renamed (the name of a file does not have the album).

What is written is the text of the tag, the ``og_title`` of the album: the app shows a
cleaner title ("Deluxe" and the like are taken out), but the tag keeps it all.
"""

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from musix.lib.renamecommon import BaseJobState, run_in_background, update_hashes
from musix.lib.taglib import get_tags
from musix.lib.tagwriter import (
    SUPPORTED_EXTENSIONS,
    TagChanges,
    TagSnapshot,
    TagWriteError,
    read_tags,
    write_tags,
)
from musix.lib.trackrename import RenameError, append_journal
from musix.models.track import Track
from musix.store.albums import AlbumStore
from musix.store.tracks import TrackStore
from musix.utils.hashing import create_hash

log = logging.getLogger(__name__)

MAX_TITLE_LENGTH = 200
# the lists in the preview are cut here (the counts are always complete)
LIST_LIMIT = 200
SAMPLE_COUNT = 20

LINE_BREAKS = re.compile(r"[\r\n\x0b\x0c\x85\u2028\u2029]")


# SECTION: the new title


def validate_new_title(title: str) -> str:
    """
    Checks the new title and returns it as it will be written (without spaces around it).
    Raises ``RenameError`` (400) when it can not be used. A comma is fine in a title.
    """
    title = (title or "").strip()

    if not title:
        raise RenameError(400, "The title can not be empty")

    if len(title) > MAX_TITLE_LENGTH:
        raise RenameError(400, f"The title can have at most {MAX_TITLE_LENGTH} characters")

    if LINE_BREAKS.search(title):
        raise RenameError(400, "The title can not have line breaks")

    return title


# SECTION: the plan of one file


@dataclass
class AlbumFilePlan:
    """
    What would be done to one file.
    """

    track: Track
    path: Path
    before: TagSnapshot | None = None
    changes: TagChanges = field(default_factory=TagChanges)
    # the file is never renamed (these two exist because the shared code reads them)
    new_path: Path | None = None
    # the album hash the file gets with the new title
    new_albumhash: str | None = None
    # the file already has the new title
    unchanged: bool = False
    # problems
    error: str | None = None
    unsupported: bool = False
    not_writable: bool = False
    no_album_tag: bool = False


def _predict_albumhash(plan: AlbumFilePlan, new_title: str, config: Any) -> str | None:
    """
    The album hash the file will have, worked out the way the scanner does it
    (``get_tags`` and then the ``Track``) with the new title. Reads the file; writes nothing.
    """
    try:
        meta = get_tags(plan.path.as_posix(), config=config)
        meta["album"] = new_title
        meta["albumhash"] = create_hash(new_title, meta.get("albumartists", ""))
        meta["trackhash"] = create_hash(
            meta.get("artists", ""), new_title, meta.get("title", "")
        )
        track = Track(id=0, lastplayed=0, playcount=0, playduration=0, **meta, config=config)
        return track.albumhash
    except Exception as error:
        log.warning(f"Could not work out the new album hash of {plan.path}: {error}")
        return None


def plan_file(track: Track, new_title: str, config: Any) -> AlbumFilePlan:
    """
    Reads the tags of a file and works out what to write. Writes nothing.
    """
    plan = AlbumFilePlan(track=track, path=Path(track.filepath))
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

    if before.album is None:
        # a file without the tag is not changed: it is not really of this album
        plan.no_album_tag = True
        plan.error = "this file has no album tag, so it was not changed"
        return plan

    if before.album == new_title:
        plan.unchanged = True
        plan.new_albumhash = track.albumhash
        return plan

    plan.changes = TagChanges(album=new_title)
    plan.new_albumhash = _predict_albumhash(plan, new_title, config)
    return plan


def album_tracks(albumhash: str) -> list[Track]:
    """
    Every file of the album, by its hash (not by its title).
    """
    return [t for t in TrackStore.get_flat_list() if t.albumhash == albumhash]


def plan_all(albumhash: str, new_title: str, config: Any) -> list[AlbumFilePlan]:
    return [plan_file(t, new_title, config) for t in album_tracks(albumhash)]


# SECTION: preview


def _sample(plan: AlbumFilePlan, new_title: str) -> dict[str, Any]:
    return {
        "filepath": plan.track.filepath,
        "title": plan.track.title.strip(),
        "album_before": plan.before.album if plan.before else None,
        "album_after": new_title if plan.changes.album is not None else (plan.before.album if plan.before else None),
    }


def build_preview(old_hash: str, new_title: str, config: Any) -> dict[str, Any]:
    """
    What a rename would do. Reads tags; writes nothing.

    Raises ``RenameError(400)`` when every file already has the new title.
    """
    entry = AlbumStore.albummap.get(old_hash)

    if entry is None:
        raise RenameError(404, "Album not found")

    plans = plan_all(old_hash, new_title, config)
    to_rewrite = [p for p in plans if p.changes != TagChanges()]

    if not to_rewrite and not any(p.error for p in plans):
        raise RenameError(400, "The new title is the same as the current one")

    def cut(items: list):
        return items[:LIST_LIMIT]

    unsupported = [p for p in plans if p.unsupported]
    not_writable = [p for p in plans if p.not_writable]
    no_album_tag = [p for p in plans if p.no_album_tag]
    other_errors = [
        p for p in plans if p.error and not (p.unsupported or p.not_writable or p.no_album_tag)
    ]

    # the album tag as it is in the files now (it differs between files when the app
    # merges albums: "Abbey Road" and "Abbey Road (Remastered)" can be one album)
    distinct: list[str] = []

    for plan in plans:
        value = plan.before.album if plan.before else None

        if value is not None and value not in distinct:
            distinct.append(value)

    predicted = {p.new_albumhash for p in plans if p.new_albumhash}
    new_hash = next(iter(predicted)) if len(predicted) == 1 else None
    hash_changes = new_hash is not None and new_hash != old_hash

    # another album with this title and these artists: the two become one
    existing = AlbumStore.albummap.get(new_hash) if hash_changes else None

    return {
        "album": {
            "albumhash": old_hash,
            "title": entry.album.og_title,
            "albumartists": [a["name"] for a in entry.album.albumartists],
        },
        "current_title": entry.album.og_title,
        "new_title": new_title,
        "new_albumhash": new_hash,
        "hash_changes": hash_changes,
        "tracks_count": len({p.track.trackhash for p in plans}),
        "files_total": len(plans),
        "files_to_rewrite": len(to_rewrite),
        "distinct_titles": cut(distinct),
        "distinct_titles_count": len(distinct),
        "no_album_tag": cut([p.track.filepath for p in no_album_tag]),
        "no_album_tag_count": len(no_album_tag),
        "unsupported_formats": cut(
            [{"filepath": p.track.filepath, "error": p.error} for p in unsupported]
        ),
        "unsupported_count": len(unsupported),
        "not_writable": cut([p.track.filepath for p in not_writable]),
        "not_writable_count": len(not_writable),
        "other_errors": cut([{"filepath": p.track.filepath, "error": p.error} for p in other_errors]),
        "merge": (
            {
                "title": existing.album.og_title,
                "albumhash": new_hash,
                "trackcount": len(existing.trackhashes),
            }
            if existing
            else None
        ),
        "samples": [_sample(p, new_title) for p in to_rewrite[:SAMPLE_COUNT]],
        "warning": f"The album tag of {len(to_rewrite)} files will be rewritten.",
    }


# SECTION: the job


class AlbumJobState(BaseJobState):
    """
    The state of the album rename job. Read by ``GET /album/rename/status``. The lock and the
    rule "one rename at a time" are shared with the artist rename (see ``renamecommon``).
    """

    kind = "album"
    old_hash = ""
    old_title = ""
    new_title = ""


def job_status() -> dict[str, Any]:
    return {
        "running": AlbumJobState.running,
        "albumhash": AlbumJobState.old_hash,
        "old_title": AlbumJobState.old_title,
        "new_title": AlbumJobState.new_title,
        "done": AlbumJobState.done,
        "total": AlbumJobState.total,
        "current": AlbumJobState.current,
        "errors": dict(AlbumJobState.errors),
        "finished": bool(AlbumJobState.result) and not AlbumJobState.running,
        # the same hash when it did not change (only the letter case)
        "new_albumhash": (AlbumJobState.result or {}).get("new_albumhash"),
        "result": AlbumJobState.result,
    }


def _has_something_to_do(old_hash: str, new_title: str) -> bool:
    """
    False only when every file of the album is readable and already has the new title.
    """
    for track in album_tracks(old_hash):
        try:
            if read_tags(track.filepath).album != new_title:
                return True
        except Exception:
            return True  # the job reports the file

    return False


def start_rename(old_hash: str, new_title: str, config: Any, wait: bool = False) -> None:
    """
    Starts the rename in a background thread. Raises ``RenameError(409)`` if a rename
    (of an album or of an artist) is running.
    """
    entry = AlbumStore.albummap.get(old_hash)

    if entry is None:
        raise RenameError(404, "Album not found")

    if not _has_something_to_do(old_hash, new_title):
        raise RenameError(400, "The new title is the same as the current one")

    AlbumJobState.begin()
    AlbumJobState.old_hash = old_hash
    AlbumJobState.old_title = entry.album.og_title
    AlbumJobState.new_title = new_title

    run_in_background(
        AlbumJobState, lambda: _do_rename(old_hash, new_title, config), "album-rename", wait
    )


def _do_rename(old_hash: str, new_title: str, config: Any) -> dict[str, Any]:
    plans = plan_all(old_hash, new_title, config)
    AlbumJobState.total = len(plans)

    ok: list[AlbumFilePlan] = []
    failed: dict[str, str] = {}

    for plan in plans:
        AlbumJobState.current = plan.track.filepath

        try:
            if plan.error:
                raise TagWriteError(plan.error)

            if plan.changes != TagChanges():
                write_tags(plan.path, plan.changes, config=config)
                _journal(plan, old_hash, new_title)

            ok.append(plan)
        except (TagWriteError, OSError) as error:
            failed[plan.track.filepath] = str(error)
            AlbumJobState.errors[plan.track.filepath] = str(error)
        except Exception as error:  # a file must never stop the others
            failed[plan.track.filepath] = f"unexpected error: {error}"
            AlbumJobState.errors[plan.track.filepath] = failed[plan.track.filepath]
            log.exception(f"album rename: {plan.track.filepath}")

        AlbumJobState.done += 1

    moved: dict[str, Any] = {}
    new_hash: str | None = None

    if ok:
        update = update_hashes(ok)
        moved = update.moved
        hashes = update.album_map.get(old_hash, [])
        new_hash = hashes[0] if len(hashes) == 1 else None

    return {
        "new_albumhash": new_hash,
        "old_albumhash": old_hash,
        "old_title": AlbumJobState.old_title,
        "new_title": new_title,
        "files_ok": len(ok),
        "files_failed": failed,
        # the hash is moved only when every file of the album was written
        "album_moved": bool(moved.get("albums")),
        "hash_changed": new_hash is not None and new_hash != old_hash,
        "moved": moved,
        "seconds": round(time.time() - AlbumJobState.started, 1),
    }


def _journal(plan: AlbumFilePlan, old_hash: str, new_title: str):
    append_journal(
        {
            "action": "rename-album",
            "filepath": plan.path.as_posix(),
            "albumhash_old": old_hash,
            "album_old": plan.before.album if plan.before else None,
            "album_new": new_title,
        }
    )
