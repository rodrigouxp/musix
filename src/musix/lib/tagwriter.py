"""
Safe writing of tags into music files.

Everything that writes to a music file goes through this module (``write_tags``).
The app itself only reads tags (``taglib.py`` uses tinytag); writing uses mutagen.

How a write works, for each file:

1. the file is copied to a hidden temporary file in the same folder;
2. the tags are changed in the copy;
3. the copy is read again with mutagen and with tinytag (the reader of the app)
   and checked: the requested tags have the new values and no other tag changed;
4. only then ``os.replace`` puts the copy where the original was.

Any failure removes the copy and leaves the original untouched. The original
file is never opened for writing.

Only what is asked is written: the title, the album, the artist tags and the front
cover. A tag of an artist that the file did not have is never created (the app guesses
the album owner from the artist when ``ALBUMARTIST`` is missing, so creating the tag
would change the owner), and neither is the album tag (a file without it does not belong
to the album it is shown in), unless the caller names it in ``create_missing``.
"""

import base64
import hashlib
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TPE2, TXXX
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from tinytag import TinyTag

from musix.utils.hashing import create_hash
from musix.utils.parsers import split_artists

# extension -> kind
SUPPORTED_EXTENSIONS = {
    ".mp3": "mp3",
    ".flac": "flac",
    ".m4a": "mp4",
    ".mp4": "mp4",
    ".m4b": "mp4",
    ".ogg": "ogg",
    ".oga": "ogg",
    ".opus": "ogg",
}

ARTIST_FIELDS = ("artist", "albumartist", "artists")
FRONT_COVER = 3


class TagWriteError(Exception):
    """A file could not be written. The original file was not changed."""


class UnsupportedFormat(TagWriteError):
    """The file is not in one of the formats that can be written."""


class TagVerificationError(TagWriteError):
    """The copy did not read back as expected, so it was not used."""


# SECTION: artist elements


def artist_elements(value: str, config: Any) -> list[tuple[int, int]]:
    """
    The ``(start, end)`` position of each artist inside a tag string.

    Splits exactly like ``split_artists`` (same separators, same exceptions such
    as "AC/DC", and the same comma rule), so the elements here are the artists the
    app sees. The positions let a name be swapped without touching the
    separators and spaces around it.
    """
    separators = sorted((s for s in config.artistSeparators if s), key=len, reverse=True)
    ignore = list(config.artistSplitIgnoreList)
    lower = value.lower()
    spans: list[tuple[int, int]] = []
    chunk_start = 0
    i = 0

    def flush(start: int, end: int):
        # a chunk is split on commas and each piece is stripped
        position = start
        for piece in value[start:end].split(","):
            stripped = piece.strip()

            if stripped:
                begin = position + (len(piece) - len(piece.lstrip()))
                spans.append((begin, begin + len(stripped)))

            position += len(piece) + 1

    while i < len(value):
        ignored = next((ig for ig in ignore if lower.startswith(ig.lower(), i)), None)

        if ignored:
            flush(chunk_start, i)
            spans.append((i, i + len(ignored)))
            i += len(ignored)
            chunk_start = i
            continue

        separator = next((s for s in separators if lower.startswith(s.lower(), i)), None)

        if separator:
            flush(chunk_start, i)
            i += len(separator)
            chunk_start = i
            continue

        i += 1

    flush(chunk_start, len(value))
    return spans


def split_elements(values: Iterable[str], config: Any) -> list[str]:
    """
    The artists of a tag, as the text of each element, in order.
    """
    names: list[str] = []

    for value in values:
        names.extend(value[a:b] for a, b in artist_elements(value, config))

    return names


def _element_hash(name: str) -> str:
    # the same hash the app gives an artist (see ``Track.split_artists``)
    return create_hash(name, decode=True)


