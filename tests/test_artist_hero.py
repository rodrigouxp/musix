import json
from io import BytesIO
from types import SimpleNamespace

import pytest
from flask_openapi3 import OpenAPI
from PIL import Image

from musix import settings
from musix.api import artist as artist_api
from musix.api import auth as auth_api
from musix.lib.artistlib import get_artist_hero
from musix.store.artists import ArtistStore

ARTISTHASH = "a" * 16


@pytest.fixture
def paths(tmp_path, monkeypatch):
    root = tmp_path / "artists"
    fake = SimpleNamespace(
        artist_img_path=root,
        sm_artist_img_path=root / "small",
        md_artist_img_path=root / "medium",
        lg_artist_img_path=root / "large",
        artist_hero_img_path=root / "hero",
        sm_artist_hero_img_path=root / "hero" / "small",
    )
    # the hero folders are not made here: saving a hero makes them

    for folder in (fake.sm_artist_img_path, fake.md_artist_img_path, fake.lg_artist_img_path):
        folder.mkdir(parents=True)

    monkeypatch.setattr(settings, "Paths", lambda: fake)
    return fake


@pytest.fixture
def http(paths, database, monkeypatch):
    monkeypatch.setattr(auth_api, "current_user", {"roles": ["admin"]})
    artist = SimpleNamespace(name="Black Sabbath", artisthash=ARTISTHASH)
    entry = SimpleNamespace(artist=artist, update_color_info=lambda color, blurhash: None)
    monkeypatch.setattr(ArtistStore, "artistmap", {ARTISTHASH: entry})

    app = OpenAPI(__name__)
    app.register_api(artist_api.api)
    return app.test_client()


def image_bytes(size=(3000, 1000), color=(200, 30, 30), fmt="PNG") -> BytesIO:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    buffer.seek(0)
    return buffer


def upload(http, data=None, name="hero.png", artisthash=ARTISTHASH, **fields):
    form = {"image": (data or image_bytes(), name), **fields}
    return http.post(
        f"/artist/{artisthash}/hero", data=form, content_type="multipart/form-data"
    )


def test_no_hero_by_default(paths):
    assert get_artist_hero(ARTISTHASH) is None


def test_upload_is_not_cropped_and_is_made_smaller_in_two_sizes(http, paths):
    res = upload(http)

    assert res.status_code == 200
    hero = res.get_json()["hero"]
    assert hero["image"] == f"{ARTISTHASH}.webp"
    assert (hero["x"], hero["y"]) == (50, 50)
    assert hero["version"] > 0

    with Image.open(paths.artist_hero_img_path / hero["image"]) as lg:
        assert lg.size == (2560, 853)  # 3000 x 1000 kept in proportion
    with Image.open(paths.sm_artist_hero_img_path / hero["image"]) as sm:
        assert sm.size == (1280, 427)


def test_a_smaller_image_is_not_made_bigger(http, paths):
    upload(http, image_bytes((900, 300)))

    with Image.open(paths.artist_hero_img_path / f"{ARTISTHASH}.webp") as lg:
        assert lg.size == (900, 300)
    with Image.open(paths.sm_artist_hero_img_path / f"{ARTISTHASH}.webp") as sm:
        assert sm.size == (900, 300)


@pytest.mark.parametrize("fmt,name", [("PNG", "a.png"), ("JPEG", "a.jpg"), ("WEBP", "a.webp")])
def test_the_three_formats_are_accepted(http, fmt, name):
    assert upload(http, image_bytes((400, 200), fmt=fmt), name).status_code == 200


def test_the_focus_point_is_saved_with_the_image(http, paths):
    res = upload(http, x="12.5", y="80")

    hero = res.get_json()["hero"]
    assert (hero["x"], hero["y"]) == (12.5, 80)
    meta = json.loads((paths.artist_hero_img_path / f"{ARTISTHASH}.json").read_text())
    assert meta["x"] == 12.5


@pytest.mark.parametrize("x,y", [("abc", "50"), ("50", ""), ("-1", "50"), ("50", "101")])
def test_a_bad_focus_point_is_400(http, paths, x, y):
    assert upload(http, x=x, y=y).status_code == 400
    assert get_artist_hero(ARTISTHASH) is None


@pytest.mark.parametrize(
    "make",
    [
        lambda: BytesIO(b"this is not an image"),
        lambda: image_bytes(fmt="BMP"),
    ],
    ids=["text", "bmp"],
)
def test_invalid_files_are_400_and_save_nothing(http, make):
    assert upload(http, make()).status_code == 400
    assert get_artist_hero(ARTISTHASH) is None


def test_file_over_10_mb_is_400(http, monkeypatch):
    monkeypatch.setattr(artist_api, "MAX_ARTIST_IMAGE_BYTES", 1000)

    assert upload(http, image_bytes((800, 800))).status_code == 400


def test_missing_field_is_400(http):
    res = http.post(f"/artist/{ARTISTHASH}/hero", data={}, content_type="multipart/form-data")

    assert res.status_code == 400


def test_unknown_artist_is_404(http):
    assert upload(http, artisthash="b" * 16).status_code == 404
    assert http.delete(f"/artist/{'b' * 16}/hero").status_code == 404
    res = http.post(f"/artist/{'b' * 16}/hero/position", json={"x": 1, "y": 1})
    assert res.status_code == 404


def test_only_admins_can_change_the_hero(http, monkeypatch):
    upload(http)
    monkeypatch.setattr(auth_api, "current_user", {"roles": []})

    assert upload(http).status_code == 403
    res = http.post(f"/artist/{ARTISTHASH}/hero/position", json={"x": 1, "y": 1})
    assert res.status_code == 403
    assert http.delete(f"/artist/{ARTISTHASH}/hero").status_code == 403
    assert get_artist_hero(ARTISTHASH) is not None


def test_position_only_moves_the_focus_point(http, paths):
    first = upload(http).get_json()["hero"]
    before = (paths.artist_hero_img_path / f"{ARTISTHASH}.webp").read_bytes()

    res = http.post(f"/artist/{ARTISTHASH}/hero/position", json={"x": 20, "y": 30})

    assert res.status_code == 200
    hero = res.get_json()["hero"]
    assert (hero["x"], hero["y"]) == (20, 30)
    assert hero["version"] >= first["version"]
    assert (paths.artist_hero_img_path / f"{ARTISTHASH}.webp").read_bytes() == before


def test_position_without_a_hero_is_404(http):
    res = http.post(f"/artist/{ARTISTHASH}/hero/position", json={"x": 1, "y": 1})

    assert res.status_code == 404


@pytest.mark.parametrize("body", [{"x": -1, "y": 0}, {"x": 0, "y": 101}, {"x": 5}])
def test_position_out_of_range_is_refused(http, body):
    upload(http)

    res = http.post(f"/artist/{ARTISTHASH}/hero/position", json=body)

    assert res.status_code in (400, 422)


def test_delete_removes_the_hero(http, paths):
    upload(http)

    res = http.delete(f"/artist/{ARTISTHASH}/hero")

    assert res.status_code == 200
    assert res.get_json()["hero"] is None
    assert get_artist_hero(ARTISTHASH) is None
    assert not list(paths.artist_hero_img_path.glob(f"{ARTISTHASH}*"))
    assert not list(paths.sm_artist_hero_img_path.glob(f"{ARTISTHASH}*"))


def test_delete_without_a_hero_is_fine(http):
    assert http.delete(f"/artist/{ARTISTHASH}/hero").status_code == 200


def test_the_hero_does_not_touch_the_round_photo(http, paths):
    upload(http)

    assert not list(paths.sm_artist_img_path.iterdir())
