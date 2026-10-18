"""
Renaming a track: the title on the screen, the title in the tag and the name of
the file become the same text.

The pieces that Stage 3 (renaming an artist in all files) shares with this are here
too: the file name rules, the journal, the safe rename and the re-reading of changed
files.
"""

import json
import os
import platform
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from musix import settings
from musix.config import UserConfig
from musix.db.libdata import TrackTable
from musix.lib.coverart import refresh_album_art
from musix.lib.index import reload_stores
from musix.lib.rekey import log_rekey, refresh_track_extras, rekey_hash
from musix.lib.tagwriter import (
    SUPPORTED_EXTENSIONS,
    TagChanges,
    TagWriteError,
    append_artists,
    read_tags,
    write_tags,
)
from musix.lib.taglib import get_tags
import logging

log = logging.getLogger(__name__)
from musix.models.track import Track
from musix.serializers.track import serialize_track
from musix.store.tracks import TrackStore
from musix.utils.filesystem import is_hidden_file
from musix.utils.parsers import parse_feat_from_title

MAX_TITLE_LENGTH = 200
MAX_FILENAME_BYTES = 255

# characters Windows does not accept in a file name, and the control characters
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{n}" for n in range(1, 10)),
    *(f"LPT{n}" for n in range(1, 10)),
}


class RenameError(Exception):
    """
    A rename that can not be done. ``status`` is the HTTP status for the answer.
    Nothing was changed when this is raised.
    """

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# SECTION: file names


def _cut_to_bytes(text: str, limit: int) -> str:
    """
    Cuts text to at most ``limit`` bytes in UTF-8, on a character boundary.
    """
    encoded = text.encode("utf-8")

    if len(encoded) <= limit:
        return text

    return encoded[:limit].decode("utf-8", errors="ignore")


def sanitize_filename(title: str, extension: str = "") -> str:
    """
    The name of the file for a title: the title with what Windows does not
    accept turned into "_", plus the extension.

    - ``< > : " / \\ | ?  *`` and control characters become "_";
    - spaces and dots at the end go away;
    - a reserved Windows name (CON, PRN, AUX, NUL, COM1 to COM9, LPT1 to LPT9) gets
      an "_" after it;
    - a name that would start with "." or "$" gets an "_" before it, because the
      scanner skips such files;
    - the whole name is at most 255 bytes.
    """
    name = INVALID_FILENAME_CHARS.sub("_", title).rstrip(" .")

    if not name:
        name = "_"

    if is_hidden_file(name):
        name = "_" + name

    first = name.split(".")[0]

    if first.upper() in RESERVED_NAMES:
        name = first + "_" + name[len(first) :]

    name = _cut_to_bytes(name, MAX_FILENAME_BYTES - len(extension.encode("utf-8")))
    name = name.rstrip(" .") or "_"

    return name + extension


def safe_rename(source: Path, target: Path):
    """
    Renames a file without ever replacing another one.

    ``os.replace`` (and ``os.rename`` on Linux) would silently overwrite a file that
    is already there. On Windows ``os.rename`` refuses; elsewhere the file is
    hard-linked to the new name and the old name is removed, which also
    refuses. Raises ``FileExistsError`` when the target is taken.
    """
    # (not ``source == target``: Windows paths compare without regard to letter case)
    if str(source) == str(target):
        return

    # the same file with a different letter case (Windows, macOS): a plain rename
    if target.exists() and not _same_file(source, target):
        raise FileExistsError(str(target))

    if platform.system() == "Windows" or _same_file(source, target):
        os.rename(source, target)
        return

    try:
        os.link(source, target)
    except FileExistsError:
        raise
    except OSError:
        # no hard links on this file system: check and rename
        if target.exists():
            raise FileExistsError(str(target))

        os.rename(source, target)
        return

    os.unlink(source)


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


# SECTION: journal


def journal_path() -> Path:
    return settings.Paths().config_dir / "rename-journal.jsonl"


def append_journal(entry: dict[str, Any]):
    """
    Adds a line to ``rename-journal.jsonl`` in the config folder. It lets the
    user undo a rename by hand: it is not a backup of the audio.
    """
    line = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}

    try:
        path = journal_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "a", encoding="utf-8") as file:
            file.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError as error:
        log.error(f"Could not write the rename journal: {error}")


# SECTION: re-reading changed files


def reindex_files(old_to_new: dict[str, str]) -> dict[str, Track]:
    """
    Updates the database after files were changed or renamed: the old rows go,
    the new files are read again. The in-memory stores are not touched (see
    ``reload_stores``).

    :param old_to_new: old filepath -> new filepath (the same one when only the tags
        changed)
    :returns: the new ``Track`` of each new filepath, by posix path
    """
    config = UserConfig()
    old_paths = {Path(p).as_posix() for p in old_to_new}
    new_paths = [Path(p).as_posix() for p in old_to_new.values()]

    TrackTable.remove_tracks_by_filepaths(old_paths | set(new_paths))

    for filepath in new_paths:
        TrackTable.insert_one(get_tags(filepath, config=config))

    # (``TrackTable.get_tracks_by_filepaths`` hands rows to a function that wants dicts)
    wanted = set(new_paths)
    return {t.filepath: t for t in TrackTable.get_all() if t.filepath in wanted}


