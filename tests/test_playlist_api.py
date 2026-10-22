import json
from io import BytesIO
from types import SimpleNamespace

import pytest
from flask_openapi3 import OpenAPI
from PIL import Image

from musix import settings
from musix.api import playlist as playlist_api
from musix.db.userdata import PlaylistTable, UserTable
from musix.utils import auth as auth_utils


@pytest.fixture
def paths(tmp_path, monkeypatch):
    root = tmp_path / "playlist-img"
    root.mkdir()
    fake = SimpleNamespace(playlist_img_path=root)
    monkeypatch.setattr(settings, "Paths", lambda: fake)
    return fake


@pytest.fixture
def users(database):
    UserTable.insert_one({"username": "one", "password": "x", "roles": []})
    UserTable.insert_one({"username": "two", "password": "x", "roles": []})


@pytest.fixture
def http(paths, database, users, monkeypatch):
    monkeypatch.setattr(auth_utils, "current_user", {"id": 1})

    app = OpenAPI(__name__)
    app.register_api(playlist_api.api)
    return app.test_client()


def png(size=(200, 200)) -> BytesIO:
    buffer = BytesIO()
    Image.new("RGB", size, (20, 90, 200)).save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def new_playlist(http, name="Mix") -> int:
    res = http.post("/playlists/new", json={"name": name})
    assert res.status_code == 201
    return res.json["playlist"]["id"]


def update(http, pid, **fields):
    data = {k: v for k, v in fields.items() if v is not None}
    return http.put(f"/playlists/{pid}/update", data=data, content_type="multipart/form-data")


def test_a_new_playlist_does_not_have_square_img(http):
    pid = new_playlist(http)

    assert "square_img" not in PlaylistTable.get_by_id(pid).settings


def test_renaming_without_a_photo_keeps_the_photo(http, paths):
    pid = new_playlist(http)
    photo = update(http, pid, image=(png(), "cover.png")).json["data"]["image"]

    res = update(http, pid, name="Renamed")

    assert res.status_code == 200
    assert res.json["data"]["name"] == "Renamed"
    assert res.json["data"]["image"] == photo
    assert res.json["data"]["has_image"] is True
    assert (paths.playlist_img_path / photo).exists()
    assert (paths.playlist_img_path / ("thumb_" + photo)).exists()


def test_the_answers_tell_how_long_ago_the_playlist_changed(http):
    pid = new_playlist(http)

    updated = update(http, pid, name="Renamed").json["data"]
    removed = http.delete(f"/playlists/{pid}/remove-img").json["playlist"]

    assert updated["_last_updated"]
    assert removed["_last_updated"]


def test_changing_the_photo_without_a_name_keeps_the_name(http):
    pid = new_playlist(http, "Road trip")

    res = update(http, pid, image=(png(), "cover.png"))

    assert res.status_code == 200
    assert res.json["data"]["name"] == "Road trip"
    assert PlaylistTable.get_by_id(pid).name == "Road trip"


def test_the_settings_stay_when_they_are_not_sent(http):
    pid = new_playlist(http)
    http.post(f"/playlists/{pid}/pin_unpin")

    update(http, pid, name="Renamed")

    assert PlaylistTable.get_by_id(pid).settings["pinned"] is True


def test_square_img_from_the_client_is_ignored(http):
    pid = new_playlist(http)

    update(http, pid, settings=json.dumps({"square_img": True, "pinned": True}))

    saved = PlaylistTable.get_by_id(pid).settings
    assert "square_img" not in saved
    assert saved["pinned"] is True


def test_a_name_that_another_playlist_has_is_a_409(http):
    new_playlist(http, "Taken")
    pid = new_playlist(http, "Mine")

    res = update(http, pid, name="Taken")

    assert res.status_code == 409
    assert PlaylistTable.get_by_id(pid).name == "Mine"


def test_a_name_that_looks_like_a_number_is_a_name(http):
    pid = new_playlist(http, "Mine")

    res = update(http, pid, name="2024")

    assert res.status_code == 200
    assert PlaylistTable.get_by_id(pid).name == "2024"


def test_removing_the_photo_of_a_gif_clears_has_gif(http):
    from PIL import Image as PILImage

    pid = new_playlist(http)
    frames = [PILImage.new("RGB", (40, 30), c) for c in ((255, 0, 0), (0, 255, 0))]
    buffer = BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=50, loop=0)
    buffer.seek(0)
    update(http, pid, image=(buffer, "anim.gif"))
    assert PlaylistTable.get_by_id(pid).settings["has_gif"] is True

    http.delete(f"/playlists/{pid}/remove-img")

    assert PlaylistTable.get_by_id(pid).settings["has_gif"] is False


