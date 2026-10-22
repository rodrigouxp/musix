import json
from io import BytesIO
from types import SimpleNamespace

import pytest
from flask_openapi3 import OpenAPI
from PIL import Image

from musix import settings
from musix.api import playlist as playlist_api
from musix.db.userdata import PlaylistTable, UserTable
from musix.lib import playlistlib
from musix.utils import auth as auth_utils

SETTINGS = json.dumps({"has_gif": False, "pinned": False})


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


def image_bytes(size=(300, 200), color=(200, 30, 30), fmt="PNG") -> BytesIO:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    buffer.seek(0)
    return buffer


def gif_bytes(size=(120, 80)) -> BytesIO:
    frames = [Image.new("RGB", size, color) for color in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
    buffer = BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=80, loop=0)
    buffer.seek(0)
    return buffer


def new_playlist(http, name="Mix") -> int:
    res = http.post("/playlists/new", json={"name": name})
    assert res.status_code == 201
    return res.json["playlist"]["id"]


def upload(http, pid, data, name="cover.png", playlist_name="Mix"):
    return http.put(
        f"/playlists/{pid}/update",
        data={"image": (data, name), "name": playlist_name, "settings": SETTINGS},
        content_type="multipart/form-data",
    )


def files(paths) -> set[str]:
    return {f.name for f in paths.playlist_img_path.iterdir() if f.is_file()}


def add_playlist(name, image, userid=1):
    PlaylistTable.insert_one(
        {"name": name, "last_updated": "2026-01-01 00:00:00", "image": image, "userid": userid, "settings": {}, "trackhashes": []}
    )


def test_the_photo_and_its_thumbnail_are_still_there_after_the_upload(http, paths):
    # the bug: the cleanup that runs after the upload deleted the files in use
    pid = new_playlist(http)

    res = upload(http, pid, image_bytes())

    assert res.status_code == 200
    name = res.json["data"]["image"]
    assert name != "None"
    assert {name, "thumb_" + name} <= files(paths)
    assert res.json["data"]["has_image"] is True

    # the list of the Playlists page and the page of the playlist
    listed = http.get("/playlists").json["data"][0]
    assert listed["has_image"] is True
    assert listed["image"] == name
    assert listed["thumb"] == "thumb_" + name
    assert http.get(f"/playlists/{pid}").json["info"]["has_image"] is True


def test_replacing_the_photo_deletes_the_old_files_and_keeps_the_new_ones(http, paths):
    pid = new_playlist(http)
    first = upload(http, pid, image_bytes()).json["data"]["image"]

    second = upload(http, pid, image_bytes(color=(10, 200, 10)), name="other.png").json["data"]["image"]

    assert first != second
    assert files(paths) == {second, "thumb_" + second}


def test_a_rectangular_photo_becomes_a_square_cover_and_thumbnail(http, paths):
    pid = new_playlist(http)

    name = upload(http, pid, image_bytes(size=(300, 200))).json["data"]["image"]

    with Image.open(paths.playlist_img_path / name) as cover:
        assert cover.size == (200, 200)

    with Image.open(paths.playlist_img_path / ("thumb_" + name)) as thumb:
        assert thumb.size == (250, 250)


def test_a_tall_photo_is_cut_in_the_center(http, paths):
    pid = new_playlist(http)
    img = Image.new("RGB", (100, 300), (0, 0, 0))
    img.paste((255, 255, 255), (0, 100, 100, 200))  # the central square is white
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    name = upload(http, pid, buffer).json["data"]["image"]

    with Image.open(paths.playlist_img_path / name) as cover:
        assert cover.size == (100, 100)
        assert cover.convert("RGB").getpixel((50, 50)) == (255, 255, 255)
        assert cover.convert("RGB").getpixel((2, 2)) == (255, 255, 255)


def test_a_gif_is_accepted_and_every_frame_is_square(http, paths):
    pid = new_playlist(http)

    res = upload(http, pid, gif_bytes(), name="anim.gif")

    assert res.status_code == 200
    assert res.json["data"]["settings"]["has_gif"] is True
    name = res.json["data"]["image"]
    assert {name, "thumb_" + name} <= files(paths)

    with Image.open(paths.playlist_img_path / name) as cover:
        assert cover.size == (80, 80)
        assert getattr(cover, "n_frames", 1) == 3

    with Image.open(paths.playlist_img_path / ("thumb_" + name)) as thumb:
        assert thumb.size == (250, 250)


def test_an_invalid_image_is_a_400_and_nothing_is_written(http, paths):
    pid = new_playlist(http)

    res = upload(http, pid, BytesIO(b"this is not an image"), name="cover.png")

    assert res.status_code == 400
    assert files(paths) == set()


def test_cleanup_deletes_the_orphans_and_keeps_the_files_in_use(paths, users):
    folder = paths.playlist_img_path
    for name in ("used.webp", "thumb_used.webp", "orphan.webp", "thumb_orphan.webp", "thumb_alone.webp"):
        (folder / name).write_bytes(b"x")

    add_playlist("p", "used.webp")

    playlistlib.cleanup_playlist_images()

    assert files(paths) == {"used.webp", "thumb_used.webp"}


def test_cleanup_counts_the_playlists_of_every_user(paths, users):
    folder = paths.playlist_img_path
    for name in ("mine.webp", "thumb_mine.webp", "theirs.webp", "thumb_theirs.webp"):
        (folder / name).write_bytes(b"x")

    add_playlist("mine", "mine.webp", userid=1)
    add_playlist("theirs", "theirs.webp", userid=2)

    playlistlib.cleanup_playlist_images()

    assert files(paths) == {"mine.webp", "thumb_mine.webp", "theirs.webp", "thumb_theirs.webp"}


def test_cleanup_does_not_touch_subfolders(paths, users):
    folder = paths.playlist_img_path
    (folder / "sub").mkdir()
    (folder / "sub" / "orphan.webp").write_bytes(b"x")
    (folder / "orphan.webp").write_bytes(b"x")

    playlistlib.cleanup_playlist_images()

    assert files(paths) == set()
    assert (folder / "sub" / "orphan.webp").exists()


def test_cleanup_with_no_image_in_the_database_keeps_nothing_in_use(paths, users):
    (paths.playlist_img_path / "orphan.webp").write_bytes(b"x")
    add_playlist("no image", None)

    playlistlib.cleanup_playlist_images()

    assert files(paths) == set()