def replace_artist_element(
    tag_value: list[str], old_hash: str, new_name: str, config: Any = None
) -> list[str]:
    """
    Swaps one artist of an artist tag for another, element by element.

    ``tag_value`` is the tag as it is stored: the list of its values. A Vorbis
    tag with several ``ARTIST`` lines has several values; most files have one
    string such as ``"Lucinha; The Rolling Stones"``.

    Each element whose ``create_hash`` is ``old_hash`` becomes ``new_name``. Text is
    never replaced inside a name ("Stones" does not touch "Rolling Stones"), the
    other elements keep their text and order, and the separators and spaces
    between elements stay as they were. The number of values and elements never
    shrinks, except for one case: a tag can not name the same artist twice, so if
    ``new_name`` ends up more than once in the tag, only the first one stays (and it
    is written exactly as ``new_name``).
    """
    config = config or _default_config()
    new_hash = _element_hash(new_name)
    targets = (old_hash, new_hash)
    result: list[str] = []
    seen_new = False

    for value in tag_value:
        spans = artist_elements(value, config)
        kept: list[int] = []
        texts: dict[int, str] = {}

        for index, (a, b) in enumerate(spans):
            if _element_hash(value[a:b]) in targets:
                if seen_new:
                    continue  # a repeat of the new name: dropped

                seen_new = True
                texts[index] = new_name

            kept.append(index)

        if not spans:
            result.append(value)
            continue

        if not kept:
            continue  # every element of this value was a repeat

        # rebuild the string: the text before the first element and after the last
        # one stay, and each kept element comes with the separator that was before it
        out = value[: spans[0][0]]

        for position, index in enumerate(kept):
            a, b = spans[index]

            if position:
                out += value[spans[index - 1][1] : a]

            out += texts.get(index, value[a:b])

        result.append(out + value[spans[-1][1] :])

    return result


def append_artists(tag_value: list[str], names: list[str], config: Any = None) -> list[str]:
    """
    Adds artists to an artist tag, skipping the ones that are already in it.
    A tag stored as several values gets new values; a tag stored as one string gets
    the names joined with "; " (the default separator).
    """
    config = config or _default_config()
    present = {_element_hash(n) for n in split_elements(tag_value, config)}
    new: list[str] = []

    for name in names:
        if _element_hash(name) not in present:
            present.add(_element_hash(name))
            new.append(name)

    if not new:
        return list(tag_value)

    if len(tag_value) > 1:
        return [*tag_value, *new]

    if not tag_value:
        return ["; ".join(new)]

    return ["; ".join([tag_value[0], *new])]


def assert_artists_preserved(
    before: list[str] | None,
    after: list[str] | None,
    old_hash: str,
    new_name: str,
    config: Any = None,
):
    """
    Checks an artist tag after ``old_hash`` was renamed to ``new_name``.

    Raises ``TagVerificationError`` unless: every element that was not the old
    artist (and not the new name) is still there, with the same text and in the
    same order; the old artist became the new name, exactly once and in the
    place the first one was; and nothing else was added or removed.
    """
    config = config or _default_config()
    new_hash = _element_hash(new_name)

    if before is None and after is None:
        return

    if before is None or after is None:
        raise TagVerificationError("an artist tag was created or removed")

    before_names = split_elements(before, config)
    after_names = split_elements(after, config)

    def is_target(name: str) -> bool:
        return _element_hash(name) in (old_hash, new_hash)

    def others(names: list[str]) -> list[str]:
        return [n for n in names if not is_target(n)]

    if others(before_names) != others(after_names):
        raise TagVerificationError(
            "an artist of the tag was lost, changed or moved: "
            f"{before_names!r} -> {after_names!r}"
        )

    targets_before = [n for n in before_names if is_target(n)]
    targets_after = [n for n in after_names if is_target(n)]

    if targets_before and targets_after != [new_name]:
        raise TagVerificationError(
            f"the new name should be in the tag exactly once: {after_names!r}"
        )

    if not targets_before and targets_after:
        raise TagVerificationError(f"an artist was added to the tag: {after_names!r}")

    if targets_before:
        # the new name takes the place of the first old artist
        def rank(names: list[str]) -> int:
            position = next(i for i, n in enumerate(names) if is_target(n))
            return len(others(names[:position]))

        if rank(before_names) != rank(after_names):
            raise TagVerificationError(
                f"the new name is not in the place of the old one: {after_names!r}"
            )


def _default_config():
    from musix.config import UserConfig

    return UserConfig()


# SECTION: reading


