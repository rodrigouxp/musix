import shutil
import subprocess
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

from musix.db import create_all_tables
from musix.db.engine import DbEngine


@pytest.fixture
def database(tmp_path, monkeypatch):
    """
    An empty sqlite database with every table, in a temporary folder.
    """
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setattr(DbEngine, "_engine", engine)
    create_all_tables()
    yield engine
    engine.dispose()


def find_ffmpeg() -> str | None:
    path = shutil.which("ffmpeg")

    if path:
        return path

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


FFMPEG_CODECS = {
    "mp3": ["-c:a", "libmp3lame"],
    "flac": ["-c:a", "flac"],
    "m4a": ["-c:a", "aac"],
    "ogg": ["-c:a", "libvorbis"],
    "opus": ["-c:a", "libopus"],
}


@pytest.fixture
def make_audio(tmp_path):
    """
    Makes a short audio file with ffmpeg. Skips the test if ffmpeg is not there.
    ``make_audio("flac", title="x", artist="y")`` gives the Path.
    """
    ffmpeg = find_ffmpeg()

    if ffmpeg is None:
        pytest.skip("ffmpeg is not available")

    counter = {"n": 0}

    def make(fmt: str, name: str | None = None, **tags: str):
        counter["n"] += 1
        path = tmp_path / "music" / (name or f"song{counter['n']}.{fmt}")
        path.parent.mkdir(parents=True, exist_ok=True)
        command = [ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1"]
        command += FFMPEG_CODECS[fmt]

        for key, value in tags.items():
            command += ["-metadata", f"{key}={value}"]

        result = subprocess.run([*command, str(path)], capture_output=True)

        if result.returncode != 0:
            pytest.skip(f"ffmpeg can not make {fmt}: {result.stderr.decode(errors='replace')[:100]}")

        return path

    return make


@pytest.fixture
def config():
    """
    The separators and the split exceptions the app has by default.
    """
    return SimpleNamespace(
        artistSeparators={";", "/"},
        artistSplitIgnoreList={"AC/DC", "Earth, Wind & Fire"},
    )


@pytest.fixture
def app_env(tmp_path, monkeypatch, database):
    """
    Folders and settings for code that uses ``Paths()`` and ``UserConfig()``,
    all inside the temporary folder. The real config of the user is never read.
    """
    from musix.config import UserConfig
    from musix.settings import Paths, Singleton

    root = tmp_path / "config"
    thumbs = root / "images" / "thumbnails"
    artists = root / "images" / "artists"
    paths = SimpleNamespace(
        config_dir=root,
        img_path=root / "images",
        thumbs_path=thumbs,
        lg_thumb_path=thumbs / "large",
        sm_thumb_path=thumbs / "small",
        xsm_thumb_path=thumbs / "xsmall",
        md_thumb_path=thumbs / "medium",
        og_thumb_path=thumbs / "original",
        artist_img_path=artists,
        sm_artist_img_path=artists / "small",
        md_artist_img_path=artists / "medium",
        lg_artist_img_path=artists / "large",
        USER_HOME_DIR=tmp_path,
        playlist_img_path=root / "images" / "playlists",
    )
    for folder in (
        paths.lg_thumb_path,
        paths.sm_thumb_path,
        paths.xsm_thumb_path,
        paths.md_thumb_path,
        paths.og_thumb_path,
        paths.sm_artist_img_path,
        paths.md_artist_img_path,
        paths.lg_artist_img_path,
    ):
        folder.mkdir(parents=True)

    config = SimpleNamespace(
        artistSeparators={";", "/"},
        artistSplitIgnoreList={"AC/DC"},
        genreSeparators={"/", ";", "&"},
        extractFeaturedArtists=True,
        removeProdBy=True,
        removeRemasterInfo=True,
        cleanAlbumTitle=True,
        mergeAlbums=False,
        rootDirs=[str(tmp_path / "music")],
    )
    monkeypatch.setitem(Singleton._instances, Paths, paths)
    monkeypatch.setitem(Singleton._instances, UserConfig, config)
    return SimpleNamespace(paths=paths, config=config, root=tmp_path)
