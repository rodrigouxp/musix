"""
This module combines all API blueprints into a single Flask app instance.
"""

from musix.api import (
    album,
    artist,
    collections,
    colors,
    favorites,
    folder,
    imgserver,
    playlist,
    search,
    settings,
    lyrics,
    plugins,
    scrobble,
    home,
    getall,
    auth,
    stream,
    track,
    backup_and_restore,
)

from musix.api.plugins import lyrics as lyrics_plugin
from musix.api.sse import api as events

__all__ = [
    "album", "artist", "collections", "colors", "favorites", "folder", "imgserver", "playlist", "search", "settings",
    "lyrics", "plugins", "scrobble", "home", "getall", "auth", "stream", "track", "backup_and_restore", "events",

    "lyrics_plugin",
]
