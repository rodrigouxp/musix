"""
Moving everything the app keeps under a hash to a new hash.

The hash of a track, album or artist comes from tags (``Track.recreate_trackhash``,
``create_hash(album, *albumartists)``, ``create_hash(name)``), so when a tag
changes the hash changes, and everything that was saved under the old one would be
orphaned: favorites, plays, playlists, collections, colours, similar artists,
album marks, the artist photos and the album thumbnails.

``rekey_hash(kind, old, new)`` moves all of it. If the new hash already exists
(two things became one) the data is joined without duplicates and the data of the
new hash wins when both have a value.

The in-memory stores are not touched here: they are rebuilt from the database by
the caller (``reload_stores``).
"""

import os
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert, select, update

from musix.db.engine import DbEngine
from musix.db.userdata import (
    AlbumTypeTable,
    CollectionTable,
    FavoritesTable,
    LibDataTable,
    PlaylistTable,
    ScrobbleTable,
    SimilarArtistTable,
)
import logging

log = logging.getLogger(__name__)
from musix.store.albumtypes import AlbumTypeStore
from musix.store.homepage import HomepageStore

KINDS = ("track", "album", "artist")

# how each kind is written in the ``source`` of a scrobble
SOURCE_PREFIX = {"track": "tr:", "album": "al:", "artist": "ar:"}


def rekey_hash(kind: str, old: str, new: str) -> dict[str, int]:
    """
    Moves everything saved under ``old`` to ``new``.

    :param kind: ``"track"``, ``"album"`` or ``"artist"``
    :returns: how many records were moved or joined, by table (for the journal)
    """
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind}")

    if not old or not new or old == new:
        return {}

    moved: dict[str, int] = {}

    with DbEngine.manager(commit=True) as conn:
        moved["favorites"] = _favorites(conn, kind, old, new)
        moved["scrobbles"] = _scrobbles(conn, kind, old, new)

        if kind == "track":
            moved["playlists"] = _playlists(conn, old, new)
        else:
            moved["collections"] = _collections(conn, kind, old, new)
            moved["libdata"] = _libdata(conn, kind, old, new)

        if kind == "album":
            moved["album_types"] = _album_type(conn, old, new)

        if kind == "artist":
            moved["similar_artists"] = _similar_artists(conn, old, new)

    if kind == "album":
        AlbumTypeStore.load(AlbumTypeTable.get_all())
        moved["thumbnails"] = _move_album_files(old, new)

    if kind == "artist":
        moved["photos"] = _move_artist_files(old, new)

    _homepage(kind, old, new)

    return {table: count for table, count in moved.items() if count}


# SECTION: tables


def _favorites(conn, kind: str, old: str, new: str) -> int:
    table = FavoritesTable
    # the prefixed form and the old form without prefix
    old_keys = (f"{kind}_{old}", old)
    new_keys = (f"{kind}_{new}", new)

    old_rows = conn.execute(
        select(table.id).where(table.hash.in_(old_keys) & (table.type == kind))
    ).all()

    if not old_rows:
        return 0

    target_exists = (
        conn.execute(
            select(table.id).where(table.hash.in_(new_keys) & (table.type == kind))
        ).first()
        is not None
    )
    ids = [r.id for r in old_rows]

    if target_exists:
        # already a favorite under the new hash: the old one is the same favorite
        conn.execute(delete(table).where(table.id.in_(ids)))
    else:
        conn.execute(update(table).where(table.id.in_(ids)).values(hash=f"{kind}_{new}"))

    return len(ids)


def _scrobbles(conn, kind: str, old: str, new: str) -> int:
    table = ScrobbleTable
    prefix = SOURCE_PREFIX[kind]
    count = 0

    if kind == "track":
        count += conn.execute(
            update(table).where(table.trackhash == old).values(trackhash=new)
        ).rowcount

    # plays that came from this track, album or artist page
    count += conn.execute(
        update(table).where(table.source == prefix + old).values(source=prefix + new)
    ).rowcount

    return count


def _playlists(conn, old: str, new: str) -> int:
    table = PlaylistTable
    count = 0

    for row in conn.execute(select(table.id, table.trackhashes)).all():
        hashes = list(row.trackhashes or [])

        if old not in hashes:
            continue

        result: list[str] = []
        seen_new = False

        for trackhash in hashes:
            if trackhash in (old, new):
                if seen_new:
                    continue  # the playlist had both: keep one

                seen_new = True
                result.append(new)
            else:
                result.append(trackhash)

        conn.execute(update(table).where(table.id == row.id).values(trackhashes=result))
        count += 1

    return count


def _collections(conn, kind: str, old: str, new: str) -> int:
    table = CollectionTable
    count = 0

    for row in conn.execute(select(table.id, table.items)).all():
        items: list[dict[str, Any]] = list(row.items or [])

        if not any(i.get("type") == kind and i.get("hash") == old for i in items):
            continue

        result: list[dict[str, Any]] = []
        seen_new = False

        for item in items:
            if item.get("type") == kind and item.get("hash") in (old, new):
                if seen_new:
                    continue

                seen_new = True
                result.append({**item, "hash": new})
            else:
                result.append(item)

        conn.execute(update(table).where(table.id == row.id).values(items=result))
        count += 1

    return count


