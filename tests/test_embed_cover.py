import hashlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask_openapi3 import OpenAPI
from PIL import Image

from musix.api import album as album_api
from musix.api import auth as auth_api
from musix.lib import tagwriter
from musix.lib.tagwriter import read_tags
from musix.store.albums import AlbumStore
from musix.store.tracks import TrackStore

ALBUMHASH = "bfe300e966abcdef"


def jpeg_bytes(color=(200, 30, 30)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 64), color).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch, config):
    thumbs = tmp_path / "thumbnails"
    paths = SimpleNamespace(
        lg_thumb_path=thumbs / "large",
        sm_thumb_path=thumbs / "small",
        xsm_thumb_path=thumbs / "xsmall",
        md_thumb_path=thumbs / "medium",
        og_thumb_path=thumbs / "original",
    )
    monkeypatch.setattr(album_api, "Paths", lambda: paths)
    monkeypatch.setattr(auth_api, "current_user", {"roles": ["admin"]})
    monkeypatch.setattr(tagwriter, "_default_config", lambda: config)

    app = OpenAPI(__name__)
    app.register_api(album_api.api)
    return app.test_client(), paths


def put_album_in_store(monkeypatch, files: list[Path], albumhash: str = ALBUMHASH):
    tracks = [
        SimpleNamespace(
            albumhash=albumhash,
            trackhash=f"th{i}",
            filepath=str(f),
            folder=str(f.parent),
        )
        for i, f in enumerate(files)
    ]
    monkeypatch.setattr(
        AlbumStore,
        "albummap",
        {albumhash: SimpleNamespace(trackhashes={t.trackhash for t in tracks})},
    )
    monkeypatch.setattr(
        TrackStore,
        "trackhashmap",
        {t.trackhash: SimpleNamespace(tracks=[t]) for t in tracks},
    )
    return tracks


def test_embeds_the_folder_cover_in_mp3_and_flac(client, make_audio, monkeypatch):
    http, paths = client
    mp3 = make_audio("mp3", title="One", artist="A", album="B", comment="keep")
    flac = make_audio("flac", title="Two", artist="A", album="B")
    image = jpeg_bytes()
    (mp3.parent / "cover.jpg").write_bytes(image)
    before_files = sorted(p.name for p in mp3.parent.iterdir())
    before_tags = read_tags(mp3).others
    put_album_in_store(monkeypatch, [mp3, flac])

    res = http.post(f"/album/{ALBUMHASH}/embed-cover")

    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["tracks_ok"] == 2
    assert body["tracks_failed"] == []
    md5 = hashlib.md5(image).hexdigest()
    assert read_tags(mp3).covers == [md5]
    assert read_tags(flac).covers == [md5]
    assert read_tags(mp3).others == before_tags
    assert read_tags(mp3).title == "One"
    # nothing was created or renamed in the folder
    assert sorted(p.name for p in mp3.parent.iterdir()) == before_files
    # and the thumbnails were rebuilt
    assert (paths.og_thumb_path / f"{ALBUMHASH}.webp").exists()


def test_a_failure_in_one_track_does_not_stop_the_others(client, make_audio, tmp_path, monkeypatch):
    http, _ = client
    good = make_audio("flac", title="One", artist="A", album="B")
    wav = good.parent / "bad.wav"
    wav.write_bytes(b"RIFF....WAVEfmt ")
    also_good = make_audio("mp3", title="Two", artist="A", album="B")
    (good.parent / "cover.jpg").write_bytes(jpeg_bytes())
    wav_before = wav.read_bytes()
    put_album_in_store(monkeypatch, [good, wav, also_good])

    res = http.post(f"/album/{ALBUMHASH}/embed-cover")

    body = res.get_json()
    assert res.status_code == 200
    assert body["tracks_ok"] == 2
    assert body["tracks_failed"] == [str(wav)]
    assert "unsupported format" in body["errors"][str(wav)]
    assert wav.read_bytes() == wav_before
    assert len(read_tags(good).covers) == 1
    assert len(read_tags(also_good).covers) == 1


def test_the_original_is_intact_when_the_write_fails(client, make_audio, monkeypatch):
    http, _ = client
    path = make_audio("flac", title="One", artist="A", album="B")
    (path.parent / "cover.jpg").write_bytes(jpeg_bytes())
    original = path.read_bytes()
    put_album_in_store(monkeypatch, [path])

    def no_save(self):
        raise OSError("disk full")

    monkeypatch.setattr(tagwriter._VorbisAdapter, "save", no_save)

    res = http.post(f"/album/{ALBUMHASH}/embed-cover")

    assert res.get_json()["tracks_failed"] == [str(path)]
    assert path.read_bytes() == original
    assert sorted(p.name for p in path.parent.iterdir()) == ["cover.jpg", path.name]


def test_tracks_in_different_folders(client, make_audio, tmp_path, monkeypatch):
    http, _ = client
    one = make_audio("mp3", name="cd1/one.mp3", title="One", artist="A", album="B")
    two = make_audio("flac", name="cd2/two.flac", title="Two", artist="A", album="B")
    (one.parent / "cover.jpg").write_bytes(jpeg_bytes())
    put_album_in_store(monkeypatch, [one, two])

    res = http.post(f"/album/{ALBUMHASH}/embed-cover")

    assert res.get_json()["tracks_ok"] == 2
    assert read_tags(one).covers == read_tags(two).covers


def test_a_webp_cover_is_saved_as_png(client, make_audio, monkeypatch):
    http, _ = client
    path = make_audio("mp3", title="One", artist="A", album="B")
    Image.new("RGB", (64, 64), (0, 0, 255)).save(path.parent / "cover.webp")
    put_album_in_store(monkeypatch, [path])

    res = http.post(f"/album/{ALBUMHASH}/embed-cover")

    assert res.get_json()["tracks_ok"] == 1
    from tinytag import TinyTag

    image = TinyTag.get(path, image=True).images.any
    assert image.mime_type == "image/png"


def test_no_cover_in_the_folder_is_400(client, make_audio, monkeypatch):
    http, _ = client
    path = make_audio("flac", title="One", artist="A", album="B")
    original = path.read_bytes()
    put_album_in_store(monkeypatch, [path])

    res = http.post(f"/album/{ALBUMHASH}/embed-cover")

    assert res.status_code == 400
    assert "no cover" in res.get_json()["error"]
    assert path.read_bytes() == original


def test_unknown_album_is_404(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(AlbumStore, "albummap", {})

    assert http.post(f"/album/{ALBUMHASH}/embed-cover").status_code == 404


def test_embed_requires_admin(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(auth_api, "current_user", {"roles": []})

    assert http.post(f"/album/{ALBUMHASH}/embed-cover").status_code == 403
