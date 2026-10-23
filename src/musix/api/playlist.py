"""
All playlist-related routes.
"""

import json
from datetime import datetime
import pathlib
from typing import Any

from PIL import UnidentifiedImageError, Image
from pydantic_core import core_schema
from pydantic import BaseModel, Field, GetCoreSchemaHandler

from flask_openapi3 import Tag
from flask_openapi3 import APIBlueprint, FileStorage as _FileStorage

from musix import models
from musix.api.apischemas import GenericLimitSchema
from musix.db.userdata import PlaylistTable
from musix.lib import playlistlib
from musix.lib.albumslib import sort_by_track_no
from musix.lib.home.recentlyadded import get_recently_added_playlist
from musix.lib.home.recentlyplayed import get_recently_played_playlist
from musix.lib.sortlib import sort_tracks
from musix.models.playlist import Playlist
from musix.serializers.playlist import serialize_for_card
from musix.serializers.track import serialize_tracks

from musix.store.tracks import TrackStore
from musix.utils.dates import create_new_date, date_string_to_time_passed
from musix.settings import Paths

tag = Tag(name="Playlists", description="Get and manage playlists")
api = APIBlueprint("playlists", __name__, url_prefix="/playlists", abp_tags=[tag])


def insert_playlist(name: str, image: str = None):
    playlist = {
        "image": image,
        "last_updated": create_new_date(),
        "name": name,
        "trackhashes": [],
        "settings": {
            "has_gif": False,
            "banner_pos": 50,
            "pinned": False,
        },
    }

    rowid = PlaylistTable.add_one(playlist)
    if rowid:
        playlist["id"] = rowid
        return Playlist(**playlist)

    return None


def get_path_trackhashes(path: str, tracksortby: str, reverse: bool):
    """
    Returns a list of trackhashes in a folder.
    """
    tracks = TrackStore.get_tracks_in_path(path)
    tracks = sort_tracks(tracks, key=tracksortby, reverse=reverse)
    return [t.trackhash for t in tracks]


def get_album_trackhashes(albumhash: str):
    """
    Returns a list of trackhashes in an album.
    """
    tracks = TrackStore.get_tracks_by_albumhash(albumhash)
    tracks = sort_by_track_no(tracks)

    return [t.trackhash for t in tracks]


def get_artist_trackhashes(artisthash: str):
    """
    Returns a list of trackhashes for an artist.
    """
    tracks = TrackStore.get_tracks_by_artisthash(artisthash)
    tracks = sort_tracks(tracks, key="playcount", reverse=True)
    return [t.trackhash for t in tracks]


def format_custom_playlist(playlist: models.Playlist, tracks: list[models.Track]):
    playlist.duration = sum(t.duration for t in tracks)
    playlist.count = len(tracks)

    return {
        "info": serialize_for_card(playlist),
        "tracks": serialize_tracks(tracks),
    }


class SendAllPlaylistsQuery(BaseModel):
    no_images: bool = Field(False, description="Whether to include images")


@api.get("")
def send_all_playlists(query: SendAllPlaylistsQuery):
    """
    Gets all the playlists.
    """
    playlists = PlaylistTable.get_all()
    playlists = sorted(
        playlists,
        key=lambda p: datetime.strptime(p.last_updated, "%Y-%m-%d %H:%M:%S"),
        reverse=True,
    )

    for playlist in playlists:
        if not playlist.has_image:
            playlist.images = playlistlib.get_first_4_images(
                trackhashes=playlist.trackhashes
            )

        playlist.clear_lists()

    # playlists.sort(
    #     key=lambda p: datetime.strptime(p.last_updated, "%Y-%m-%d %H:%M:%S"),
    #     reverse=True,
    # )

    return {"data": playlists}


class CreatePlaylistBody(BaseModel):
    name: str = Field(..., description="The name of the playlist")


@api.post("/new")
def create_playlist(body: CreatePlaylistBody):
    """
    New playlist

    Creates a new playlist. Accepts POST method with a JSON body.
    """
    exists = PlaylistTable.check_exists_by_name(body.name)

    if exists:
        return {"error": "Playlist already exists"}, 409

    playlist = insert_playlist(body.name)

    if playlist is None:
        return {"error": "Playlist could not be created"}, 500

    return {"playlist": playlist}, 201


class PlaylistIDPath(BaseModel):
    # INFO: playlistid string examples: "recentlyadded"
    playlistid: str = Field(..., description="The ID of the playlist")


