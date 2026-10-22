"""
This library contains all the functions related to playlists.
"""
import random
import string
import logging
from PIL import Image, ImageOps, ImageSequence

from musix import settings
from musix.models.track import Track
from musix.store.albums import AlbumStore
from musix.store.tracks import TrackStore

logger = logging.getLogger(__name__)

# The cover of a playlist is always a square. The thumbnail is 250 x 250.
THUMB_SIZE = 250


def crop_square(image: Image.Image) -> Image.Image:
    """
    Cuts the image to the central square. A square image is returned as it is.
    """
    side = min(image.width, image.height)

    if image.width == image.height:
        return image

    left = (image.width - side) // 2
    top = (image.height - side) // 2

    return image.crop((left, top, left + side, top + side))


def prepare_image(image: Image.Image) -> Image.Image:
    """
    Applies the rotation of the camera (EXIF) and keeps a mode that WEBP can save.
    """
    image = ImageOps.exif_transpose(image)

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "transparency" in image.info or "A" in image.mode else "RGB")

    return image


def get_gif_frames(image: Image.Image) -> tuple[list[Image.Image], int]:
    """
    Returns every frame of the GIF (square, RGBA) and the time of a frame in ms.
    """
    frames = [crop_square(frame.convert("RGBA")) for frame in ImageSequence.Iterator(image)]
    return frames, int(image.info.get("duration", 100) or 100)


def create_thumbnail(image: Image.Image, img_name: str) -> str:
    """
    Creates a 250 x 250 thumbnail from the Image (cut to the central square).

    Images are saved in the playlist-img path

    :param image: Image object.
    :param img_name: Name of image.
    :return: Filename of image.
    """
    thumb = crop_square(image).resize((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)

    thumb_filename = "thumb_" + img_name
    thumb_path = settings.Paths().playlist_img_path / thumb_filename

    thumb.save(thumb_path, "webp")

    return thumb_filename


def create_gif_thumbnail(image: Image.Image, img_name: str):
    """
    Creates a 250 x 250 thumbnail from the provided GIF (every frame is cut to
    the central square).

    Images are saved in the playlist-img path

    :param image: Image object.
    :param img_name: Name of image.
    :return: Filename of image.
    """
    thumb_name = "thumb_" + img_name
    thumb_path = settings.Paths().playlist_img_path / thumb_name

    frames, duration = get_gif_frames(image)
    frames = [f.resize((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS) for f in frames]

    frames[0].save(
        thumb_path, "webp", save_all=True, append_images=frames[1:], duration=duration, loop=0
    )

    return thumb_name


def save_p_image(img: Image.Image, pid: int, content_type: str = None, filename: str = None) -> str:
    """
    Saves a playlist cover (cut to the central square) and its thumbnail, and
    returns the file name.
    """
    random_str = "".join(random.choices(string.ascii_letters + string.digits, k=5))

    if not filename:
        filename = str(pid) + str(random_str) + ".webp"

    full_img_path = settings.Paths().playlist_img_path / filename

    if content_type == "image/gif" or img.format == "GIF":
        frames, duration = get_gif_frames(img)

        frames[0].save(
            full_img_path, "webp", save_all=True, append_images=frames[1:], duration=duration, loop=0
        )
        create_gif_thumbnail(img, img_name=filename)

        return filename

    img = crop_square(prepare_image(img))
    img.save(full_img_path, "webp")
    create_thumbnail(img, img_name=filename)

    return filename


def duplicate_images(images: list):
    if len(images) == 1:
        images *= 4
    elif len(images) == 2:
        images += list(reversed(images))
    elif len(images) == 3:
        images = images + images[:1]

    return images

# TODO: mutable var in param.
def get_first_4_images(
        tracks: list[Track] = [],
        trackhashes: list[str] = []
) -> list[dict["str", str]]:
    """
    Returns images of the first 4 albums that appear in the track list.

    When tracks are not passed, trackhashes need to be passed.
    Tracks are then resolved from the store.
    """
    if len(trackhashes) > 0:
        tracks = TrackStore.get_tracks_by_trackhashes(trackhashes)

    albums = []

    for track in tracks:
        if track.albumhash not in albums:
            albums.append(track.albumhash)

            if len(albums) == 4:
                break

    albums = AlbumStore.get_albums_by_hashes(albums)
    images = [
        {
            "image": album.image,
            "color": album.color,
        }
        for album in albums
    ]

    if len(images) == 4:
        return images

    return duplicate_images(images)



def cleanup_playlist_images() -> None:
    """
    Deletes the files of the playlist-img folder that no playlist uses.

    A playlist uses its image and the thumbnail of it (``thumb_`` + image).
    The playlists of every user count, not only the one of the current user.
    Only the files that are directly in the folder are looked at.
    """
    # Import here to avoid circular import
    from musix.db.userdata import PlaylistTable

    in_use: set[str] = set()

    for playlist in PlaylistTable.get_all(current_user=False):
        if playlist.image and playlist.image != "None":
            in_use.add(playlist.image)
            in_use.add("thumb_" + playlist.image)

    playlist_dir = settings.Paths().playlist_img_path

    if not playlist_dir.is_dir():
        return

    for file in playlist_dir.iterdir():
        # not stem: the table saves the name with the extension
        if not file.is_file() or file.name in in_use:
            continue

        try:
            file.unlink(missing_ok=True)
        except OSError as e:
            logger.exception("could not delete file", exc_info=e)
