import json
import os
import random
import time
from typing import Any
import urllib
from concurrent.futures import ProcessPoolExecutor
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, PngImagePlugin, UnidentifiedImageError
from requests.exceptions import ConnectionError as RequestConnectionError
from requests.exceptions import ReadTimeout

from musix import settings
from musix.models.artist import Artist
from musix.store.artists import ArtistStore
from musix.utils.hashing import create_hash
from musix.utils.progressbar import tqdm

LARGE_ENOUGH_NUMBER = 100
PngImagePlugin.MAX_TEXT_CHUNK = LARGE_ENOUGH_NUMBER * (1024**2)
# https://stackoverflow.com/a/61466412


def get_artist_image_link(artist: str):
    """
    Returns an artist image url.
    """
    response: requests.Response | None = None

    def make_request():
        query = urllib.parse.quote(artist)  # type: ignore
        url = f"https://api.deezer.com/search/artist?q={query}"
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
        ]
        headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.deezer.com/",
            "Origin": "https://www.deezer.com",
        }
        return requests.get(url, headers=headers, timeout=30)

    for attempt in range(5):
        try:
            response = make_request()
            try:
                data = response.json()
            except requests.exceptions.JSONDecodeError:
                return None

            for res in data["data"]:
                res_hash = create_hash(res["name"], decode=True)
                artist_hash = create_hash(artist, decode=True)

                if res_hash == artist_hash:
                    return str(res["picture_big"])

            return None
        except (RequestConnectionError, ReadTimeout, IndexError, KeyError):
            if attempt == 4:
                print("Failed to get artist image link  ")

            if attempt <= 4:
                time.sleep(10)
            else:
                return None

        # except (IndexError, KeyError):
        #     print(f"Encountered index/key error in attempt {attempt}")
        #     if response is not None:
        #         print(response.headers)

        #     return None


def artist_image_entries(name: str) -> list[tuple[Path, int | None]]:
    """
    The three files an artist photo is saved to: the original size
    and the small and medium thumbnails.
    """
    paths = settings.Paths()

    return [
        (paths.lg_artist_img_path / name, None),  # save in the original size
        (paths.sm_artist_img_path / name, settings.Defaults.SM_ARTIST_IMG_SIZE),
        (paths.md_artist_img_path / name, settings.Defaults.MD_ARTIST_IMG_SIZE),
    ]


def manual_marker_path(artisthash: str) -> Path:
    return settings.Paths().artist_img_path / "manual" / artisthash


def is_manual_artist_image(artisthash: str) -> bool:
    """
    Whether the photo of the artist was chosen by hand. The automatic
    download never replaces such a photo.
    """
    return manual_marker_path(artisthash).exists()


def set_manual_artist_image(artisthash: str, manual: bool):
    """
    Saves (or removes) the "chosen by hand" mark of an artist photo.
    The mark is an empty file named after the artist hash.
    """
    marker = manual_marker_path(artisthash)

    if manual:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    else:
        marker.unlink(missing_ok=True)


def crop_square(img: Image.Image, x: float = 50, y: float = 50) -> Image.Image:
    """
    Cuts the biggest square of the image around the point (x, y), both in percent of the
    width and the height. The square is kept inside the image, so a point near an edge
    gives the square that touches that edge. (50, 50) is the centre.
    """
    side = min(img.width, img.height)
    left = round(min(max(img.width * x / 100 - side / 2, 0), img.width - side))
    top = round(min(max(img.height * y / 100 - side / 2, 0), img.height - side))

    return img.crop((left, top, left + side, top + side))


# THE HERO of the artist page. The image is saved in two sizes without cropping (the browser
# cuts it with `object-fit: cover`) and the focus point is saved next to it, in a small json
# file named after the artist: both are only written by hand, nothing is downloaded.
def hero_image_path(artisthash: str, small: bool = False) -> Path:
    paths = settings.Paths()
    folder = paths.sm_artist_hero_img_path if small else paths.artist_hero_img_path

    return folder / f"{artisthash}.webp"


def hero_meta_path(artisthash: str) -> Path:
    return settings.Paths().artist_hero_img_path / f"{artisthash}.json"


def get_artist_hero(artisthash: str) -> dict | None:
    """
    The hero of an artist: the image file, the focus point (x and y in percent) and a
    version that changes when the image or the point changes (the browser uses it to
    load the new one). ``None`` when the artist has no hero.
    """
    if not hero_image_path(artisthash).exists():
        return None

    meta: dict[str, Any] = {}

    try:
        meta = json.loads(hero_meta_path(artisthash).read_text())
    except (OSError, ValueError):
        pass

    return {
        "image": f"{artisthash}.webp",
        "x": meta.get("x", 50),
        "y": meta.get("y", 50),
        "version": meta.get("version", 0),
    }