def test_the_own_name_is_not_a_conflict(http):
    pid = new_playlist(http, "Mine")

    res = update(http, pid, name="Mine")

    assert res.status_code == 200


def test_the_playlist_of_another_user_does_not_count_for_the_name(http):
    PlaylistTable.insert_one(
        {"name": "Theirs", "last_updated": "2026-01-01 00:00:00", "userid": 2, "settings": {}, "trackhashes": []}
    )
    pid = new_playlist(http, "Mine")

    assert update(http, pid, name="Theirs").status_code == 200


def test_an_empty_name_is_a_400(http):
    pid = new_playlist(http, "Mine")

    assert update(http, pid, name="   ").status_code == 400
    assert PlaylistTable.get_by_id(pid).name == "Mine"


def test_an_invalid_image_is_a_400_and_the_name_does_not_change(http):
    pid = new_playlist(http, "Mine")

    res = update(http, pid, name="Other", image=(BytesIO(b"not an image"), "cover.png"))

    assert res.status_code == 400
    assert PlaylistTable.get_by_id(pid).name == "Mine"


def test_updating_a_playlist_that_does_not_exist_is_a_404(http):
    assert update(http, 999, name="x").status_code == 404
    assert update(http, "recentlyadded", name="x").status_code == 404


def test_removing_the_photo_deletes_the_files(http, paths):
    pid = new_playlist(http)
    update(http, pid, image=(png(), "cover.png"))

    res = http.delete(f"/playlists/{pid}/remove-img")

    assert res.status_code == 200
    assert list(paths.playlist_img_path.iterdir()) == []
    assert http.get(f"/playlists/{pid}").json["info"]["has_image"] is False


def test_deleting_a_playlist_deletes_its_photo_and_keeps_the_others(http, paths):
    first = new_playlist(http, "First")
    second = new_playlist(http, "Second")
    update(http, first, image=(png(), "a.png"))
    kept = update(http, second, image=(png(), "b.png")).json["data"]["image"]

    http.delete(f"/playlists/{first}/delete")

    assert {f.name for f in paths.playlist_img_path.iterdir()} == {kept, "thumb_" + kept}


def test_favorite_toggles_and_is_listed(http):
    pid = new_playlist(http)
    assert http.get("/playlists").json["data"][0]["is_favorite"] is False

    first = http.post(f"/playlists/{pid}/favorite")
    assert first.status_code == 200
    assert first.json["is_favorite"] is True
    assert http.get("/playlists").json["data"][0]["is_favorite"] is True
    assert http.get(f"/playlists/{pid}").json["info"]["is_favorite"] is True
    assert update(http, pid, name="Renamed").json["data"]["is_favorite"] is True

    second = http.post(f"/playlists/{pid}/favorite")
    assert second.json["is_favorite"] is False
    assert http.get(f"/playlists/{pid}").json["info"]["is_favorite"] is False


def test_favorite_does_not_touch_the_pin(http):
    pid = new_playlist(http)
    http.post(f"/playlists/{pid}/pin_unpin")

    http.post(f"/playlists/{pid}/favorite")

    saved = PlaylistTable.get_by_id(pid).settings
    assert saved["pinned"] is True
    assert saved["favorite"] is True


def test_favorite_of_a_missing_playlist_is_a_404(http):
    assert http.post("/playlists/999/favorite").status_code == 404
    assert http.post("/playlists/recentlyadded/favorite").status_code == 404


def test_the_favorite_of_a_playlist_of_another_user_is_a_404(http):
    PlaylistTable.insert_one(
        {"name": "Theirs", "last_updated": "2026-01-01 00:00:00", "userid": 2, "settings": {}, "trackhashes": []}
    )
    other = list(PlaylistTable.get_all(current_user=False))[0].id

    assert http.post(f"/playlists/{other}/favorite").status_code == 404


def test_pin_still_works(http):
    pid = new_playlist(http)

    assert http.post(f"/playlists/{pid}/pin_unpin").status_code == 200
    assert http.get(f"/playlists/{pid}").json["info"]["pinned"] is True
    assert http.post(f"/playlists/{pid}/pin_unpin").status_code == 200
    assert http.get(f"/playlists/{pid}").json["info"]["pinned"] is False