def ensure_album_thumbnails(tracks: list[Track]):
    """
    Makes sure each album of the given tracks has its thumbnails.
    """
    seen: set[str] = set()

    for track in tracks:
        if track.albumhash in seen:
            continue

        seen.add(track.albumhash)
        refresh_album_art(
            track.albumhash,
            Path(track.folder),
            [track.filepath],
            settings.Paths(),
        )


# SECTION: the rename


def _find_track(filepath: str) -> Track | None:
    wanted = Path(filepath).as_posix()

    for track in TrackStore.get_tracks_by_filepaths([wanted]):
        if Path(track.filepath).as_posix() == wanted:
            return track

    return None


def build_changes(before, title: str, config: Any) -> tuple[TagChanges, set[str]]:
    """
    The tags to write for a new title.

    The app turns "(feat. X)" and "[ft. X]" in the tag title into artists. When
    the old title had such a part, those names move to the artist tag, so the
    participants are not lost when the title is replaced.

    :returns: the changes and the artist tags that may be created
    """
    changes = TagChanges(title=title if title != before.title else None)
    create: set[str] = set()

    if not config.extractFeaturedArtists:
        return changes, create

    names, _ = parse_feat_from_title(before.title or "", config)

    if not names:
        return changes, create

    if before.artist is not None:
        new_artist = append_artists(before.artist, names, config)

        if new_artist != before.artist:
            changes.artist = new_artist

            if before.albumartist is None:
                # With no ALBUMARTIST the app takes the owner of the album from
                # the artist, so the artist alone would change the album. Writing
                # the old artist as the album artist keeps it as it was.
                changes.albumartist = [before.artist[0]]
                create.add("albumartist")
    elif before.albumartist is not None:
        # the app took the artists from the album artist
        changes.artist = append_artists(list(before.albumartist), names, config)
        create.add("artist")

    return changes, create


def rename_track(filepath: str, title: str) -> dict[str, Any]:
    """
    Renames one file: the title tag and the file name become ``title``.

    :raises RenameError: nothing was changed
    """
    title = (title or "").strip()

    if not title:
        raise RenameError(400, "The title can not be empty")

    if len(title) > MAX_TITLE_LENGTH:
        raise RenameError(400, f"The title can have at most {MAX_TITLE_LENGTH} characters")

    track = _find_track(filepath)

    if track is None:
        raise RenameError(404, "Track not found")

    old_path = Path(track.filepath)
    suffix = old_path.suffix

    if suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise RenameError(400, f"unsupported format: {suffix or old_path.name}")

    if not old_path.is_file():
        raise RenameError(404, "The file is not there any more")

    config = UserConfig()

    try:
        before = read_tags(old_path)
    except TagWriteError as error:
        raise RenameError(400, str(error))

    changes, create_missing = build_changes(before, title, config)
    new_path = old_path.with_name(sanitize_filename(title, suffix))
    renames_file = new_path.name != old_path.name

    if renames_file and new_path.exists() and not _same_file(old_path, new_path):
        raise RenameError(409, f"A file named {new_path.name} already exists in this folder")

    old_trackhash = track.trackhash
    old_group = TrackStore.trackhashmap.get(old_trackhash)
    others_keep_old_hash = old_group is not None and len(old_group.tracks) > 1

    if renames_file:
        try:
            safe_rename(old_path, new_path)
        except FileExistsError:
            raise RenameError(409, f"A file named {new_path.name} already exists in this folder")
        except OSError as error:
            raise RenameError(500, f"Could not rename the file: {error}")

    try:
        if changes != TagChanges():
            write_tags(new_path, changes, create_missing=create_missing, config=config)
    except TagWriteError as error:
        if renames_file:
            try:
                safe_rename(new_path, old_path)
            except OSError as undo_error:
                log.error(f"Could not undo the rename of {old_path}: {undo_error}")

        raise RenameError(500, str(error))

    after = read_tags(new_path)

    try:
        new_track = reindex_files({old_path.as_posix(): new_path.as_posix()})[new_path.as_posix()]
    except Exception as error:
        raise RenameError(500, f"The file was changed, but reading it again failed: {error}")

    new_trackhash = new_track.trackhash
    moved: dict[str, int] = {}

    # another file keeps the old hash: the favorites and plays stay with it
    if new_trackhash != old_trackhash and not others_keep_old_hash:
        moved = rekey_hash("track", old_trackhash, new_trackhash)
        log_rekey("track", old_trackhash, new_trackhash, moved)

    ensure_album_thumbnails([new_track])
    reload_stores()
    _rebuild_recently_played()
    refresh_track_extras(new_trackhash)

    append_journal(
        {
            "action": "rename-track",
            "filepath_old": old_path.as_posix(),
            "filepath_new": new_path.as_posix(),
            "title_old": before.title,
            "title_new": after.title,
            "artist_old": before.artist,
            "artist_new": after.artist,
            "albumartist_old": before.albumartist,
            "albumartist_new": after.albumartist,
            "trackhash_old": old_trackhash,
            "trackhash_new": new_trackhash,
        }
    )

    stored = _find_track(new_path.as_posix()) or new_track

    return {
        "ok": True,
        "track": serialize_track(stored),
        "old_trackhash": old_trackhash,
        "new_trackhash": new_trackhash,
    }


def _rebuild_recently_played():
    from musix.lib.recipes.recents import RecentlyPlayed

    try:
        RecentlyPlayed()
    except Exception as error:
        log.warning(f"Could not rebuild the recently played row: {error}")
