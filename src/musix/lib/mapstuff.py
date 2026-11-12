from musix.db.userdata import LibDataTable, FavoritesTable, ScrobbleTable
from musix.lib.playcount import counts_as_play
from musix.store.albums import AlbumStore
from musix.store.artists import ArtistStore
from musix.store.folder import FolderStore
from musix.store.tracks import TrackStore


from typing import Any


def map_trackhash_repairs():
    """
    Repairs trackhash-keyed user data (scrobbles and track favorites) whose
    trackhash no longer resolves — eg. after files were retagged or the
    hashing inputs changed.
    """
    basename_index: dict[str, list[str]] | None = None

    def resolve(filepath: str | None) -> str | None:
        nonlocal basename_index

        if not filepath:
            return None

        trackhash = FolderStore.map.get(filepath)
        if trackhash is not None:
            return trackhash

        if basename_index is None:
            basename_index = {}
            for path in FolderStore.map:
                basename_index.setdefault(path.rsplit("/", 1)[-1], []).append(path)

        candidates = basename_index.get(filepath.rsplit("/", 1)[-1], [])
        if len(candidates) == 1:
            return FolderStore.map.get(candidates[0])

        # ambiguous or missing — leave the entry alone
        return None

    # distinct orphaned trackhash -> stored filepath
    orphans: dict[str, str | None] = {}
    for record in ScrobbleTable.get_all_unfiltered():
        if record.trackhash not in TrackStore.trackhashmap:
            orphans.setdefault(record.trackhash, (record.extra or {}).get("filepath"))

    repaired = 0
    for old, filepath in orphans.items():
        new = resolve(filepath)
        if new is not None:
            ScrobbleTable.update_trackhash(old, new)
            repaired += 1

    fav_orphans: dict[str, str | None] = {}
    for entry in FavoritesTable.get_all():
        if entry.type != "track":
            continue
        if entry.hash not in TrackStore.trackhashmap:
            fav_orphans.setdefault(entry.hash, (entry.extra or {}).get("filepath"))

    for old, filepath in fav_orphans.items():
        new = resolve(filepath)
        if new is not None:
            FavoritesTable.update_track_hash(old, new)
            repaired += 1

    if repaired:
        print(f"Repaired {repaired} user data trackhashes")


def map_scrobble_data():
    """
    Maps scrobble data to the in-memory stores.

    The scrobble data is loaded from the database and grouped by trackhash.
    The album and artist scrobble data (for those tracks) are then incremented based on the data.
    """
    # INFO: The scrobbles of ALL users. This runs at boot and after a scan,
    # outside any request: `ScrobbleTable.get_all` would fall back to the user
    # with id 1 there, while the plays logged at runtime are added to the stores
    # whoever the user is. Reading all of them keeps the two in agreement.
    records = ScrobbleTable.get_all_unfiltered()

    # group records by trackhash
    grouped: dict[str, dict[str, Any]] = {}

    for record in records:
        group = TrackStore.trackhashmap.get(record.trackhash)
        if group is None:
            continue

        # aggregate playcount, playduration and lastplayed
        item = grouped.setdefault(record.trackhash, {})
        item.setdefault("playcount", 0)

        # INFO: a listen that is too short (a skipped track) adds its time but is
        # not a play; this also applies to the scrobbles logged before the rule
        if counts_as_play(record.duration, group.tracks[0].duration):
            item["playcount"] += 1

        item["playduration"] = item.get("playduration", 0) + record.duration
        item["lastplayed"] = max(item.get("lastplayed", 0), record.timestamp)

    # increment playcount, playduration and lastplayed for albums and artists
    for trackhash, data in grouped.items():
        track = TrackStore.trackhashmap.get(trackhash)

        if track is None:
            continue

        track.increment_playcount(
            data["playduration"], data["lastplayed"], data["playcount"]
        )

        album = AlbumStore.albummap.get(track.tracks[0].albumhash)
        if album:
            album.increment_playcount(
                data["playduration"], data["lastplayed"], data["playcount"]
            )

        for artisthash in track.tracks[0].artisthashes:
            artist = ArtistStore.artistmap.get(artisthash)
            if artist:
                artist.increment_playcount(
                    data["playduration"], data["lastplayed"], data["playcount"]
                )


def map_favorites():
    """
    Maps favorites data to the in-memory stores.
    """
    favorites = FavoritesTable.get_all()

    for entry in favorites:
        if entry.type == "album":
            album = AlbumStore.albummap.get(entry.hash)
            if album:
                album.toggle_favorite_user(entry.userid)

        elif entry.type == "artist":
            artist = ArtistStore.artistmap.get(entry.hash)
            if artist:
                artist.toggle_favorite_user(entry.userid)

        elif entry.type == "track":
            track = TrackStore.trackhashmap.get(entry.hash)
            if track:
                track.toggle_favorite_user(entry.userid)


def map_artist_colors():
    colors = LibDataTable.get_all_colors(type="artist")

    for color in colors:
        artist = ArtistStore.artistmap.get(color["itemhash"])

        if artist:
            blurhash: str = (color.get("extra", {}) or {}).get("blurhash", "")
            artist.update_color_info(color["color"], blurhash)


def map_album_colors():
    colors = LibDataTable.get_all_colors(type="album")

    for color in colors:
        album = AlbumStore.albummap.get(color["itemhash"])

        if not album:
            continue

        blurhash: str = (color.get("extra", {}) or {}).get("blurhash", "")
        album.update_color_info(color["color"], blurhash)

        for trackhash in album.trackhashes:
            group = TrackStore.trackhashmap.get(trackhash)

            if not group:
                continue

            group.update_color_info(color["color"], blurhash)
