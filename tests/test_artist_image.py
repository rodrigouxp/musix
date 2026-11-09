from io import BytesIO
from types import SimpleNamespace

import pytest
from flask_openapi3 import OpenAPI
from PIL import Image

from musix import settings
from musix.api import artist as artist_api
from musix.api import auth as auth_api
from musix.lib import artistlib
from musix.lib.artistlib import CheckArtistImages, is_manual_artist_image
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
    for folder in (fake.sm_artist_img_path, fake.md_artist_img_path, fake.lg_artist_img_path):
        folder.mkdir(parents=True)

    monkeypatch.setattr(settings, "Paths", lambda: fake)
    return fake


@pytest.fixture
def http(paths, database, monkeypatch):
    monkeypatch.setattr(auth_api, "current_user", {"roles": ["admin"]})
    artist = SimpleNamespace(
        name="Black Sabbath",
        artisthash=ARTISTHASH,
    )
    entry = SimpleNamespace(
        artist=artist, update_color_info=lambda color, blurhash: None
    )
    monkeypatch.setattr(ArtistStore, "artistmap", {ARTISTHASH: entry})

    app = OpenAPI(__name__)
    app.register_api(artist_api.api)
    return app.test_client()


def png_bytes(size=(300, 200), color=(200, 30, 30), fmt="PNG", mode="RGB") -> BytesIO:
    buffer = BytesIO()
    Image.new(mode, size, color).save(buffer, format=fmt)
    buffer.seek(0)
    return buffer


def upload(http, data, name="photo.png", artisthash=ARTISTHASH):
    return http.post(
        f"/artist/{artisthash}/image",
        data={"image": (data, name)},
        content_type="multipart/form-data",
    )


def test_upload_for_unknown_artist_is_404(http):
    res = upload(http, png_bytes(), artisthash="b" * 16)

    assert res.status_code == 404


def test_refetch_for_unknown_artist_is_404(http):
    res = http.post(f"/artist/{'b' * 16}/image/refetch")

    assert res.status_code == 404


def test_upload_requires_admin(http, monkeypatch):
    monkeypatch.setattr(auth_api, "current_user", {"roles": []})

    assert upload(http, png_bytes()).status_code == 403


@pytest.mark.parametrize(
    "make",
    [
        lambda: BytesIO(b"this is not an image"),
        lambda: png_bytes(fmt="GIF", mode="P", color=1),
        lambda: png_bytes(fmt="BMP"),
    ],
    ids=["text", "gif", "bmp"],
)
def test_invalid_files_are_400(http, paths, make):
    res = upload(http, make())

    assert res.status_code == 400
    assert not list(paths.sm_artist_img_path.iterdir())
    assert not is_manual_artist_image(ARTISTHASH)


def test_missing_field_is_400(http):
    res = http.post(
        f"/artist/{ARTISTHASH}/image", data={}, content_type="multipart/form-data"
    )

    assert res.status_code == 400


def test_file_over_10_mb_is_400(http, monkeypatch):
    monkeypatch.setattr(artist_api, "MAX_ARTIST_IMAGE_BYTES", 1000)

    assert upload(http, png_bytes((400, 400))).status_code == 400


@pytest.mark.parametrize(
    "fmt,name", [("PNG", "a.png"), ("JPEG", "a.jpg"), ("WEBP", "a.webp")]
)
def test_upload_makes_three_thumbnails_and_marks_it_manual(http, paths, fmt, name):
    res = upload(http, png_bytes(fmt=fmt), name)

    assert res.status_code == 200
    assert res.get_json() == {
        "ok": True,
        "image": f"{ARTISTHASH}.webp",
        "source": "upload",
    }
    file = f"{ARTISTHASH}.webp"
    with Image.open(paths.lg_artist_img_path / file) as lg:
        assert lg.size == (200, 200)
    with Image.open(paths.md_artist_img_path / file) as md:
        assert md.width == settings.Defaults.MD_ARTIST_IMG_SIZE
    with Image.open(paths.sm_artist_img_path / file) as sm:
        assert sm.width == settings.Defaults.SM_ARTIST_IMG_SIZE
    assert is_manual_artist_image(ARTISTHASH)