@dataclass
class TagSnapshot:
    """
    What is in a file that matters here. The artist fields are the raw values as
    stored (``None`` when the file does not have the tag).
    """

    title: str | None = None
    # the raw text of the album tag (``None`` when the file does not have the tag)
    album: str | None = None
    artist: list[str] | None = None
    albumartist: list[str] | None = None
    artists: list[str] | None = None
    # md5 of each front cover picture, in order
    covers: list[str] = field(default_factory=list)
    # every other tag, in a comparable form
    others: dict[str, Any] = field(default_factory=dict)


def _kind_of(path: Path) -> str:
    kind = SUPPORTED_EXTENSIONS.get(path.suffix.lower())

    if kind is None:
        raise UnsupportedFormat(f"unsupported format: {path.suffix or path.name}")

    return kind


def _open(path: Path):
    """
    Opens the file with the right mutagen class. Returns an adapter.
    """
    kind = _kind_of(path)

    try:
        if kind == "mp3":
            return _Id3Adapter(path)

        if kind == "mp4":
            return _Mp4Adapter(path)

        audio = mutagen.File(path)

        if kind == "ogg" and not isinstance(audio, (OggVorbis, OggOpus)):
            raise UnsupportedFormat("unsupported format: this Ogg file is not Vorbis or Opus")

        return _VorbisAdapter(path, audio)
    except TagWriteError:
        raise
    except Exception as error:
        raise TagWriteError(f"could not read the tags: {error}") from error


def read_tags(path: str | Path) -> TagSnapshot:
    """
    Reads the tags of a file as ``write_tags`` sees them.
    """
    adapter = _open(Path(path))
    return adapter.snapshot()


# SECTION: adapters


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


class _Adapter:
    """
    One per format. ``get_*`` give the raw list of values (or ``None`` when the
    tag does not exist); ``set_*`` replace them.
    """

    def __init__(self, path: Path):
        self.path = path

    # the artist tags, by name
    def get(self, name: str) -> list[str] | None:
        raise NotImplementedError

    def set(self, name: str, values: list[str]):
        raise NotImplementedError

    def set_cover(self, data: bytes, mime: str):
        raise NotImplementedError

    def covers(self) -> list[str]:
        raise NotImplementedError

    def others(self) -> dict[str, Any]:
        raise NotImplementedError

    def save(self):
        raise NotImplementedError

    def snapshot(self) -> TagSnapshot:
        title = self.get("title")
        album = self.get("album")

        return TagSnapshot(
            title=title[0] if title else None,
            album=album[0] if album else None,
            artist=self.get("artist"),
            albumartist=self.get("albumartist"),
            artists=self.get("artists"),
            covers=self.covers(),
            others=self.others(),
        )


class _Id3Adapter(_Adapter):
    _FRAMES = {
        "title": "TIT2",
        "album": "TALB",
        "artist": "TPE1",
        "albumartist": "TPE2",
        "artists": "TXXX:ARTISTS",
    }

    def __init__(self, path: Path):
        super().__init__(path)
        self.audio = mutagen.File(path, easy=False)

        if self.audio is None or not hasattr(self.audio, "tags"):
            raise UnsupportedFormat("unsupported format: not an MP3 file")

        if self.audio.tags is None:
            self.audio.add_tags()

        self.tags: ID3 = self.audio.tags

    def get(self, name: str) -> list[str] | None:
        frame = self.tags.get(self._FRAMES[name])
        return [str(t) for t in frame.text] if frame is not None else None

    def set(self, name: str, values: list[str]):
        key = self._FRAMES[name]
        old = self.tags.get(key)
        encoding = old.encoding if old is not None else 3

        # Latin-1 can not hold every name
        if encoding == 0 and not all(_fits_latin1(v) for v in values):
            encoding = 1 if self._v23() else 3

        if key.startswith("TXXX:"):
            frame = TXXX(encoding=encoding, desc=key.split(":", 1)[1], text=values)
        elif name == "title":
            frame = TIT2(encoding=encoding, text=values)
        elif name == "album":
            frame = TALB(encoding=encoding, text=values)
        elif name == "artist":
            frame = TPE1(encoding=encoding, text=values)
        else:
            frame = TPE2(encoding=encoding, text=values)

        self.tags.add(frame)  # replaces the frame with the same key

    def _v23(self) -> bool:
        return tuple(self.tags.version[:2]) == (2, 3)

    def set_cover(self, data: bytes, mime: str):
        for key in [k for k, f in self.tags.items() if isinstance(f, APIC) and f.type == FRONT_COVER]:
            del self.tags[key]

        self.tags.add(APIC(encoding=3, mime=mime, type=FRONT_COVER, desc="", data=data))

    def covers(self) -> list[str]:
        return [_md5(f.data) for f in self.tags.getall("APIC") if f.type == FRONT_COVER]

    def others(self) -> dict[str, Any]:
        skip = set(self._FRAMES.values())
        result: dict[str, Any] = {}

        for key, frame in self.tags.items():
            if key in skip or (isinstance(frame, APIC) and frame.type == FRONT_COVER):
                continue

            values = []
            for spec in getattr(frame, "_framespec", []):
                value = getattr(frame, spec.name, None)
                values.append(_md5(value) if isinstance(value, bytes) and len(value) > 64 else repr(value))

            result[key] = tuple(values) or repr(frame)

        return result

    def save(self):
        # keep a v2.3 tag as v2.3
        version = 3 if self._v23() else 4
        self.audio.save(v2_version=version)


