"""
This file contains all global variables.
All Variables should be read only after an initial set.

Contains default configs
"""

import multiprocessing
import pathlib
import shutil
import sys
import zipfile
from pathlib import Path
import os
import logging
from importlib import metadata, resources as imres

from musix.utils import classproperty


log = logging.getLogger(__name__)

# # # # # # # # #
#  Meta-classes  #
# # # # # # # # #


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in Singleton._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)

        return cls._instances[cls]


class AssetHandler:
    """
    Handles all assets configuration
    """

    @staticmethod
    def copy_assets_dir():
        """
        Copies assets to the app directory.
        """

        assets_source = imres.files("musix") / "assets"
        assets_path = Paths().assets_path
        # INFO: this only works for wheels and source
        # TODO: Handle this for pyinstaller builds

        if assets_path.exists():
            # no need to copy what's already copied?
            return

        if assets_source.exists():
            shutil.copytree(
                Path(assets_source),
                assets_path,
                ignore=shutil.ignore_patterns(
                    "*.pyc",
                ),
                copy_function=shutil.copy2,
                dirs_exist_ok=True,
            )
        else:
            log.error(f"Assets dir could not be found: {assets_source.as_posix()}")

    @staticmethod
    def extract_default_client(path: Path) -> bool:
        """
        Extracts the default client which is bundled with the wheel
        into the musix client folder.
        """
        # INFO: Locate the client.zip file using imres, extract it to the musix client folder
        client_zip_path = imres.files("musix") / "client.zip"
        if not client_zip_path.exists():
            # INFO: if client path contains an index.html file, return true
            if (path / "index.html").exists():
                return True

            return False

        with zipfile.ZipFile(client_zip_path, "r") as zip_ref:
            zip_ref.extractall(path)

        return True

    @classmethod
    def ensure_client_matches_app_version(cls):
        """
        Verify the extracted client's version matches the app version. When
        they diverge (e.g. after upgrading the app), refresh the client from
        the bundled client.zip.

        Skipped when the client was given explicitly (``--client`` or
        ``MUSIX_CLIENT_DIR``): that folder belongs to the user and is never
        touched. Also skipped for dev builds (Metadata.version == "0.0.0")
        and when there is no bundled client to refresh from, so a working
        client is never deleted without a replacement.
        """
        app_version = Metadata.version

        if app_version == "0.0.0" or Paths().client_is_explicit:
            return

        client_path = Paths().client_path
        version_file = client_path / "version.txt"

        def read_client_version() -> str | None:
            if not version_file.exists():
                return None
            try:
                return version_file.read_text().strip() or None
            except OSError:
                return None

        client_version = read_client_version()
        if client_version == app_version:
            return

        if not (imres.files("musix") / "client.zip").exists():
            log.warning(
                "Client version %r does not match app version %r, but there is "
                "no bundled client to refresh from. Keeping the client on disk.",
                client_version,
                app_version,
            )
            return

        log.info(
            "Client version %r does not match app version %r, refreshing client...",
            client_version,
            app_version,
        )

        # Reset the client dir so the new extraction doesn't merge with
        # stale files left by the previous client.
        try:
            if client_path.exists():
                shutil.rmtree(client_path)
            client_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.error("Could not reset client directory %s: %s", client_path, e)
            return

        cls.extract_default_client(Paths().config_dir)

        if read_client_version() == app_version:
            log.info("Client refreshed from bundle to %s.", app_version)
        else:
            log.warning(
                "The bundled client does not match app version %s.", app_version
            )

    @classmethod
    def setup_default_client(cls):
        """
        Runs on startup to ensure the default client is present.
        """

        extracted = True
        client_path = Paths().client_path

        if not client_path.exists() or not (client_path / "index.html").exists():
            extracted = cls.extract_default_client(Paths().config_dir)

        if not extracted or not (client_path / "index.html").exists():
            # INFO: the web client is never downloaded from the internet
            log.error(
                "Web client not found in %s. Pass one with --client or MUSIX_CLIENT_DIR.",
                client_path,
            )

        # Refresh the bundled client if it is outdated. No-op for an explicit
        # client and for dev builds.
        cls.ensure_client_matches_app_version()