def test_refetch_goes_back_to_the_automatic_photo(http, paths, monkeypatch):
    upload(http, png_bytes())
    assert is_manual_artist_image(ARTISTHASH)

    monkeypatch.setattr(artist_api, "get_artist_image_link", lambda name: "http://x/y.jpg")
    monkeypatch.setattr(
        artistlib.DownloadImage,
        "download",
        staticmethod(lambda url: Image.new("RGB", (500, 500), (0, 0, 255))),
    )

    res = http.post(f"/artist/{ARTISTHASH}/image/refetch")

    assert res.status_code == 200
    assert res.get_json() == {
        "ok": True,
        "image": f"{ARTISTHASH}.webp",
        "source": "deezer",
    }
    assert not is_manual_artist_image(ARTISTHASH)
    with Image.open(paths.lg_artist_img_path / f"{ARTISTHASH}.webp") as lg:
        assert lg.size == (500, 500)
        assert lg.convert("RGB").getpixel((5, 5))[2] > 200


def test_refetch_keeps_the_manual_photo_when_nothing_is_found(http, monkeypatch):
    upload(http, png_bytes())
    monkeypatch.setattr(artist_api, "get_artist_image_link", lambda name: None)

    res = http.post(f"/artist/{ARTISTHASH}/image/refetch")

    assert res.status_code == 502
    assert is_manual_artist_image(ARTISTHASH)


def test_automatic_search_never_replaces_a_manual_photo(http, paths, monkeypatch):
    upload(http, png_bytes())
    # even if the small file is gone, the mark protects the photo
    (paths.sm_artist_img_path / f"{ARTISTHASH}.webp").unlink()

    def fail(name):
        raise AssertionError("the automatic search must not run")

    monkeypatch.setattr(artistlib, "get_artist_image_link", fail)

    CheckArtistImages.download_image(SimpleNamespace(name="x", artisthash=ARTISTHASH))


def two_color_png(size=(400, 200)) -> BytesIO:
    """Left half red, right half blue."""
    img = Image.new("RGB", size, (255, 0, 0))
    img.paste((0, 0, 255), (size[0] // 2, 0, size[0], size[1]))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def upload_with_focus(http, data, x, y):
    return http.post(
        f"/artist/{ARTISTHASH}/image",
        data={"image": (data, "photo.png"), "x": x, "y": y},
        content_type="multipart/form-data",
    )


def test_focus_point_moves_the_square_of_the_photo(http, paths):
    # a 400 x 200 photo: the square is 200 x 200 and the focus point decides which one
    assert upload_with_focus(http, two_color_png(), 0, 50).status_code == 200
    with Image.open(paths.lg_artist_img_path / f"{ARTISTHASH}.webp") as lg:
        assert lg.size == (200, 200)
        assert lg.convert("RGB").getpixel((100, 100))[0] > 200  # the left part: red

    assert upload_with_focus(http, two_color_png(), 100, 50).status_code == 200
    with Image.open(paths.lg_artist_img_path / f"{ARTISTHASH}.webp") as lg:
        assert lg.convert("RGB").getpixel((100, 100))[2] > 200  # the right part: blue


def test_without_a_focus_point_the_square_is_the_centre(http, paths):
    assert upload(http, two_color_png()).status_code == 200
    with Image.open(paths.lg_artist_img_path / f"{ARTISTHASH}.webp") as lg:
        pixels = lg.convert("RGB")
        assert pixels.getpixel((5, 100))[0] > 200  # red on the left of the square
        assert pixels.getpixel((195, 100))[2] > 200  # blue on the right


@pytest.mark.parametrize("x,y", [("abc", "50"), ("50", ""), ("-1", "50"), ("50", "101")])
def test_a_bad_focus_point_is_400(http, paths, x, y):
    assert upload_with_focus(http, png_bytes(), x, y).status_code == 400
    assert not list(paths.sm_artist_img_path.iterdir())
