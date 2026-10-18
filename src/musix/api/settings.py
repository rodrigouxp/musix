import threading
from typing import Any
from flask_openapi3 import Tag
from flask_openapi3 import APIBlueprint

from dataclasses import asdict
from pydantic import BaseModel, Field

from musix.config import UserConfig
from musix.settings import Metadata
from musix.db.userdata import PluginTable
from musix.store.general import GeneralStore

from musix.api.auth import admin_required
from musix.lib.index import index_everything
from musix.lib.populate import ProcessTrackThumbnails
from musix.utils.paths import normalize_paths
from musix.utils.threading import background

# Config keys returned by GET /notsettings
PUBLIC_SETTINGS = (
    "serverId",
    "usersOnLogin",
    "rootDirs",
    "excludeDirs",
    "artistSeparators",
    "artistSplitIgnoreList",
    "genreSeparators",
    "extractFeaturedArtists",
    "removeProdBy",
    "removeRemasterInfo",
    "mergeAlbums",
    "cleanAlbumTitle",
    "showAlbumsAsSingles",
    "enablePeriodicScans",
    "scanInterval",
    "enableWatchdog",
    "showPlaylistsInFolderView",
    "enablePlugins",
    "lastfmApiKey",
    "lastfmApiSecret",
    "artistArticleAwareSorting",
    "artistSortingArticles",
)

bp_tag = Tag(name="Settings", description="Customize stuff")
api = APIBlueprint("settings", __name__, url_prefix="/notsettings", abp_tags=[bp_tag])


def get_child_dirs(parent: str, children: list[str]):
    """Returns child directories in a list, given a parent directory"""

    return [_dir for _dir in children if _dir.startswith(parent) and _dir != parent]


class AddRootDirsBody(BaseModel):
    new_dirs: list[str] = Field(
        description="The new directories to add",
        example=["/home/user/Music", "/home/user/Downloads"],
    )
    removed: list[str] = Field(
        description="The directories to remove",
        example=["/home/user/Downloads"],
    )


@api.post("/add-root-dirs")
@admin_required()
def add_root_dirs(body: AddRootDirsBody):
    """
    Add custom root directories to the database.
    """
    new_dirs = body.new_dirs
    removed_dirs = body.removed

    config = UserConfig()
    db_dirs = [*config.rootDirs]

    for dir in removed_dirs:
        try:
            db_dirs.remove(dir)
        except ValueError:
            pass

    final_paths = [*db_dirs, *new_dirs]
    config.rootDirs = normalize_paths(final_paths)
    config.save()

    index_everything()
    GeneralStore.root_dirs_set = True

    return {"root_dirs": config.rootDirs}


@api.get("/get-root-dirs")
def get_root_dirs():
    """
    Get root directories
    """
    return {"dirs": UserConfig().rootDirs}


@api.get("")
def get_all_settings():
    """
    Get all settings
    """
    full_config = asdict(UserConfig())
    config = {key: full_config[key] for key in PUBLIC_SETTINGS}

    # Convert sets to lists for JSON serialization
    for key, value in config.items():
        if isinstance(value, set):
            config[key] = sorted(list(value))

    config["plugins"] = [p for p in PluginTable.get_all()]
    config["version"] = Metadata.version

    if config["version"] == "0.0.0":
        # fallback to version.txt (useful for docker builds)
        config["version"] = open("version.txt", "r").read().strip()

    return config


class SetSettingBody(BaseModel):
    key: str = Field(
        description="The setting key",
        example="artist_separators",
    )
    value: Any = Field(
        description="The setting value",
        example=",",
    )

@api.get("/trigger-scan")
def trigger_scan_get():
    """
    Triggers scan for new music (deprecated, use /trigger-scan POST instead).
    
    For already indexed files, will only re-scan changed files.
    """
    index_everything(full_scan=False)
    return {"msg": "Scan triggered!"}

class TriggerScanBody(BaseModel):
    full_scan: bool = Field(
        description="Whether to perform a full scan of the root directories",
        example=False,
    )

@api.post("/trigger-scan")
def trigger_scan(body: TriggerScanBody):
    """
    Triggers scan for new music
    """
    index_everything(full_scan=body.full_scan)
    return {"msg": "Scan triggered!"}


class UpdateConfigBody(BaseModel):
    key: str = Field(
        description="The setting key",
        example="usersOnLogin",
    )
    value: Any = Field(
        description="The setting value",
        example=False,
    )


@api.put("/update")
@admin_required()
def update_config(body: UpdateConfigBody):
    """
    Update the config file
    """
    config = UserConfig()
    if body.key == "artistSeparators":
        body.value = body.value.split(",")

    setattr(config, body.key, body.value)

    # INFO: Rebuild stores when these settings are updated
    reset_stores_lists = {
        "artistSeparators",
        "artistSplitIgnoreList",
        "removeProdBy",
        "removeRemasterInfo",
        "mergeAlbums",
        "cleanAlbumTitle",
        "showAlbumsAsSingles",
    }

    if body.key in reset_stores_lists:
        index_everything()

    return {
        "msg": "Config updated!",
    }


_covers_lock = threading.Lock()


@background
def _refresh_all_covers():
    # one rebuild at a time: a second click while it runs is a no-op
    if not _covers_lock.acquire(blocking=False):
        return

    try:
        ProcessTrackThumbnails(overwrite_track_thumbnails=True)
    finally:
        _covers_lock.release()


@api.post("/refresh-covers")
@admin_required()
def refresh_covers():
    """
    Rebuilds the covers of all albums in the background.
    """
    _refresh_all_covers()
    return {"ok": True}