class Paths(metaclass=Singleton):
    """
    This class stores all paths for ``musix``s config.
    * Configs
    * DBs
    * Assets
    * Cache

    This class is a singleton.
    You cannot change the config path later.
    """

    config_parent: Path = Path.home().resolve()
    """
    The parent directory of the config folder.
    This is the directory where the config folder is located.
    """

    client_is_explicit: bool = False
    """
    True when the client folder came from ``--client`` or ``MUSIX_CLIENT_DIR``.
    An explicit client is never checked against the app version or replaced.
    """

    USER_HOME_DIR = Path.home().resolve()
    APP_DB_NAME = "musix.db"
    USER_DATA_DB_NAME = "userdata.db"

    def __init__(
        self,
        config_parent: Path | None = None,
        client_dir: Path | None = None,
    ):
        """
        Create config-folder structure and check permissions.
        Copy all assets if needed.

        If `config` or `client` are provided, they are used exclusively.
        In case of multithread, the environment vars are used.
        The detailed decision can be viewed in :func:`default_base_path`.

        :param self: Own object
        :param config: Parent path of ``musix``s config path.
        :param client: Path to static Web client folder.c
        :param fallback: Path to fallback client folder.
        """

        """
        Returns the XDG_CONFIG_HOME environment variable if it exists, otherwise
        returns the default config directory. If none of those exist, returns the
        user's home directory.
        """

        if config_parent is not None:
            self.config_parent = config_parent.resolve()
        else:
            self.config_parent = Paths.get_default_config_parent_dir()

        if multiprocessing.current_process().name == "MainProcess":
            # INFO: Move data from the old Swing Music names, before anything
            # creates the new folders or opens the database
            from musix.utils.legacy_names import migrate_legacy_names

            migrate_legacy_names(self.config_parent, self.USER_HOME_DIR)

            # INFO: Setup client path
            env_client_dir = os.environ.get("MUSIX_CLIENT_DIR")
            self.client_is_explicit = client_dir is not None or env_client_dir is not None
            if client_dir is not None:
                self.client_path = client_dir.resolve()
            elif env_client_dir is not None:
                self.client_path = Path(env_client_dir).resolve()
            else:
                self.client_path = self.config_dir / "client"

            # Path copy only on MainProcess
            if not self.config_dir.exists():
                self.config_dir.mkdir(parents=True)

            # TODO: find a platform independent way to access module globals like `Paths`
            # TODO: move this into multithreading management class
            os.environ["MUSIX_CONFIG_DIR"] = (
                self.config_parent.resolve().as_posix()
            )
            os.environ["MUSIX_CLIENT_DIR"] = self.client_path.resolve().as_posix()

            self.setup_config_dirs()
        else:
            # Worker process: read client path from environment variable set by main process
            env_client_dir = os.environ.get("MUSIX_CLIENT_DIR")
            self.client_is_explicit = env_client_dir is not None
            if env_client_dir is not None:
                self.client_path = Path(env_client_dir).resolve()
            else:
                self.client_path = self.config_dir / "client"

    @classmethod
    def get_default_config_parent_dir(cls) -> pathlib.Path:
        """
        Determines the default config path in the following order:

        1. Env:``MUSIX_CONFIG_DIR``
        2. Env:``xdg_config_home``
        3. <User Home>/.config
        4. <User Home>

        :return: First valid path
        """

        config_dir_from_env = os.environ.get("MUSIX_CONFIG_DIR")
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME")

        if config_dir_from_env is not None:
            return pathlib.Path(config_dir_from_env)

        if xdg_config_home is not None:
            return pathlib.Path(xdg_config_home)

        fallback_dir = pathlib.Path.home() / ".config"
        if fallback_dir.exists():
            return fallback_dir

        return pathlib.Path.home()

    def setup_config_dirs(self):
        """
        Create the config/cache folder structure.

        base folder
        └───`musix` or `.musix`
            ├───images
            │   ├───artists
            │   │   ├───large
            │   │   ├───medium
            │   │   └───small
            │   ├───playlists
            │   └───thumbnails
            │       ├───large
            │       ├───medium
            │       ├───small
            │       └───xsmall
            └───plugins
                └───lyrics
        """

        # all dirs relative to `musix` config dir
        dirs = [
            "",  # `musix` or `.musix`
            "plugins/lyrics",
            "images/playlists",
            "images/thumbnails/small",
            "images/thumbnails/large",
            "images/thumbnails/medium",
            "images/thumbnails/xsmall",
            "images/thumbnails/original",
            "images/artists/medium",
            "images/artists/small",
            "images/artists/large",
        ]

        for folder in dirs:
            path = self.config_parent / self.config_folder_name / folder
            if not path.exists():
                path.mkdir(parents=True)
                path.chmod(mode=0o755)

        # Empty files to create
        empty_files = [
            # artist split ignore list
            self.config_dir
            / "data"
            / "artist_split_ignore.txt"  # TODO: use USERCONFIG -> circular import error
        ]

        for file in empty_files:
            if file.is_dir():
                file.rmdir()

            if not file.exists():
                file.parent.mkdir(parents=True, exist_ok=True)
                file.touch()

    @property
    def config_folder_name(self) -> str:
        """
        return the name of the musix config folder.

        When the base path is the same as the home dir,
        it returns `.musix` else `musix`
        """
        if self.config_parent == self.USER_HOME_DIR:
            return ".musix"
        else:
            return "musix"

    @property
    def config_dir(self) -> Path:
        return self.config_parent / self.config_folder_name

    @property
    def img_path(self) -> Path:
        return self.config_dir / "images"

    # ARTISTS
    @property
    def artist_img_path(self) -> Path:
        return self.img_path / "artists"

    @property
    def sm_artist_img_path(self) -> Path:
        return self.artist_img_path / "small"

    @property
    def md_artist_img_path(self) -> pathlib.Path:
        return self.artist_img_path / "medium"

    @property
    def lg_artist_img_path(self) -> pathlib.Path:
        return self.artist_img_path / "large"

    # TRACK THUMBNAILS
    @property
    def thumbs_path(self) -> pathlib.Path:
        return self.img_path / "thumbnails"

    @property
    def sm_thumb_path(self) -> pathlib.Path:
        return self.thumbs_path / "small"

    @property
    def xsm_thumb_path(self) -> pathlib.Path:
        return self.thumbs_path / "xsmall"

    @property
    def md_thumb_path(self) -> pathlib.Path:
        return self.thumbs_path / "medium"

    @property
    def lg_thumb_path(self) -> pathlib.Path:
        return self.thumbs_path / "large"

    @property
    def og_thumb_path(self) -> pathlib.Path:
        return self.thumbs_path / "original"

    # OTHERS
    @property
    def playlist_img_path(self) -> pathlib.Path:
        return self.img_path / "playlists"

    @property
    def assets_path(self) -> pathlib.Path:
        return self.config_dir / "assets"

    @property
    def plugins_path(self) -> pathlib.Path:
        return self.config_dir / "plugins"

    @property
    def lyrics_plugins_path(self) -> pathlib.Path:
        return self.plugins_path / "lyrics"

    @property
    def config_file_path(self) -> pathlib.Path:
        return self.config_dir / "settings.json"

    @property
    def image_cache_path(self) -> pathlib.Path:
        return self.img_path / "cache"

    @property
    def app_db_path(self):
        return Paths().config_dir / self.APP_DB_NAME

    @property
    def userdata_db_path(self):
        return Paths().config_dir / self.USER_DATA_DB_NAME

    @property
    def json_config_path(self):
        return Paths().config_dir / "config.json"