class AddItemToPlaylistBody(BaseModel):
    itemtype: str = Field(
        default="tracks",
        description="The type of item to add",
        examples=["tracks", "folder", "album", "artist"],
    )
    sortoptions: dict = Field(
        default=None,
        description="The sort options for the tracks",
    )
    itemhash: str = Field(..., description="The hash of the item to add")


@api.post("/<playlistid>/add")
def add_item_to_playlist(path: PlaylistIDPath, body: AddItemToPlaylistBody):
    """
    Add to playlist.

    If itemtype is not "tracks", itemhash is expected to be a folder, album or artist hash.
    """
    itemtype = body.itemtype
    itemhash = body.itemhash
    playlist_id = int(path.playlistid)
    sortoptions = body.sortoptions

    if itemtype == "tracks":
        trackhashes = itemhash.split(",")
        if len(trackhashes) == 1 and trackhashes[0] in PlaylistTable.get_trackhashes(
            playlist_id
        ):
            return {"msg": "Track already exists in playlist"}, 409
    elif itemtype == "folder":
        trackhashes = get_path_trackhashes(
            itemhash,
            sortoptions.get("tracksortby") or "default",
            sortoptions.get("tracksortreverse") or False,
        )
    elif itemtype == "album":
        trackhashes = get_album_trackhashes(itemhash)
    elif itemtype == "artist":
        trackhashes = get_artist_trackhashes(itemhash)
    else:
        trackhashes = []

    PlaylistTable.append_to_playlist(playlist_id, trackhashes)
    return {"msg": "Done"}, 200


class GetPlaylistQuery(GenericLimitSchema):
    no_tracks: bool = Field(False, description="Whether to include tracks")
    start: int = Field(0, description="The start index of the tracks")


@api.get("/<playlistid>")
def get_playlist(path: PlaylistIDPath, query: GetPlaylistQuery):
    """
    Get playlist by id
    """
    no_tracks = query.no_tracks
    playlistid = path.playlistid

    custom_playlists = [
        {"name": "recentlyadded", "handler": get_recently_added_playlist},
        {"name": "recentlyplayed", "handler": get_recently_played_playlist},
    ]
    is_custom = playlistid in {p["name"] for p in custom_playlists}

    if is_custom:
        if query.start != 0:
            return {
                "tracks": [],
            }

        handler = next(
            p["handler"] for p in custom_playlists if p["name"] == playlistid
        )
        playlist, tracks = handler()
        return format_custom_playlist(playlist, tracks)

    playlist = PlaylistTable.get_by_id(int(playlistid))

    if playlist is None:
        return {"msg": "Playlist not found"}, 404

    if query.limit == -1:
        # every track
        query.limit = len(playlist.trackhashes)

    tracks = TrackStore.get_tracks_by_trackhashes(
        playlist.trackhashes[query.start : query.start + query.limit]
    )
    duration = sum(t.duration for t in tracks)
    playlist._last_updated = date_string_to_time_passed(playlist.last_updated)
    playlist.duration = duration
    playlist.images = playlistlib.get_first_4_images(tracks)
    playlist.clear_lists()

    return {
        "info": playlist,
        "tracks": serialize_tracks(tracks) if not no_tracks else [],
    }


class FileStorage(_FileStorage):
    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.with_info_plain_validator_function(cls.validate)


def get_playlist_id(path: PlaylistIDPath) -> int | None:
    """
    The numeric id of the path. Special playlists ("recentlyadded") have none.
    """
    try:
        return int(path.playlistid)
    except ValueError:
        return None


class UpdatePlaylistForm(BaseModel):
    # INFO: not `X | None`: flask-openapi3 reads a form field whose schema is an anyOf as JSON
    # (a name like "2024" would arrive as a number and the file would not arrive at all)
    image: FileStorage = Field(
        None, description="The cover (cut to the central square). Without it the cover stays"
    )
    name: str = Field(None, description="The name of the playlist. Without it the name stays")
    settings: str = Field(
        None,
        description="The settings of the playlist. Without them the settings stay",
        json_schema_extra={"example": '{"pinned": false}'},
    )


# the settings that the client can not set through the update
SETTINGS_SET_BY_THE_SERVER = {"has_gif", "square_img", "favorite"}


