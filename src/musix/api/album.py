"""
Contains all the album routes.
"""

import random
from dataclasses import asdict
from pathlib import Path

from flask_openapi3 import Tag
from pydantic import BaseModel, Field
from flask_openapi3 import APIBlueprint
from musix.api.apischemas import (
    AlbumHashSchema,
    AlbumLimitSchema,
    ArtistHashSchema,
)

from musix.api.auth import admin_required
from musix.config import UserConfig
from musix.db.userdata import AlbumTypeTable, SimilarArtistTable
from musix.lib.coverart import (
    find_best_cover,
    read_cover_for_embedding,
    refresh_album_art,
)
from musix.lib import albumrename
from musix.lib.tagwriter import TagChanges, TagWriteError, write_tags
from musix.models.album import Album
from musix.settings import Paths
from musix.store.albums import AlbumStore
from musix.store.albumtypes import ALBUM_KINDS, AlbumTypeStore
from musix.store.artists import ArtistStore
from musix.store.tracks import TrackStore
from musix.utils.hashing import create_hash
from musix.lib.albumslib import sort_by_track_no
from musix.serializers.album import serialize_for_card_many
from musix.serializers.track import serialize_tracks
from musix.utils.stats import get_track_group_stats


bp_tag = Tag(name="Album", description="Single album")
api = APIBlueprint("album", __name__, url_prefix="/album", abp_tags=[bp_tag])


class GetAlbumVersionsBody(BaseModel):
    og_album_title: str = Field(
        description="The original album title (album.og_title)",
    )

    albumhash: str = Field(
        description="The album hash of the album to exclude from the results.",
    )


class GetMoreFromArtistsBody(AlbumLimitSchema):
    albumartists: list = Field(
        description="The artist hashes to get more albums from",
    )

    base_title: str = Field(
        description="The base title of the album to exclude from the results.",
    )


class GetAlbumInfoBody(AlbumHashSchema, AlbumLimitSchema):
    pass


# NOTE: Don't use "/" as it will cause redirects (failure)
@api.post("")
def get_album_tracks_and_info(body: GetAlbumInfoBody):
    """
    Get album and tracks

    Returns album info and tracks for the given albumhash.
    """
    albumhash = body.albumhash
    albumentry = AlbumStore.albummap.get(albumhash)

    if albumentry is None:
        return {"error": "Album not found"}, 404

    album = albumentry.album
    tracks = TrackStore.get_tracks_by_trackhashes(albumentry.trackhashes)
    album.trackcount = len(tracks)
    album.duration = sum(t.duration for t in tracks)
    album.check_type(tracks)

    track_total = sum({int(t.extra.get("track_total", 1) or 1) for t in tracks})
    avg_bitrate = sum(t.bitrate for t in tracks) // (len(tracks) or 1)

    more_from_data = GetMoreFromArtistsBody(
        albumartists=[a["artisthash"] for a in album.albumartists],
        albumlimit=body.limit,
        base_title=album.base_title,
    )
    other_versions_data = GetAlbumVersionsBody(
        albumhash=albumhash,
        og_album_title=album.og_title,
    )

    more_from_albums = get_more_from_artist(more_from_data)
    other_versions = get_album_versions(other_versions_data)

    response = {
        "stats": get_track_group_stats(tracks, is_album=True),
        "info": {
            **asdict(album),
            "is_favorite": album.is_favorite,
        },
        "extra": {
            # INFO: track_total is the sum of a set of track_total values from each track
            # ASSUMPTIONS
            # 1. All the tracks have the correct track totals
            # 2. Tracks with the same track total are from the same disc
            "track_total": track_total,
            "avg_bitrate": avg_bitrate,
        },
        "copyright": tracks[0].copyright,
        "more_from": more_from_albums,
        "other_versions": other_versions,
    }

    response["tracks"] = serialize_tracks(tracks, remove_disc=False)
    return response


@api.get("/<albumhash>/tracks")
def get_album_tracks(path: AlbumHashSchema):
    """
    Get album tracks

    Returns all the tracks in the given album, sorted by disc and track number.
    NOTE: No album info is returned.
    """
    tracks = AlbumStore.get_album_tracks(path.albumhash)
    tracks = sort_by_track_no(tracks)

    return serialize_tracks(tracks)


