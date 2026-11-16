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


# ---- a playlist never has the same track twice ----


def add_tracks(http, pid, hashes):
    return http.post(f"/playlists/{pid}/add", json={"itemtype": "tracks", "itemhash": ",".join(hashes)})


def test_a_track_that_comes_twice_is_added_once(http):
    pid = add("dup", "2026-01-01 00:00:00")

    assert add_tracks(http, pid, ["a", "b", "a"]).status_code == 200
    assert PlaylistTable.get_trackhashes(pid) == ["a", "b"]


def test_adding_what_the_playlist_has_is_a_409_and_changes_nothing(http):
    pid = add("dup", "2026-01-01 00:00:00")
    add_tracks(http, pid, ["a", "b"])

    assert add_tracks(http, pid, ["a"]).status_code == 409
    assert add_tracks(http, pid, ["b", "a"]).status_code == 409
    assert PlaylistTable.get_trackhashes(pid) == ["a", "b"]


def test_only_the_new_tracks_of_a_list_are_added(http):
    pid = add("dup", "2026-01-01 00:00:00")
    add_tracks(http, pid, ["a", "b"])

    assert add_tracks(http, pid, ["b", "c", "c"]).status_code == 200
    assert PlaylistTable.get_trackhashes(pid) == ["a", "b", "c"]


def test_the_old_repeated_tracks_are_taken_out(http):
    pid = add("old", "2026-01-01 00:00:00")
    clean = add("clean", "2026-01-02 00:00:00")
    PlaylistTable.update_one(pid, {"trackhashes": ["a", "b", "a", "c", "b"]})
    PlaylistTable.update_one(clean, {"trackhashes": ["x", "y"]})

    assert PlaylistTable.remove_duplicate_tracks() == 1
    assert PlaylistTable.get_trackhashes(pid) == ["a", "b", "c"]
    assert PlaylistTable.get_trackhashes(clean) == ["x", "y"]


def test_the_next_page_starts_in_positions_of_the_playlist(http):
    # none of the tracks is in the library (as the ones that were deleted): the pages have no tracks, but the next start moves
    pid = add("paged", "2026-01-01 00:00:00")
    add_tracks(http, pid, ["a", "b", "c", "d", "e"])

    first = http.get(f"/playlists/{pid}?start=0&limit=2").json
    second = http.get(f"/playlists/{pid}?start={first['next_start']}&limit=2").json
    last = http.get(f"/playlists/{pid}?start={second['next_start']}&limit=2").json

    assert [first["next_start"], second["next_start"], last["next_start"]] == [2, 4, 5]