def _fits_latin1(text: str) -> bool:
    try:
        text.encode("latin-1")
        return True
    except UnicodeEncodeError:
        return False


class _VorbisAdapter(_Adapter):
    """
    FLAC, Ogg Vorbis and Opus: Vorbis comments.
    """

    _KEYS = {
        "title": "title",
        "album": "album",
        "artist": "artist",
        "albumartist": "albumartist",
        "artists": "artists",
    }

    def __init__(self, path: Path, audio: Any):
        super().__init__(path)

        if audio is None:
            raise UnsupportedFormat("unsupported format: could not read the file")

        self.audio = audio

        if self.audio.tags is None:
            self.audio.add_tags()

        self.tags = self.audio.tags
        self.is_flac = isinstance(audio, FLAC)

    def get(self, name: str) -> list[str] | None:
        values = self.tags.get(self._KEYS[name])
        return [str(v) for v in values] if values else None

    def set(self, name: str, values: list[str]):
        self.tags[self._KEYS[name]] = values

    def _pictures(self) -> list[Picture]:
        if self.is_flac:
            return list(self.audio.pictures)

        pictures = []
        for raw in self.tags.get("metadata_block_picture", []):
            try:
                pictures.append(Picture(base64.b64decode(raw)))
            except Exception:
                continue

        return pictures

    def set_cover(self, data: bytes, mime: str):
        picture = Picture()
        picture.type = FRONT_COVER
        picture.mime = mime
        picture.desc = ""
        picture.data = data

        try:
            from PIL import Image
            from io import BytesIO

            with Image.open(BytesIO(data)) as img:
                picture.width, picture.height = img.size
                picture.depth = {"RGB": 24, "RGBA": 32, "L": 8, "P": 8}.get(img.mode, 24)
        except Exception:
            pass

        if self.is_flac:
            keep = [p for p in self.audio.pictures if p.type != FRONT_COVER]
            self.audio.clear_pictures()

            for p in keep:
                self.audio.add_picture(p)

            self.audio.add_picture(picture)
            return

        keep_raw = []
        for raw in self.tags.get("metadata_block_picture", []):
            try:
                if Picture(base64.b64decode(raw)).type != FRONT_COVER:
                    keep_raw.append(raw)
            except Exception:
                keep_raw.append(raw)

        keep_raw.append(base64.b64encode(picture.write()).decode("ascii"))
        self.tags["metadata_block_picture"] = keep_raw

    def covers(self) -> list[str]:
        return [_md5(p.data) for p in self._pictures() if p.type == FRONT_COVER]

    def others(self) -> dict[str, Any]:
        skip = set(self._KEYS.values()) | {"metadata_block_picture"}
        result: dict[str, Any] = {}

        for key, value in self.tags:
            if key.lower() in skip:
                continue

            result.setdefault(key.lower(), []).append(value)

        for index, p in enumerate(self._pictures()):
            if p.type != FRONT_COVER:
                result[f"picture:{index}"] = (p.type, p.mime, p.desc, _md5(p.data))

        return result

    def save(self):
        self.audio.save()