def _libdata(conn, kind: str, old: str, new: str) -> int:
    """
    Colours, blurhash, bio and info of an album or artist (the ``artistdata`` table).
    """
    table = LibDataTable
    old_row = conn.execute(select(table).where(table.itemhash == kind + old)).scalar()

    if old_row is None:
        return 0

    new_row = conn.execute(select(table).where(table.itemhash == kind + new)).scalar()

    if new_row is None:
        conn.execute(
            update(table).where(table.id == old_row.id).values(itemhash=kind + new)
        )
        return 1

    # both exist: keep the new one and fill what it lacks from the old one
    fill: dict[str, Any] = {}

    for column in ("color", "bio", "info"):
        if not getattr(new_row, column) and getattr(old_row, column):
            fill[column] = getattr(old_row, column)

    extra = {**(old_row.extra or {}), **(new_row.extra or {})}

    if extra != (new_row.extra or {}):
        fill["extra"] = extra

    if fill:
        conn.execute(update(table).where(table.id == new_row.id).values(**fill))

    conn.execute(delete(table).where(table.id == old_row.id))
    return 1


def _album_type(conn, old: str, new: str) -> int:
    table = AlbumTypeTable

    if conn.execute(select(table.albumhash).where(table.albumhash == old)).first() is None:
        return 0

    if conn.execute(select(table.albumhash).where(table.albumhash == new)).first() is None:
        conn.execute(update(table).where(table.albumhash == old).values(albumhash=new))
    else:
        # the album that stays keeps its own mark
        conn.execute(delete(table).where(table.albumhash == old))

    return 1


def _similar_artists(conn, old: str, new: str) -> int:
    table = SimilarArtistTable
    count = 0

    # the entries of every artist that point to the old one
    for row in conn.execute(select(table.id, table.similar_artists)).all():
        entries = list(row.similar_artists or [])

        if not any(e.get("artisthash") == old for e in entries):
            continue

        result: list[dict[str, Any]] = []
        seen_new = False

        for entry in entries:
            if entry.get("artisthash") in (old, new):
                if seen_new:
                    continue

                seen_new = True
                result.append({**entry, "artisthash": new})
            else:
                result.append(entry)

        conn.execute(update(table).where(table.id == row.id).values(similar_artists=result))
        count += 1

    # the row of the artist itself
    old_row = conn.execute(select(table).where(table.artisthash == old)).scalar()

    if old_row is not None:
        new_row = conn.execute(select(table).where(table.artisthash == new)).scalar()

        if new_row is None:
            conn.execute(update(table).where(table.id == old_row.id).values(artisthash=new))
        else:
            known = {e.get("artisthash") for e in (new_row.similar_artists or [])}
            joined = list(new_row.similar_artists or []) + [
                e
                for e in (old_row.similar_artists or [])
                if e.get("artisthash") not in known and e.get("artisthash") != new
            ]
            conn.execute(
                update(table).where(table.id == new_row.id).values(similar_artists=joined)
            )
            conn.execute(delete(table).where(table.id == old_row.id))

        count += 1

    return count


# SECTION: files named by hash


def _move_file(old: Path, new: Path) -> bool:
    """
    Renames a cache file. Never overwrites: if the new name is taken, the old
    file stays where it is (it is only a cache of something that can be rebuilt).
    """
    if not old.exists() or new.exists():
        return False

    new.parent.mkdir(parents=True, exist_ok=True)
    os.replace(old, new)
    return True


def _move_album_files(old: str, new: str) -> int:
    from musix.lib.coverart import _source_sidecar, _thumb_targets
    from musix.settings import Paths

    paths = Paths()
    moved = 0

    for (old_path, _), (new_path, _) in zip(_thumb_targets(old, paths), _thumb_targets(new, paths)):
        moved += _move_file(old_path, new_path)

    moved += _move_file(_source_sidecar(old, paths), _source_sidecar(new, paths))
    return moved


def _move_artist_files(old: str, new: str) -> int:
    from musix.lib.artistlib import artist_image_entries, manual_marker_path

    moved = 0

    for (old_path, _), (new_path, _) in zip(
        artist_image_entries(f"{old}.webp"), artist_image_entries(f"{new}.webp")
    ):
        moved += _move_file(old_path, new_path)

    moved += _move_file(manual_marker_path(old), manual_marker_path(new))
    return moved


# SECTION: in memory


def _homepage(kind: str, old: str, new: str):
    """
    The rows of the homepage that are kept in memory ("top artists" and the like).
    """
    for entry in HomepageStore.entries.values():
        for items in entry.items.values():
            if not isinstance(items, list):
                continue

            for item in items:
                if isinstance(item, dict) and item.get("type") == kind and item.get("hash") == old:
                    item["hash"] = new


def refresh_track_extras(trackhash: str):
    """
    Updates the extra info kept with a track's favorites and plays (title, artists
    and file path, used to restore a backup) after the track changed.
    """
    from musix.lib.extras import get_extra_info

    extra = get_extra_info(trackhash, "track")

    if not extra:
        return

    with DbEngine.manager(commit=True) as conn:
        conn.execute(
            update(FavoritesTable)
            .where(FavoritesTable.hash.in_((f"track_{trackhash}", trackhash)))
            .values(extra=extra)
        )

        for row in conn.execute(
            select(ScrobbleTable.id, ScrobbleTable.extra).where(ScrobbleTable.trackhash == trackhash)
        ).all():
            conn.execute(
                update(ScrobbleTable)
                .where(ScrobbleTable.id == row.id)
                .values(extra={**(row.extra or {}), **extra})
            )


def log_rekey(kind: str, old: str, new: str, moved: dict[str, int]):
    if moved:
        log.info(f"Moved {kind} {old} -> {new}: {moved}")
