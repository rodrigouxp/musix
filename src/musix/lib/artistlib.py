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
