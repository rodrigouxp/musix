from types import SimpleNamespace

import pytest
from flask_openapi3 import OpenAPI

from musix import settings
from musix.api import playlist as playlist_api
from musix.db.userdata import PlaylistTable, UserTable
from musix.store.tracks import TrackStore
from musix.utils import auth as auth_utils

HASHES = ["a", "b", "c", "d", "e"]


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


@pytest.fixture
def pid(http) -> int:
    PlaylistTable.insert_one(
        {
            "name": "Mix",
            "last_updated": "2026-01-01 00:00:00",
            "userid": 1,
            "settings": {},
            "trackhashes": list(HASHES),
        }
    )
    return list(PlaylistTable.get_all())[0].id


def move(http, pid, trackhash, to_index):
    return http.post(f"/playlists/{pid}/move-track", json={"trackhash": trackhash, "to_index": to_index})


def order(pid) -> list[str]:
    return PlaylistTable.get_trackhashes(pid)


def test_moves_a_track_up(http, pid):
    assert move(http, pid, "d", 1).status_code == 200
    assert order(pid) == ["a", "d", "b", "c", "e"]


def test_moves_a_track_down(http, pid):
    assert move(http, pid, "b", 3).status_code == 200
    assert order(pid) == ["a", "c", "d", "b", "e"]


def test_moves_a_track_to_the_start(http, pid):
    assert move(http, pid, "e", 0).status_code == 200
    assert order(pid) == ["e", "a", "b", "c", "d"]


def test_moves_a_track_to_the_end(http, pid):
    assert move(http, pid, "a", 4).status_code == 200
    assert order(pid) == ["b", "c", "d", "e", "a"]


def test_the_same_position_is_a_success_and_does_not_save(http, pid, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("nothing should be saved")

    monkeypatch.setattr(PlaylistTable, "move_track", fail)

    res = move(http, pid, "c", 2)

    assert res.status_code == 200
    assert res.json == {"msg": "Done"}
    assert order(pid) == HASHES


def test_a_track_that_is_not_in_the_playlist_is_a_404(http, pid):
    assert move(http, pid, "zzz", 0).status_code == 404
    assert order(pid) == HASHES


@pytest.mark.parametrize("to_index", [-1, 5, 99])
def test_an_index_outside_of_the_list_is_a_400(http, pid, to_index):
    assert move(http, pid, "a", to_index).status_code == 400
    assert order(pid) == HASHES


def test_a_playlist_of_another_user_is_a_404(http, pid, monkeypatch):
    monkeypatch.setattr(auth_utils, "current_user", {"id": 2})

    assert move(http, pid, "a", 3).status_code == 404

    monkeypatch.setattr(auth_utils, "current_user", {"id": 1})
    assert order(pid) == HASHES


def test_a_playlist_that_does_not_exist_is_a_404(http, pid):
    assert move(http, 999, "a", 0).status_code == 404
    assert move(http, "recentlyadded", "a", 0).status_code == 404


def test_the_move_does_not_change_the_date_of_the_playlist(http, pid):
    move(http, pid, "e", 0)

    assert list(PlaylistTable.get_all())[0].last_updated == "2026-01-01 00:00:00"


def test_the_page_of_the_playlist_has_the_tracks_in_the_new_order(http, pid, monkeypatch):
    tracks = {h: SimpleNamespace(trackhash=h, duration=10, albumhash="x") for h in HASHES}

    def by_hashes(hashes):
        return [tracks[h] for h in hashes if h in tracks]

    monkeypatch.setattr(TrackStore, "get_tracks_by_trackhashes", by_hashes)
    monkeypatch.setattr(playlist_api, "serialize_tracks", lambda items: [{"trackhash": t.trackhash} for t in items])
    monkeypatch.setattr(playlist_api.playlistlib, "get_first_4_images", lambda *a, **k: [])

    move(http, pid, "d", 0)
    res = http.get(f"/playlists/{pid}")

    assert [t["trackhash"] for t in res.json["tracks"]] == ["d", "a", "b", "c", "e"]


def test_limit_minus_one_gives_every_track(http, pid, monkeypatch):
    monkeypatch.setattr(TrackStore, "get_tracks_by_trackhashes", lambda hashes: [SimpleNamespace(trackhash=h, duration=1, albumhash="x") for h in hashes])
    monkeypatch.setattr(playlist_api, "serialize_tracks", lambda items: [{"trackhash": t.trackhash} for t in items])
    monkeypatch.setattr(playlist_api.playlistlib, "get_first_4_images", lambda *a, **k: [])

    res = http.get(f"/playlists/{pid}?limit=-1")

    assert [t["trackhash"] for t in res.json["tracks"]] == HASHES