@api.put("/<playlistid>/update", methods=["PUT"])
def update_playlist_info(path: PlaylistIDPath, form: UpdatePlaylistForm):
    """
    Update playlist

    Every field is optional: only what is sent changes. The cover is cut to the
    central square. A name that another playlist of the user has is a 409.
    """
    playlist_id = get_playlist_id(path)
    db_playlist = PlaylistTable.get_by_id(playlist_id) if playlist_id is not None else None

    if db_playlist is None:
        return {"error": "Playlist not found"}, 404

    changes: dict[str, Any] = {"last_updated": create_new_date()}
    settings = dict(db_playlist.settings)

    if form.name is not None:
        name = form.name.strip()

        if not name:
            return {"error": "The name can not be empty"}, 400

        if PlaylistTable.check_exists_by_name(name, exclude_id=playlist_id):
            return {"error": "Playlist already exists"}, 409

        changes["name"] = name

    if form.settings:
        try:
            sent = json.loads(form.settings)
        except ValueError:
            return {"error": "The settings are not valid JSON"}, 400

        if not isinstance(sent, dict):
            return {"error": "The settings are not valid JSON"}, 400

        settings.update({k: v for k, v in sent.items() if k not in SETTINGS_SET_BY_THE_SERVER})

    if form.image:
        try:
            pil_image = Image.open(form.image)
            is_gif = pil_image.format == "GIF"
            changes["image"] = playlistlib.save_p_image(pil_image, playlist_id, form.image.content_type)
        except (UnidentifiedImageError, OSError, ValueError):
            # a file that was half written is an orphan now
            playlistlib.cleanup_playlist_images()
            return {"error": "Failed: Invalid image"}, 400

        settings["has_gif"] = is_gif

    changes["settings"] = settings

    PlaylistTable.update_one(playlist_id, changes)
    playlistlib.cleanup_playlist_images()

    playlist = PlaylistTable.get_by_id(playlist_id)
    playlist._last_updated = date_string_to_time_passed(playlist.last_updated)

    if not playlist.has_image:
        playlist.images = playlistlib.get_first_4_images(trackhashes=playlist.trackhashes)

    playlist.clear_lists()

    return {
        "data": playlist,
    }


@api.post("/<playlistid>/pin_unpin")
def pin_unpin_playlist(path: PlaylistIDPath):
    """
    Pin playlist.
    """
    playlist_id = get_playlist_id(path)
    playlist = PlaylistTable.get_by_id(playlist_id) if playlist_id is not None else None

    if playlist is None:
        return {"error": "Playlist not found"}, 404

    settings = playlist.settings

    try:
        settings["pinned"] = not settings["pinned"]
    except KeyError:
        settings["pinned"] = True

    PlaylistTable.update_settings(playlist_id, settings)
    return {"msg": "Done"}, 200


@api.post("/<playlistid>/favorite")
def favorite_playlist(path: PlaylistIDPath):
    """
    Favorite or unfavorite a playlist.

    The favorite is kept in the settings of the playlist (like the pin), so the
    favorites API, which only knows tracks, albums and artists, does not change.
    """
    playlist_id = get_playlist_id(path)
    playlist = PlaylistTable.get_by_id(playlist_id) if playlist_id is not None else None

    if playlist is None:
        return {"error": "Playlist not found"}, 404

    settings = dict(playlist.settings)
    settings["favorite"] = not settings.get("favorite", False)

    PlaylistTable.update_settings(playlist_id, settings)
    return {"msg": "Done", "is_favorite": settings["favorite"]}, 200


class MoveTrackBody(BaseModel):
    trackhash: str = Field(..., description="The track to move")
    to_index: int | None = Field(
        None, description="The position the track goes to (0 is the first)"
    )
    after_trackhash: str | None = Field(
        None,
        description="Or: the track it goes right after. It is how the client says it when the "
        "playlist has tracks that are not in the library anymore (the client does not see them, so "
        "its positions are not the ones of the list)",
    )


@api.post("/<playlistid>/move-track")
def move_track_in_playlist(path: PlaylistIDPath, body: MoveTrackBody):
    """
    Move a track to another position of the playlist.

    404 if the playlist is not the user's or does not have the track, 400 if
    to_index is not a position of the list (or neither to_index nor after_trackhash was sent).
    """
    playlist_id = get_playlist_id(path)
    trackhashes = PlaylistTable.get_trackhashes(playlist_id) if playlist_id is not None else None

    if trackhashes is None:
        return {"error": "Playlist not found"}, 404

    if body.trackhash not in trackhashes:
        return {"error": "The track is not in the playlist"}, 404

    if body.after_trackhash is not None:
        others = [h for h in trackhashes if h != body.trackhash]

        if body.after_trackhash == body.trackhash:
            to_index = trackhashes.index(body.trackhash)
        elif body.after_trackhash not in others:
            return {"error": "The track to go after is not in the playlist"}, 404
        else:
            to_index = others.index(body.after_trackhash) + 1
    elif body.to_index is not None:
        to_index = body.to_index
    else:
        return {"error": "Send to_index or after_trackhash"}, 400

    if not 0 <= to_index < len(trackhashes):
        return {"error": "to_index is outside of the playlist"}, 400

    # the same position: nothing to save
    if trackhashes.index(body.trackhash) != to_index:
        PlaylistTable.move_track(playlist_id, body.trackhash, to_index)

    return {"msg": "Done"}, 200