def set_hero_focus(artisthash: str, x: float, y: float):
    path = hero_meta_path(artisthash)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"x": x, "y": y, "version": time.time_ns() // 1_000_000})
    )


def save_artist_hero(img: Image.Image, artisthash: str, x: float = 50, y: float = 50):
    """
    Saves the hero (the big and the small one, same proportion as the image, never wider
    than it is) and the focus point.
    """
    for small, width in (
        (False, settings.Defaults.LG_ARTIST_HERO_WIDTH),
        (True, settings.Defaults.SM_ARTIST_HERO_WIDTH),
    ):
        path = hero_image_path(artisthash, small)
        path.parent.mkdir(parents=True, exist_ok=True)

        if img.width > width:
            resized = img.resize(
                (width, round(img.height * width / img.width)),
                Image.Resampling.LANCZOS,
            )
        else:
            resized = img

        resized.save(path, format="webp", quality=90)

    set_hero_focus(artisthash, x, y)


def remove_artist_hero(artisthash: str):
    for path in (
        hero_image_path(artisthash),
        hero_image_path(artisthash, True),
        hero_meta_path(artisthash),
    ):
        path.unlink(missing_ok=True)


def update_artist_color(artisthash: str):
    """
    Works out the colour of the artist photo again, after the photo was replaced.
    """
    # imported here to avoid a circular import
    from musix.db.userdata import LibDataTable
    from musix.lib.colorlib import extract_color_worker

    result = extract_color_worker(
        {
            "hash_field": "artisthash",
            "path_func": settings.Paths().sm_artist_img_path,
            "artisthash": artisthash,
        }
    )

    if result["color"] is None:
        return

    existing = LibDataTable.find_one(artisthash, type="artist")
    extra = {**((existing or {}).get("extra") or {}), "blurhash": result["blurhash"]}

    if existing is None:
        LibDataTable.insert_one(
            {
                "itemhash": "artist" + artisthash,
                "color": result["color"],
                "itemtype": "artist",
                "extra": extra,
            }
        )
    else:
        LibDataTable.update_one(
            "artist" + artisthash, {"color": result["color"], "extra": extra}
        )

    entry = ArtistStore.artistmap.get(artisthash)

    if entry:
        entry.update_color_info(result["color"], result["blurhash"])


# TODO: Move network calls to utils/network.py
class DownloadImage:
    # whether the image was downloaded and saved
    saved: bool = False

    def __init__(self, url: str, name: str) -> None:
        img = self.download(url)

        if img is None:
            return

        self.save_img(img, artist_image_entries(name))
        self.saved = True

    @staticmethod
    def download(url: str) -> Image.Image | None:
        """
        Downloads the image from the url.
        Retries after 10 seconds on a connection error.
        """
        for attempt in range(2):
            try:
                response = requests.get(url, timeout=10)
                return Image.open(BytesIO(response.content))
            except (RequestConnectionError, requests.Timeout, ReadTimeout):
                if attempt == 0:
                    time.sleep(10)
                else:
                    return None
            except UnidentifiedImageError:
                return None

    @staticmethod
    def save_img(img: Image.Image, entries: list[tuple[Path, int | None]]):
        """
        Saves the image to the destinations.
        """
        ratio = img.width / img.height
        for entry in entries:
            path, size = entry

            if size is None:
                img.save(path, format="webp")
                continue

            img.resize((size, int(size / ratio)), Image.Resampling.LANCZOS).save(
                path, format="webp"
            )


class CheckArtistImages:
    def __init__(self):
        # read all files in the artist image folder
        storeArtists = ArtistStore.get_flat_list()
        path = settings.Paths().sm_artist_img_path
        processed = set(i.replace(".webp", "") for i in os.listdir(path))

        unprocessed = [
            artist for artist in storeArtists if artist.artisthash not in processed
        ]

        num_workers = max(1, (os.cpu_count() or 1) // 2)

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            list(
                tqdm(
                    executor.map(self.download_image, unprocessed),
                    total=len(unprocessed),
                    desc="Downloading missing artist images",
                )
            )

    @staticmethod
    def download_image(artist: Artist):
        """
        Checks if an artist image exists and downloads it if not.

        :param artist: The artist name
        """
        img_path = (
                settings.Paths().sm_artist_img_path / f"{artist.artisthash}.webp"
        )

        if img_path.exists() or is_manual_artist_image(artist.artisthash):
            return

        url = get_artist_image_link(artist.name)

        if url is not None:
            return DownloadImage(url, name=f"{artist.artisthash}.webp")