class _Mp4Adapter(_Adapter):
    _KEYS = {
        "title": "\xa9nam",
        "album": "\xa9alb",
        "artist": "\xa9ART",
        "albumartist": "aART",
        "artists": "----:com.apple.iTunes:ARTISTS",
    }

    def __init__(self, path: Path):
        super().__init__(path)
        self.audio = MP4(path)

        if self.audio.tags is None:
            self.audio.add_tags()

        self.tags = self.audio.tags

    def get(self, name: str) -> list[str] | None:
        values = self.tags.get(self._KEYS[name])

        if not values:
            return None

        return [v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v) for v in values]

    def set(self, name: str, values: list[str]):
        key = self._KEYS[name]

        if key.startswith("----:"):
            self.tags[key] = [MP4FreeForm(v.encode("utf-8")) for v in values]
        else:
            self.tags[key] = values

    def set_cover(self, data: bytes, mime: str):
        fmt = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
        self.tags["covr"] = [MP4Cover(data, imageformat=fmt)]

    def covers(self) -> list[str]:
        return [_md5(bytes(c)) for c in self.tags.get("covr", [])]

    def others(self) -> dict[str, Any]:
        skip = set(self._KEYS.values()) | {"covr"}
        result: dict[str, Any] = {}

        for key, value in self.tags.items():
            if key in skip:
                continue

            result[key] = repr([bytes(v) if isinstance(v, bytes) else v for v in value])

        return result

    def save(self):
        self.audio.save()


# SECTION: writing


@dataclass
class TagChanges:
    """
    What to write. ``None`` means "leave it".

    The artist fields are the new raw values of the tag (see ``replace_artist_element``).
    ``album`` is the new text of the album tag. ``cover`` is ``(image bytes, mime type)``.
    """

    title: str | None = None
    album: str | None = None
    artist: list[str] | None = None
    albumartist: list[str] | None = None
    artists: list[str] | None = None
    cover: tuple[bytes, str] | None = None


def _tmp_path(path: Path) -> Path:
    # hidden (the scanner and the watcher skip dotfiles) and ending in the same
    # extension, so the format is recognised
    return path.with_name(f".{path.stem}.musix-{uuid.uuid4().hex[:8]}{path.suffix}")


def write_tags(
    path: str | Path,
    changes: TagChanges,
    *,
    create_missing: Iterable[str] = (),
    swap: tuple[str, str] | None = None,
    config: Any = None,
) -> TagSnapshot:
    """
    Writes ``changes`` into a music file, safely (see the top of this module).

    :param create_missing: tags (``"artist"``, ``"albumartist"``, ``"artists"``,
        ``"album"``) that may be created if the file does not have them. Without it, a
        change to a tag the file does not have is skipped.
    :param swap: ``(old_hash, new_name)`` of an artist rename; the artist tags are
        then also checked with ``assert_artists_preserved`` after the write.
    :returns: the tags of the file after the write
    :raises TagWriteError: the file was not changed
    """
    original = Path(path)
    create_missing = set(create_missing)
    _kind_of(original)

    if not original.is_file():
        raise TagWriteError(f"file not found: {original}")

    if not os.access(original, os.W_OK):
        raise TagWriteError("no permission to write this file")

    before = read_tags(original)
    duration_before = _tinytag_duration(original)
    tmp = _tmp_path(original)

    try:
        shutil.copyfile(original, tmp)
        shutil.copymode(original, tmp)

        adapter = _open(tmp)
        expected = _apply(adapter, before, changes, create_missing)
        adapter.save()

        _verify(tmp, before, expected, changes, swap, duration_before, config)
        os.replace(tmp, original)
    except TagWriteError:
        raise
    except Exception as error:
        raise TagWriteError(f"could not write the tags: {error}") from error
    finally:
        tmp.unlink(missing_ok=True)

    return read_tags(original)