@api.delete("/<playlistid>/remove-img")
def remove_playlist_image(path: PlaylistIDPath):
    """
    Clear playlist image.
    """
    playlist = PlaylistTable.get_by_id(path.playlistid)

    if playlist is None:
        return {"error": "Playlist not found"}, 404

    PlaylistTable.remove_image(path.playlistid)
    PlaylistTable.update_settings(path.playlistid, {**playlist.settings, "has_gif": False})
    playlistlib.cleanup_playlist_images()

    playlist.image = None
    playlist.thumb = None
    playlist.settings["has_gif"] = False
    playlist.has_image = False

    playlist.images = playlistlib.get_first_4_images(trackhashes=playlist.trackhashes)
    playlist._last_updated = date_string_to_time_passed(playlist.last_updated)

    return {"playlist": playlist}, 200


@api.delete("/<playlistid>/delete", methods=["DELETE"])
def remove_playlist(path: PlaylistIDPath):
    """
    Delete playlist
    """
    PlaylistTable.remove_one(path.playlistid)
    playlistlib.cleanup_playlist_images()
    return {"msg": "Done"}, 200


class RemoveTracksFromPlaylistBody(BaseModel):
    tracks: list[dict] = Field(..., description="A list of trackhashes to remove")


@api.post("/<playlistid>/remove-tracks")
def remove_tracks_from_playlist(
    path: PlaylistIDPath, body: RemoveTracksFromPlaylistBody
):
    """
    Remove track from playlist
    """
    # A track looks like this:
    # {
    #    trackhash: str;
    #    index: int;
    # }

    PlaylistTable.remove_from_playlist(path.playlistid, body.tracks)

    return {"msg": "Done"}, 200


class SavePlaylistAsItemBody(BaseModel):
    itemtype: str = Field(..., description="The type of item", example="tracks")
    playlist_name: str = Field(..., description="The name of the playlist")
    itemhash: str = Field(..., description="The hash of the item to save")
    sortoptions: dict = Field(
        default=dict(),
        description="The sort options for the tracks",
    )


@api.post("/save-item")
def save_item_as_playlist(body: SavePlaylistAsItemBody):
    """
    Save as playlist

    Saves a track, album, artist or folder as a playlist
    """
    itemtype = body.itemtype
    playlist_name = body.playlist_name
    itemhash = body.itemhash
    sortoptions = body.sortoptions

    if PlaylistTable.check_exists_by_name(playlist_name):
        return {"error": "Playlist already exists"}, 409

    if itemtype == "tracks":
        trackhashes = itemhash.split(",")
    elif itemtype == "folder":
        trackhashes = get_path_trackhashes(
            itemhash,
            sortoptions.get("tracksortby") or "default",
            sortoptions.get("tracksortreverse") or False,
        )
    elif itemtype == "album":
        trackhashes = get_album_trackhashes(itemhash)
    elif itemtype == "artist":
        trackhashes = get_artist_trackhashes(itemhash)
    else:
        trackhashes = []

    if len(trackhashes) == 0:
        return {"error": "No tracks founds"}, 404

    image = (
        itemhash + ".webp" if itemtype != "folder" and itemtype != "tracks" else None
    )

    playlist = insert_playlist(playlist_name, image)

    if playlist is None:
        return {"error": "Playlist could not be created"}, 500

    # save image
    if itemtype != "folder" and itemtype != "tracks":
        filename = itemhash + ".webp"

        base_path = (
            Paths().lg_artist_img_path
            if itemtype == "artist"
            else Paths().lg_thumb_path
        )
        img_path = pathlib.Path(base_path / filename)

        if img_path.exists():
            img = Image.open(img_path)
            playlistlib.save_p_image(
                img, str(playlist.id), "image/webp", filename=filename
            )

    PlaylistTable.append_to_playlist(playlist.id, trackhashes)
    playlist.count = len(trackhashes)

    images = playlistlib.get_first_4_images(trackhashes=trackhashes)
    playlist.images = [img["image"] for img in images]

    return {"playlist": playlist}, 201