@api.post("/<albumhash>/refresh-cover")
@admin_required()
def refresh_album_cover(path: AlbumHashSchema):
    """
    Refresh album cover

    Rebuilds the cached cover of the album from the folder image
    (cover.jpg, folder.jpg, ...) or, if there is none, from the embedded art.
    """
    tracks = AlbumStore.get_album_tracks(path.albumhash)

    if not tracks:
        return {"error": "Album not found"}, 404

    has_cover = refresh_album_art(
        path.albumhash,
        Path(tracks[0].folder),
        [track.filepath for track in tracks],
        Paths(),
        overwrite=True,
    )

    return {"ok": True, "has_cover": has_cover}


class AlbumTypeBody(BaseModel):
    kind: str | None = Field(
        None,
        description='"ep", "soundtrack", "live album" or null to remove the mark',
        json_schema_extra={"example": "ep"},
    )


@api.post("/<albumhash>/type")
@admin_required()
def set_album_type(path: AlbumHashSchema, body: AlbumTypeBody):
    """
    Mark the type of an album

    An album only counts as an EP, a soundtrack or a live album when it is marked
    by hand. One mark per album: marking again replaces the old mark and
    ``null`` removes it.
    """
    entry = AlbumStore.albummap.get(path.albumhash)

    if entry is None:
        return {"error": "Album not found"}, 404

    kind = body.kind

    if kind is not None and kind not in ALBUM_KINDS:
        return {"error": f"kind must be one of {', '.join(ALBUM_KINDS)} or null"}, 400

    AlbumTypeTable.set_kind(path.albumhash, kind)
    AlbumTypeStore.set(path.albumhash, kind)
    entry.album.check_type()

    return {"ok": True, "kind": kind}


@api.post("/<albumhash>/embed-cover")
@admin_required()
def embed_album_cover(path: AlbumHashSchema):
    """
    Save the cover into the files

    Writes the cover image of the album folder (cover.jpg, folder.jpg, ...) as the
    embedded cover of every music file of the album. Nothing is created or
    renamed in the folders. A file that fails does not stop the others.
    """
    albumhash = path.albumhash
    entry = AlbumStore.albummap.get(albumhash)

    if entry is None:
        return {"error": "Album not found"}, 404

    tracks = []
    for trackhash in entry.trackhashes:
        group = TrackStore.trackhashmap.get(trackhash)

        if group:
            tracks.extend(t for t in group.tracks if t.albumhash == albumhash)

    if not tracks:
        return {"error": "Album not found"}, 404

    cover = None
    for folder in dict.fromkeys(Path(t.folder) for t in tracks):
        cover = find_best_cover(folder)

        if cover is not None:
            break

    if cover is None:
        return {"error": "This album has no cover image in its folder"}, 400

    try:
        data, mime = read_cover_for_embedding(cover)
    except Exception:
        return {"error": f"Could not read the cover image {cover.name}"}, 400

    ok = 0
    failed: dict[str, str] = {}

    for track in tracks:
        try:
            write_tags(track.filepath, TagChanges(cover=(data, mime)))
            ok += 1
        except TagWriteError as error:
            failed[track.filepath] = str(error)
        except Exception as error:
            failed[track.filepath] = f"unexpected error: {error}"

    refresh_album_art(
        albumhash,
        Path(tracks[0].folder),
        [track.filepath for track in tracks],
        Paths(),
        overwrite=True,
    )

    return {
        "ok": True,
        "tracks_ok": ok,
        "tracks_failed": list(failed),
        "errors": failed,
    }


@api.post("/from-artist")
def get_more_from_artist(body: GetMoreFromArtistsBody):
    """
    Get more from artist

    Returns more albums from the given artist hashes.
    """
    albumartists = body.albumartists
    limit = body.limit
    base_title = body.base_title

    all_albums: dict[str, list[Album]] = {}

    for artisthash in albumartists:
        all_albums[artisthash] = AlbumStore.get_albums_by_artisthash(artisthash)

    seen_hashes = set()

    for artisthash, albums in all_albums.items():
        albums = [
            a
            for a in albums
            # INFO: filter out albums added to other artists
            if a.albumhash not in seen_hashes
            and artisthash in a.artisthashes
            # INFO: filter out albums with the same base title
            and create_hash(a.base_title) != create_hash(base_title)
        ]

        all_albums[artisthash] = serialize_for_card_many(
            [a for a in albums if create_hash(a.base_title) != create_hash(base_title)][
                :limit
            ]
        )
        # INFO: record albums added to other artists
        seen_hashes.update([a.albumhash for a in albums][:limit])

    return all_albums


