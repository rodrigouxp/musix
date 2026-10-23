from types import SimpleNamespace

import pytest
from flask_openapi3 import OpenAPI

from musix import settings
from musix.api import playlist as playlist_api
from musix.db.userdata import PlaylistTable, UserTable
from musix.utils import auth as auth_utils


@pytest.fixture
def http(tmp_path, database, monkeypatch):
    root = tmp_path / "playlist-img"
    root.mkdir()
    monkeypatch.setattr(settings, "Paths", lambda: SimpleNamespace(playlist_img_path=root))
    monkeypatch.setattr(auth_utils, "current_user", {"id": 1})
    monkeypatch.setattr(playlist_api.playlistlib, "get_first_4_images", lambda *a, **k: [])
    UserTable.insert_one({"username": "one", "password": "x", "roles": []})
    UserTable.insert_one({"username": "two", "password": "x", "roles": []})

    for name, hashes, userid in [
        ("Road trip", ["a", "b", "c"], 1),
        ("Gym", ["b"], 1),
        ("Empty", [], 1),
        ("Of another user", ["a", "b"], 2),
    ]:
        PlaylistTable.insert_one(
            {
                "name": name,
                "last_updated": "2026-01-01 00:00:00",
                "userid": userid,
                "settings": {},
                "trackhashes": hashes,
            }
        )

    app = OpenAPI(__name__)
    app.register_api(playlist_api.api)
    return app.test_client()


def has_track(res) -> dict[str, bool]:
    return {p["name"]: p["has_track"] for p in res.json["data"]}


def test_without_trackhash_the_playlists_do_not_have_has_track(http):
    res = http.get("/playlists")

    assert res.status_code == 200
    assert {p["name"] for p in res.json["data"]} == {"Road trip", "Gym", "Empty"}
    assert all("has_track" not in p for p in res.json["data"])


def test_with_a_trackhash_it_is_true_only_where_the_playlist_has_it(http):
    res = http.get("/playlists?trackhash=b")

    assert has_track(res) == {"Road trip": True, "Gym": True, "Empty": False}


def test_a_track_of_one_playlist(http):
    res = http.get("/playlists?trackhash=a")

    assert has_track(res) == {"Road trip": True, "Gym": False, "Empty": False}


def test_with_several_trackhashes_it_is_true_only_when_all_are_there(http):
    res = http.get("/playlists?trackhash=a,b")

    assert has_track(res) == {"Road trip": True, "Gym": False, "Empty": False}


def test_a_trackhash_that_is_in_no_playlist_gives_all_false(http):
    res = http.get("/playlists?trackhash=zzz")

    assert has_track(res) == {"Road trip": False, "Gym": False, "Empty": False}


def test_the_lists_of_hashes_still_do_not_go_over_the_api(http):
    res = http.get("/playlists?trackhash=a")

    assert all(p["trackhashes"] == [] for p in res.json["data"])
    assert {p["count"] for p in res.json["data"]} == {3, 1, 0}
