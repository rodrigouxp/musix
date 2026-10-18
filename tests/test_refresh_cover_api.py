from pathlib import Path
from types import SimpleNamespace

import pytest
from flask_openapi3 import OpenAPI
from PIL import Image

from swingmusic.api import album as album_api
from swingmusic.api import auth as auth_api
from swingmusic.api import imgserver
from swingmusic.store.albums import AlbumStore

ALBUMHASH = "bfe300e966abcdef"


def _make_paths(tmp_path: Path) -> SimpleNamespace:
    thumbs = tmp_path / "thumbnails"
    paths = SimpleNamespace(
        lg_thumb_path=thumbs / "large",
        sm_thumb_path=thumbs / "small",
        xsm_thumb_path=thumbs / "xsmall",
        md_thumb_path=thumbs / "medium",
        og_thumb_path=thumbs / "original",
    )
    for folder in (
        paths.lg_thumb_path,
        paths.sm_thumb_path,
        paths.xsm_thumb_path,
        paths.md_thumb_path,
        paths.og_thumb_path,
    ):
        folder.mkdir(parents=True)
    return paths


class FakeTrack:
    def __init__(self, folder: Path):
        self.albumhash = ALBUMHASH
        self.folder = str(folder)
        self.filepath = str(folder / "song.mp3")


@pytest.fixture
def client(tmp_path, monkeypatch):
    paths = _make_paths(tmp_path)
    monkeypatch.setattr(album_api, "Paths", lambda: paths)
    monkeypatch.setattr(imgserver, "Paths", lambda: paths)
    monkeypatch.setattr(auth_api, "current_user", {"roles": ["admin"]})

    app = OpenAPI(__name__)
    app.register_api(album_api.api)
    app.register_api(imgserver.api)

    return app.test_client(), paths


def test_refresh_cover_unknown_album_is_404(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(AlbumStore, "get_album_tracks", classmethod(lambda cls, h: []))

    res = http.post(f"/album/{ALBUMHASH}/refresh-cover")

    assert res.status_code == 404


def test_refresh_cover_builds_thumbs_from_folder_cover(client, monkeypatch, tmp_path):
    http, paths = client
    folder = tmp_path / "album"
    folder.mkdir()
    Image.new("RGB", (64, 64), (255, 0, 0)).save(folder / "cover.jpg")

    monkeypatch.setattr(
        AlbumStore,
        "get_album_tracks",
        classmethod(lambda cls, h: [FakeTrack(folder)]),
    )

    res = http.post(f"/album/{ALBUMHASH}/refresh-cover")

    assert res.status_code == 200
    assert res.get_json() == {"ok": True, "has_cover": True}
    assert (paths.og_thumb_path / f"{ALBUMHASH}.webp").exists()
    assert (paths.sm_thumb_path / f"{ALBUMHASH}.webp").exists()


def test_refresh_cover_replaces_a_stale_thumb(client, monkeypatch, tmp_path):
    http, paths = client
    folder = tmp_path / "album"
    folder.mkdir()
    cover = folder / "cover.jpg"
    Image.new("RGB", (64, 64), (255, 0, 0)).save(cover)
    monkeypatch.setattr(
        AlbumStore,
        "get_album_tracks",
        classmethod(lambda cls, h: [FakeTrack(folder)]),
    )

    http.post(f"/album/{ALBUMHASH}/refresh-cover")
    Image.new("RGB", (64, 64), (0, 0, 255)).save(cover)
    http.post(f"/album/{ALBUMHASH}/refresh-cover")

    with Image.open(paths.og_thumb_path / f"{ALBUMHASH}.webp") as img:
        r, g, b = img.convert("RGB").getpixel((10, 10))
    assert b > r


def test_refresh_cover_requires_admin(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(auth_api, "current_user", {"roles": []})

    res = http.post(f"/album/{ALBUMHASH}/refresh-cover")

    assert res.status_code == 403


def test_thumbnail_responses_are_revalidated(client):
    http, paths = client
    Image.new("RGB", (8, 8)).save(paths.lg_thumb_path / f"{ALBUMHASH}.webp", "webp")

    res = http.get(f"/img/thumbnail/{ALBUMHASH}.webp")

    assert res.status_code == 200
    assert res.headers["Cache-Control"] == "no-cache"