class Defaults:
    """
    Contains default values for various settings.

    XSM_THUMB_SIZE: extra small thumbnail size for web client tracklist
    SM_THUMB_SIZE: small thumbnail size for android client tracklist
    MD_THUMB_SIZE: medium thumbnail size for web client album cards
    LG_THUMB_SIZE: large thumbnail size for web client now playing album art

    NOTE: LG_ARTIST_IMG_SIZE is undefined to save the images in their original size (500px)
    """

    XSM_THUMB_SIZE = 64
    SM_THUMB_SIZE = 96
    MD_THUMB_SIZE = 256
    LG_THUMB_SIZE = 512
    OG_THUMB_SIZE = 1200

    SM_ARTIST_IMG_SIZE = 128
    MD_ARTIST_IMG_SIZE = 256

    HASH_LENGTH = 16
    API_ALBUMHASH = "bfe300e966"
    API_ARTISTHASH = "cae59f1fc5"
    API_TRACKHASH = "0853280a12"
    API_ALBUMNAME = "The Goat"
    API_ARTISTNAME = "Polo G"
    API_TRACKNAME = "Martin & Gina"
    API_CARD_LIMIT = 6


class TCOLOR:
    """
    Terminal colors
    """

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    YELLOW = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    # credits: https://stackoverflow.com/a/287944


class Metadata:
    """
    Contains metadata for the application.
    """

    @classproperty
    def version(self) -> str:
        version = metadata.version("musix")

        if version == "0.0.0":
            # In frozen builds (PyInstaller) and Docker, setuptools-scm can't
            # detect the git tag so the version falls back to 0.0.0. Read the
            # version.txt shipped alongside the binary / in the repo root.
            # Try multiple locations: next to the executable (PyInstaller),
            # repo root (dev), and CWD (legacy).
            candidates = [
                Path("version.txt").resolve(),
                Path(sys.executable).parent / "version.txt",
                Path(__file__).resolve().parent.parent.parent / "version.txt",
            ]
            if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
                candidates.insert(0, Path(sys._MEIPASS) / "version.txt")

            for p in candidates:
                if p.is_file():
                    return p.read_text().strip()

            return "0.0.0"

        return version