@api.post("/other-versions")
def get_album_versions(body: GetAlbumVersionsBody):
    """
    Get other versions

    Returns other versions of the given album.
    """
    albumhash = body.albumhash

    album = AlbumStore.albummap.get(albumhash)
    if not album:
        return []
    artisthash = album.album.artisthashes[0]
    albums = AlbumStore.get_albums_by_artisthash(artisthash)

    basetitle = album.basetitle
    albums = [
        a
        for a in albums
        if a.og_title != album.album.og_title
        if a.base_title == basetitle
        and artisthash in {a["artisthash"] for a in a.albumartists}
    ]

    return serialize_for_card_many(albums)


class GetSimilarAlbumsQuery(ArtistHashSchema, AlbumLimitSchema):
    pass


@api.get("/similar")
def get_similar_albums(query: GetSimilarAlbumsQuery):
    """
    Get similar albums

    Returns similar albums to the given album.
    """
    artisthash = query.artisthash
    limit = query.limit

    similar_artists = SimilarArtistTable.get_by_hash(artisthash)

    if similar_artists is None:
        return []

    artisthashes = similar_artists.get_artist_hash_set()

    del similar_artists

    artists = ArtistStore.get_artists_by_hashes(artisthashes)
    albums = AlbumStore.get_albums_by_artisthashes([a.artisthash for a in artists])
    sample = random.sample(albums, min(len(albums), limit))

    return serialize_for_card_many(sample[:limit])


class RenameAlbumBody(BaseModel):
    title: str = Field(description="The new title of the album (the text of the album tag)")
    confirm: bool = Field(False, description="Must be true to start the rename")


def _rename_checks(albumhash: str, title: str):
    """
    Returns ``(entry, title)`` or ``(None, error response)``.
    """
    entry = AlbumStore.albummap.get(albumhash)

    if entry is None:
        return None, ({"error": "Album not found"}, 404)

    try:
        return entry, albumrename.validate_new_title(title)
    except albumrename.RenameError as error:
        return None, ({"error": error.message}, error.status)


@api.post("/<albumhash>/rename/preview")
@admin_required()
def preview_album_rename(path: AlbumHashSchema, body: RenameAlbumBody):
    """
    Preview renaming an album

    Says what would change if the album were renamed in all its files: how many files,
    the different titles the album tag has now, the files that can not be written or have
    no album tag, whether the hash of the album changes and whether the new title is an
    album that already exists (the two would be merged). Reads tags and writes nothing.
    """
    entry, checked = _rename_checks(path.albumhash, body.title)

    if entry is None:
        return checked

    try:
        return albumrename.build_preview(path.albumhash, checked, UserConfig())
    except albumrename.RenameError as error:
        return {"error": error.message}, error.status


@api.post("/<albumhash>/rename")
@admin_required()
def rename_album(path: AlbumHashSchema, body: RenameAlbumBody):
    """
    Rename an album in all its files

    Needs ``confirm: true``. Writes the album tag of every file of the album, in the
    background, one file at a time, through the safe tag writer; a file that fails does
    not stop the others. Follow it with ``GET /album/rename/status``. Only one rename (of
    an album or of an artist) runs at a time.
    """
    entry, checked = _rename_checks(path.albumhash, body.title)

    if entry is None:
        return checked

    if not body.confirm:
        return {"error": "Send confirm: true to start the rename"}, 400

    try:
        albumrename.start_rename(path.albumhash, checked, UserConfig())
    except albumrename.RenameError as error:
        return {"error": error.message}, error.status

    return {"ok": True, "started": True}, 202


@api.get("/rename/status")
def album_rename_status():
    """
    Progress of the album rename

    How many files are done, the errors by file and, when it finishes, the new
    albumhash (the same one when it did not change) and the files that failed.
    """
    return albumrename.job_status()
