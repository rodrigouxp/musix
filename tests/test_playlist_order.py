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
    UserTable.insert_one({"username": "one", "password": "x", "roles": []})
    UserTable.insert_one({"username": "two", "password": "x", "roles": []})

    app = OpenAPI(__name__)
    app.register_api(playlist_api.api)
    return app.test_client()


def add(name, date, userid=1):
    PlaylistTable.insert_one(
        {"name": name, "last_updated": date, "userid": userid, "settings": {}, "trackhashes": []}
    )
    return [p.id for p in PlaylistTable.get_all(current_user=False) if p.name == name][0]


def names(http):
    return [p["name"] for p in http.get("/playlists").json["data"]]


def test_without_an_order_the_newest_comes_first(http):
    add("old", "2026-01-01 00:00:00")
    add("new", "2026-02-01 00:00:00")

    assert names(http) == ["new", "old"]


def test_the_saved_order_wins_over_the_date(http):
    a = add("a", "2026-01-01 00:00:00")
    b = add("b", "2026-02-01 00:00:00")
    c = add("c", "2026-03-01 00:00:00")

    assert http.post("/playlists/reorder", json={"ids": [a, c, b]}).status_code == 200
    assert names(http) == ["a", "c", "b"]


def test_a_playlist_without_an_order_comes_before_the_ordered_ones(http):
    a = add("a", "2026-01-01 00:00:00")
    b = add("b", "2026-02-01 00:00:00")
    http.post("/playlists/reorder", json={"ids": [b, a]})
    add("fresh", "2026-03-01 00:00:00")

    assert names(http) == ["fresh", "b", "a"]


def test_the_date_of_the_playlist_does_not_change(http):
    a = add("a", "2026-01-01 00:00:00")
    http.post("/playlists/reorder", json={"ids": [a]})

    assert PlaylistTable.get_by_id(a).last_updated == "2026-01-01 00:00:00"


def test_playlists_of_other_users_are_ignored(http):
    mine = add("mine", "2026-01-01 00:00:00")
    other = add("other", "2026-01-01 00:00:00", userid=2)

    assert http.post("/playlists/reorder", json={"ids": [other, mine]}).status_code == 200
    theirs = [p for p in PlaylistTable.get_all(current_user=False) if p.id == other][0]
    assert "order" not in theirs.settings
    assert PlaylistTable.get_by_id(mine).settings["order"] == 1
