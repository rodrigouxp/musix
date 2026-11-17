from types import SimpleNamespace

import pytest
from flask_openapi3 import OpenAPI

from musix.api import imgserver


@pytest.fixture
def http(tmp_path, monkeypatch):
    folders = {name: tmp_path / name for name in ("lg", "og", "sm", "xsm", "md")}

    for folder in folders.values():
        folder.mkdir()

    monkeypatch.setattr(
        imgserver,
        "Paths",
        lambda: SimpleNamespace(
            lg_thumb_path=folders["lg"],
            og_thumb_path=folders["og"],
            sm_thumb_path=folders["sm"],
            xsm_thumb_path=folders["xsm"],
            md_thumb_path=folders["md"],
            image_cache_path=tmp_path / "cache",
            assets_path=tmp_path,
        ),
    )

    app = OpenAPI(__name__)
    app.register_api(imgserver.api)
    client = app.test_client()
    client.folders = folders
    return client


def test_the_original_size_is_the_file_of_the_original_folder(http):
    (http.folders["og"] / "a.webp").write_bytes(b"original")
    (http.folders["lg"] / "a.webp").write_bytes(b"large")

    assert http.get("/img/thumbnail/original/a.webp").data == b"original"


def test_a_cover_without_an_original_file_gets_the_large_one(http):
    (http.folders["lg"] / "b.webp").write_bytes(b"large")

    res = http.get("/img/thumbnail/original/b.webp")

    assert res.status_code == 200
    assert res.data == b"large"
