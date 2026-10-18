"""
Contains all the artist(s) routes.
"""

import math
import random
from io import BytesIO
from datetime import datetime, timezone
from typing import Any

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from PIL import Image, ImageOps
from pydantic import Field
from musix.api.apischemas import (
    AlbumLimitSchema,
    ArtistHashSchema,
    ArtistLimitSchema,
    TrackLimitSchema,
)

from musix.api.auth import admin_required
from musix.db.userdata import SimilarArtistTable
from musix.lib.artistlib import (
    DownloadImage,
    artist_image_entries,
    get_artist_image_link,
    set_manual_artist_image,
    update_artist_color,
)
from musix.lib.sortlib import sort_tracks
from musix.models.track import Track

from musix.serializers.album import serialize_for_card_many
from musix.serializers.artist import serialize_for_cards, serialize_for_card
from musix.serializers.track import serialize_track

from musix.store.albums import AlbumStore
from musix.store.artists import ArtistStore
from musix.store.tracks import TrackStore
from musix.utils.stats import get_track_group_stats

bp_tag = Tag(name="Artist", description="Single artist")
api = APIBlueprint("artist", __name__, url_prefix="/artist", abp_tags=[bp_tag])


class GetArtistAlbumsQuery(AlbumLimitSchema):
    all: bool = Field(
        description="Whether to ignore albumlimit and return all albums", default=False
    )


class GetArtistQuery(TrackLimitSchema, GetArtistAlbumsQuery):
    albumlimit: int = Field(7, description="The number of albums to return")


@api.get("/<string:artisthash>")
def get_artist(path: ArtistHashSchema, query: GetArtistQuery):
    """
    Get artist

    Returns artist data, tracks and genres for the given artisthash.
    """
    artisthash = path.artisthash
    limit = query.limit

    entry = ArtistStore.artistmap.get(artisthash)

    if entry is None:
        return {"error": "Artist not found"}, 404

    tracks = TrackStore.get_tracks_by_trackhashes(entry.trackhashes)
    tracks = sort_tracks(tracks, key="playcount", reverse=True)
    tcount = len(tracks)

    artist = entry.artist
    if artist.albumcount == 0 and tcount < 10:
        limit = tcount

    try:
        year = datetime.fromtimestamp(artist.date, tz=timezone.utc).year
    except ValueError:
        year = 0

    genres = [*artist.genres]
    decade = None

    if year:
        decade = math.floor(year / 10) * 10
        decade = str(decade)[2:] + "s"

    if decade:
        genres.insert(0, {"name": decade, "genrehash": decade})

    stats = get_track_group_stats(tracks)
    duration = sum(t.duration for t in tracks) if tracks else 0
    tracks = tracks[:limit] if (limit and limit != -1) else tracks
    tracks = [
        {
            **serialize_track(t),
            "help_text": (
                "unplayed"
                if t.playcount == 0
                else f"{t.playcount} play{'' if t.playcount == 1 else 's'}"
            ),
        }
        for t in tracks
    ]

    query.limit = query.albumlimit
    albums = get_artist_albums(path, query)

    return {
        "artist": {
            **serialize_for_card(artist),
            "duration": duration,
            "trackcount": tcount,
            "albumcount": artist.albumcount,
            "genres": genres,
            "is_favorite": artist.is_favorite,
        },
        "tracks": tracks,
        "albums": albums,
        "stats": stats,
    }


@api.get("/<artisthash>/albums")
def get_artist_albums(path: ArtistHashSchema, query: GetArtistAlbumsQuery):
    """
    Get artist albums.
    """
    return_all = query.all
    artisthash = path.artisthash

    limit = query.limit

    entry = ArtistStore.artistmap.get(artisthash)

    if entry is None:
        return {"error": "Artist not found"}, 404

    albums = AlbumStore.get_albums_by_hashes(entry.albumhashes)
    tracks = TrackStore.get_tracks_by_trackhashes(entry.trackhashes)

    missing_albumhashes = {
        t.albumhash for t in tracks if t.albumhash not in {a.albumhash for a in albums}
    }

    albums.extend(AlbumStore.get_albums_by_hashes(missing_albumhashes))
    albumdict = {a.albumhash: a for a in albums}

    tracks_by_album: dict[str, list[Track]] = {}
    for track in tracks:
        tracks_by_album.setdefault(track.albumhash, []).append(track)

    for albumhash, album_tracks in tracks_by_album.items():
        album = albumdict.get(albumhash)

        if album:
            album.check_type(album_tracks)

    albums = [a for a in albumdict.values()]
    all_albums = sorted(albums, key=lambda a: a.date, reverse=True)

    res: dict[str, Any] = {
        "albums": [],
        "appearances": [],
        "compilations": [],
        "singles_and_eps": [],
        "soundtracks": [],
        "live_albums": [],
    }

    for album in all_albums:
        if album.type == "ep":
            res["singles_and_eps"].append(album)
        elif album.type == "soundtrack":
            res["soundtracks"].append(album)
        elif album.type == "live album":
            res["live_albums"].append(album)
        elif album.type == "compilation":
            res["compilations"].append(album)
        elif (
            album.albumhash in missing_albumhashes
            or artisthash not in album.artisthashes
        ):
            res["appearances"].append(album)
        else:
            res["albums"].append(album)

    if return_all:
        limit = len(all_albums)

    # loop through the res dict and serialize the albums
    for key, value in res.items():
        res[key] = serialize_for_card_many(value[:limit])

    res["artistname"] = entry.artist.name
    return res


