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