def _apply(
    adapter: _Adapter, before: TagSnapshot, changes: TagChanges, create_missing: set[str]
) -> dict[str, Any]:
    """
    Changes the copy. Returns what each touched field should read back as.
    """
    expected: dict[str, Any] = {}

    if changes.title is not None:
        adapter.set("title", [changes.title])
        expected["title"] = changes.title

    # the album tag of a file that has none is not created (see the top of this module)
    if changes.album is not None and (before.album is not None or "album" in create_missing):
        adapter.set("album", [changes.album])
        expected["album"] = changes.album

    for name in ARTIST_FIELDS:
        values = getattr(changes, name)

        if values is None:
            continue

        if getattr(before, name) is None and name not in create_missing:
            continue

        adapter.set(name, list(values))
        expected[name] = list(values)

    if changes.cover is not None:
        data, mime = changes.cover
        adapter.set_cover(data, mime)
        expected["cover"] = _md5(data)

    return expected


def _verify(
    tmp: Path,
    before: TagSnapshot,
    expected: dict[str, Any],
    changes: TagChanges,
    swap: tuple[str, str] | None,
    duration_before: float | None,
    config: Any,
):
    """
    Reads the copy again and checks it. Raises ``TagVerificationError``.
    """
    config = config or _default_config()
    after = read_tags(tmp)

    if after.others != before.others:
        changed = sorted(
            k
            for k in set(after.others) | set(before.others)
            if after.others.get(k) != before.others.get(k)
        )
        raise TagVerificationError(f"other tags changed: {changed}")

    for name in ("title", "album", *ARTIST_FIELDS):
        wanted = expected.get(name)

        if wanted is None:
            if getattr(after, name) != getattr(before, name):
                raise TagVerificationError(f"the {name} tag changed without being asked to")

            continue

        if getattr(after, name) != wanted:
            raise TagVerificationError(f"the {name} tag did not read back as written")

    if "cover" in expected:
        if expected["cover"] not in after.covers:
            raise TagVerificationError("the cover did not read back as written")

        if before.covers and after.covers != [expected["cover"]]:
            raise TagVerificationError("the old front cover is still in the file")
    elif after.covers != before.covers:
        raise TagVerificationError("the cover changed without being asked to")

    if swap is not None:
        old_hash, new_name = swap

        for name in ARTIST_FIELDS:
            assert_artists_preserved(
                getattr(before, name), getattr(after, name), old_hash, new_name, config
            )

    _verify_with_tinytag(tmp, after, duration_before, config)


def _tinytag_duration(path: Path) -> float | None:
    try:
        return TinyTag.get(path).duration
    except Exception:
        return None


def _verify_with_tinytag(path: Path, after: TagSnapshot, duration_before: float | None, config: Any):
    """
    Reads the copy with the reader the app uses and checks it agrees.
    """
    try:
        tags = TinyTag.get(path)
    except Exception as error:
        raise TagVerificationError(f"the app could not read the new file: {error}") from error

    if after.title is not None and tags.title != after.title:
        raise TagVerificationError("the app reads a different title")

    if after.album is not None and tags.album != after.album:
        raise TagVerificationError("the app reads a different album")

    all_tags = tags.as_dict()

    def hashes(values: Iterable[str]) -> set[str]:
        return {_element_hash(n) for n in split_elements(values, config)}

    def read(name: str) -> list[str]:
        return [v for v in (all_tags.get(name) or []) if isinstance(v, str)]

    # some readers (tinytag among them) also put the ARTISTS tag into the artist
    if after.artist is not None:
        wanted = hashes(after.artist)
        allowed = wanted | hashes(after.artists or [])
        got = hashes(read("artist"))

        if not wanted <= got <= allowed:
            raise TagVerificationError("the app reads different artists in artist")

    if after.albumartist is not None and hashes(read("albumartist")) != hashes(after.albumartist):
        raise TagVerificationError("the app reads different artists in albumartist")

    if duration_before is not None and tags.duration is not None:
        if abs(tags.duration - duration_before) > 0.2:
            raise TagVerificationError("the length of the audio changed")


# SECTION: cover

COVER_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def embed_cover(path: str | Path, data: bytes, mime: str) -> TagSnapshot:
    """
    Saves a picture as the front cover of a file (see ``write_tags``).
    """
    return write_tags(path, TagChanges(cover=(data, mime)))