@api.get("/<artisthash>/tracks")
def get_all_artist_tracks(path: ArtistHashSchema):
    """
    Get artist tracks

    Returns all artists by a given artist.
    """
    tracks = ArtistStore.get_artist_tracks(path.artisthash)
    tracks = sort_tracks(tracks, key="playcount", reverse=True)
    tracks = [
        {
            **serialize_track(t),
            "help_text": (
                "unplayed"
                if t.playcount == 0
                else f"{t.playcount} play{'' if t.playcount == 1 else 's'}"
            ),
        }
        for t in tracks
    ]

    return tracks


@api.get("/<artisthash>/similar")
def get_similar_artists(path: ArtistHashSchema, query: ArtistLimitSchema):
    """
    Get similar artists.
    """
    limit = query.limit
    result = SimilarArtistTable.get_by_hash(path.artisthash)

    if result is None:
        return []

    similar = ArtistStore.get_artists_by_hashes(result.get_artist_hash_set())

    if len(similar) > limit:
        similar = random.sample(similar, min(limit, len(similar)))

    return serialize_for_cards(similar[:limit])


MAX_ARTIST_IMAGE_BYTES = 10 * 1024 * 1024
ARTIST_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def read_uploaded_artist_image() -> tuple[Image.Image | None, str]:
    """
    Reads the ``image`` field of the request. Returns the image (RGB, cut to
    the central square) or ``None`` and the reason it was refused.
    """
    file = request.files.get("image")

    if file is None:
        return None, "Send the photo in the image field"

    data = file.stream.read(MAX_ARTIST_IMAGE_BYTES + 1)

    if len(data) > MAX_ARTIST_IMAGE_BYTES:
        return None, "The photo is bigger than 10 MB"

    try:
        img = Image.open(BytesIO(data))
        image_format = img.format
        img.load()
    except Exception:
        return None, "That file is not an image"

    if image_format not in ARTIST_IMAGE_FORMATS:
        return None, "Only JPEG, PNG or WEBP photos are accepted"

    img = ImageOps.exif_transpose(img).convert("RGB")
    side = min(img.width, img.height)
    left = (img.width - side) // 2
    top = (img.height - side) // 2

    return img.crop((left, top, left + side, top + side)), ""


@api.post("/<artisthash>/image")
@admin_required()
def upload_artist_image(path: ArtistHashSchema):
    """
    Upload the artist photo

    Send a JPEG, PNG or WEBP (up to 10 MB) in the ``image`` form field. The
    photo is marked as chosen by hand, so the automatic download never replaces it.
    """
    artisthash = path.artisthash

    if ArtistStore.artistmap.get(artisthash) is None:
        return {"error": "Artist not found"}, 404

    img, reason = read_uploaded_artist_image()

    if img is None:
        return {"error": reason}, 400

    name = f"{artisthash}.webp"
    DownloadImage.save_img(img, artist_image_entries(name))
    set_manual_artist_image(artisthash, True)
    update_artist_color(artisthash)

    return {"ok": True, "image": name, "source": "upload"}


@api.post("/<artisthash>/image/refetch")
@admin_required()
def refetch_artist_image(path: ArtistHashSchema):
    """
    Fetch the automatic artist photo again

    Downloads the photo from Deezer, replaces the current one (even one chosen
    by hand) and removes the "chosen by hand" mark.
    """
    artisthash = path.artisthash
    entry = ArtistStore.artistmap.get(artisthash)

    if entry is None:
        return {"error": "Artist not found"}, 404

    url = get_artist_image_link(entry.artist.name)

    if url is None:
        return {"error": "No automatic photo was found for this artist"}, 502

    name = f"{artisthash}.webp"

    if not DownloadImage(url, name).saved:
        return {"error": "Could not download the photo"}, 502

    set_manual_artist_image(artisthash, False)
    update_artist_color(artisthash)

    return {"ok": True, "image": name, "source": "deezer"}
