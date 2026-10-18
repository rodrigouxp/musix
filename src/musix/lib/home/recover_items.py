from musix.db.userdata import FavoritesTable, PlaylistTable
from musix.lib.home.recentlyadded import get_recently_added_playlist
from musix.lib.home.recentlyplayed import get_recently_played_playlist
from musix.lib.playlistlib import get_first_4_images
from musix.serializers.album import album_serializer
from musix.serializers.artist import serialize_for_card
from musix.serializers.playlist import serialize_for_card as serialize_playlist
from musix.serializers.track import serialize_track
from musix.store.albums import AlbumStore
from musix.store.artists import ArtistStore
from musix.store.folder import FolderStore
from musix.store.tracks import TrackStore
from musix.utils.dates import timestamp_to_time_passed


def recover_items(items: list[dict]):
    custom_playlists = [
        {"name": "recentlyadded", "handler": get_recently_added_playlist},
        {"name": "recentlyplayed", "handler": get_recently_played_playlist},
    ]
    recovered = []

    for item in items:
        if not isinstance(item, dict):
            # Skip None / malformed entries (e.g. already-persisted bad data)
            # so a single bad item can't crash the whole homepage.
            continue

        recovered_item = None

        if item["type"] == "album":
            album = AlbumStore.get_album_by_hash(item["hash"])
            if album is None:
                continue

            album = album_serializer(
                album,
                to_remove={
                    "genres",
                    "count",
                    "duration",
                    "albumartists_hashes",
                    "og_title",
                },
            )

            recovered_item = {
                "type": "album",
                "item": album,
            }
        elif item["type"] == "artist":
            artist = ArtistStore.get_artist_by_hash(item["hash"])
            if artist is None:
                continue

            recovered_item = {
                "type": "artist",
                "item": serialize_for_card(artist),
            }
        elif item["type"] == "folder":
            count = FolderStore.count_tracks_containing_paths([item["hash"]])

            recovered_item = {
                "type": "folder",
                "item": {
                    "path": item["hash"],
                    "count": count[0]["trackcount"],
                },
            }
        elif item["type"] == "playlist":
            if item.get("is_custom"):
                playlist, _ = next(
                    i["handler"]()
                    for i in custom_playlists
                    if i["name"] == item["hash"]
                )
                playlist.images = [i["image"] for i in playlist.images]

                playlist = serialize_playlist(
                    playlist, to_remove={"settings", "duration"}
                )
                recovered_item = {
                    "type": "playlist",
                    "item": playlist,
                }
            else:
                playlist = PlaylistTable.get_by_id(item["hash"])
                if playlist is None:
                    continue

                tracks = TrackStore.get_tracks_by_trackhashes(playlist.trackhashes)
                playlist.clear_lists()

                if not playlist.has_image:
                    images = get_first_4_images(tracks)
                    images = [i["image"] for i in images]
                    playlist.images = images

                recovered_item = {
                    "type": "playlist",
                    "item": serialize_playlist(playlist),
                }
        elif item["type"] == "favorite":
            image = None
            last_trackhash = FavoritesTable.get_last_trackhash()

            if last_trackhash:
                trackhash = last_trackhash.replace("track_", "")
                entry = TrackStore.trackhashmap.get(trackhash)
                if entry:
                    image = entry.tracks[0].image

            recovered_item = {
                "type": "favorite",
                "item": {
                    "count": FavoritesTable.count_tracks(),
                    "image": image,
                },
            }
        elif item["type"] == "track":
            track = TrackStore.trackhashmap.get(item["hash"])
            if track is None:
                continue

            recovered_item = {
                "type": "track",
                "item": serialize_track(track.get_best()),
            }

        if recovered_item is not None:
            helptext = item.get("help_text") or item.get("type")
            secondary_text = item.get("secondary_text")

            if "secondary_text" in item:
                secondary_text = item["secondary_text"]
            elif "timestamp" in item:
                try:
                    secondary_text = timestamp_to_time_passed(item["timestamp"])
                except Exception:
                    secondary_text = None

            if helptext:
                recovered_item["item"]["help_text"] = helptext

            if secondary_text:
                recovered_item["item"]["time"] = secondary_text

            recovered.append(recovered_item)

    return recovered
