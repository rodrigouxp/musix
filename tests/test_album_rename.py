import ast
import json
import sys
import time
from io import BytesIO
from pathlib import Path

import pytest
from flask_openapi3 import OpenAPI
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from PIL import Image
from tinytag import TinyTag

from musix.api import album as album_api
from musix.api import auth as auth_api
from musix.db.userdata import (
    AlbumTypeTable,
    CollectionTable,
    FavoritesTable,
    LibDataTable,
    PlaylistTable,
    ScrobbleTable,
)
from musix.lib import albumrename, artistrename, tagwriter
from musix.lib.tagwriter import embed_cover, read_tags
from musix.store.albums import AlbumStore
from musix.store.albumtypes import AlbumTypeStore
from musix.store.tracks import TrackStore
from musix.utils.hashing import create_hash

ARTIST = "Lucinha"


@pytest.fixture
def http(library, monkeypatch):
    monkeypatch.setattr(auth_api, "current_user", {"roles": ["admin"]})
    monkeypatch.setattr(tagwriter, "_default_config", lambda: library.env.config)
    monkeypatch.setattr(albumrename.AlbumJobState, "running", False)
    monkeypatch.setattr(artistrename.JobState, "running", False)

    app = OpenAPI(__name__)
    app.register_api(album_api.api)
    return app.test_client()


def preview(http, albumhash: str, title: str):
    return http.post(f"/album/{albumhash}/rename/preview", json={"title": title})


def rename(http, albumhash: str, title: str, confirm=True):
    return http.post(f"/album/{albumhash}/rename", json={"title": title, "confirm": confirm})


def wait_for_job(http, timeout=60):
    end = time.time() + timeout

    while time.time() < end:
        status = http.get("/album/rename/status").get_json()

        if status["finished"] or (not status["running"] and status["result"]):
            return status

        time.sleep(0.05)

    raise AssertionError("the rename did not finish")


def do_rename(http, albumhash: str, title: str):
    res = rename(http, albumhash, title)
    assert res.status_code == 202, res.get_json()
    return wait_for_job(http)


def journal(library) -> list[dict]:
    path = library.env.paths.config_dir / "rename-journal.jsonl"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def track_of(library, path: Path):
    return library.track(path)


def cover_bytes() -> bytes:
    out = BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(out, "JPEG")
    return out.getvalue()


def album_of(library, path: Path) -> str:
    return track_of(library, path).albumhash


def duration(path: Path) -> float:
    return TinyTag.get(path).duration


def tags_without_album(path: Path):
    tags = read_tags(path)
    return (tags.title, tags.artist, tags.albumartist, tags.artists, tags.covers, tags.others)


@pytest.fixture
def abbey(library):
    """
    An album of four tracks on two discs, and an album with the same title by another artist.
    """
    files = {}

    for disc, number in ((1, 1), (1, 2), (2, 1), (2, 2)):
        name = f"abbey/d{disc}t{number}.flac"
        files[(disc, number)] = library.add(
            "flac",
            name,
            title=f"Song {disc}-{number}",
            artist=ARTIST,
            album_artist=ARTIST,
            album="Abbey Road",
            track=str(number),
            disc=str(disc),
        )

    other = library.add(
        "flac",
        "other/hits.flac",
        title="Other Song",
        artist="Somebody Else",
        album_artist="Somebody Else",
        album="Abbey Road",
    )
    library.index()
    return {"files": files, "other": other}


# SECTION: the tags


@pytest.mark.parametrize("fmt", ["mp3", "flac", "m4a", "ogg", "opus"])
def test_the_title_changes_and_everything_else_stays(http, library, fmt):
    path = library.add(
        fmt,
        f"x.{fmt}",
        title="Song",
        artist=ARTIST,
        album_artist=ARTIST,
        album="Old Title",
        track="3",
        genre="Rock",
        comment="a comment",
    )
    embed_cover(path, cover_bytes(), "image/jpeg")
    library.index()
    old_hash = album_of(library, path)
    before = tags_without_album(path)
    length = duration(path)

    status = do_rename(http, old_hash, "New Title")

    assert status["result"]["files_failed"] == {}
    assert read_tags(path).album == "New Title"
    assert tags_without_album(path) == before
    assert read_tags(path).covers == before[4] != []
    assert abs(duration(path) - length) < 0.2
    assert album_of(library, path) == create_hash("New Title", ARTIST) == status["new_albumhash"]


def test_all_the_tracks_change_and_the_hashes_follow(http, library, abbey):
    files = abbey["files"]
    old_hash = album_of(library, files[(1, 1)])
    old_tracks = {k: track_of(library, p).trackhash for k, p in files.items()}
    new_title = "Let It Be"
    paths = library.env.paths

    FavoritesTable.insert_item({"type": "track", "hash": old_tracks[(1, 1)], "userid": 1, "extra": {}})
    FavoritesTable.insert_item({"type": "track", "hash": old_tracks[(2, 2)], "userid": 1, "extra": {}})
    FavoritesTable.insert_item({"type": "album", "hash": old_hash, "userid": 1, "extra": {}})
    ScrobbleTable.add(
        {"trackhash": old_tracks[(1, 1)], "duration": 30, "timestamp": 1, "source": "al:" + old_hash, "userid": 1, "extra": {}}
    )
    PlaylistTable.insert_one(
        {"name": "p", "last_updated": 1, "userid": 1, "settings": {}, "trackhashes": ["x", old_tracks[(1, 2)]]}
    )
    CollectionTable.insert_one(
        {"name": "c", "userid": 1, "items": [{"type": "album", "hash": old_hash}]}
    )
    AlbumTypeTable.set_kind(old_hash, "live album")
    AlbumTypeStore.set(old_hash, "live album")
    LibDataTable.insert_one(
        {"itemhash": "album" + old_hash, "itemtype": "album", "color": "rgb(4, 5, 6)", "extra": {}}
    )
    (paths.og_thumb_path / f"{old_hash}.webp").write_bytes(b"thumb")
    (paths.sm_thumb_path / f"{old_hash}.webp").write_bytes(b"thumb")

    status = do_rename(http, old_hash, new_title)

    assert status["result"]["files_ok"] == 4
    assert status["result"]["files_failed"] == {}
    assert status["result"]["album_moved"] is True

    new_hash = album_of(library, files[(1, 1)])
    assert new_hash != old_hash
    assert status["new_albumhash"] == new_hash

    for (disc, number), path in files.items():
        assert read_tags(path).album == new_title
        # the other tags are as they were
        assert read_tags(path).artist == [ARTIST]
        assert track_of(library, path).albumhash == new_hash
        assert track_of(library, path).trackhash != old_tracks[(disc, number)]
        assert track_of(library, path).disc == disc
        assert track_of(library, path).track == number

    new_tracks = {k: track_of(library, p).trackhash for k, p in files.items()}
    assert {(f.type, f.hash) for f in FavoritesTable.get_all()} == {
        ("track", new_tracks[(1, 1)]),
        ("track", new_tracks[(2, 2)]),
        ("album", new_hash),
    }
    assert {(s.trackhash, s.source) for s in ScrobbleTable.get_all(0, None, userid=1)} == {
        (new_tracks[(1, 1)], "al:" + new_hash)
    }
    assert list(PlaylistTable.get_all(current_user=False))[0].trackhashes == ["x", new_tracks[(1, 2)]]
    assert _collection_items() == [{"type": "album", "hash": new_hash}]
    assert AlbumTypeTable.get_all() == [(new_hash, "live album")]
    assert AlbumTypeStore.get(new_hash) == "live album"
    assert {r.itemhash for r in _libdata_rows()} == {"album" + new_hash}
    assert (paths.og_thumb_path / f"{new_hash}.webp").read_bytes() == b"thumb"
    assert not (paths.og_thumb_path / f"{old_hash}.webp").exists()

    assert old_hash not in AlbumStore.albummap
    assert AlbumStore.albummap[new_hash].album.og_title == new_title


def _collection_items():
    from sqlalchemy import select

    from musix.db.engine import DbEngine

    with DbEngine.manager() as conn:
        return conn.execute(select(CollectionTable.items)).scalar()


def _libdata_rows():
    from sqlalchemy import select

    from musix.db.engine import DbEngine

    with DbEngine.manager() as conn:
        return conn.execute(select(LibDataTable)).scalars().all()


def test_another_album_with_the_same_title_is_not_touched(http, library, abbey):
    other = abbey["other"]
    other_before = other.read_bytes()
    other_hash = album_of(library, other)
    mine = album_of(library, abbey["files"][(1, 1)])
    assert other_hash != mine

    do_rename(http, mine, "Something New")

    assert other.read_bytes() == other_before
    assert album_of(library, other) == other_hash
    assert read_tags(other).album == "Abbey Road"
    assert AlbumStore.albummap[other_hash].album.og_title == "Abbey Road"


def test_a_change_of_letter_case_changes_the_tag_and_not_the_hash(http, library):
    path = library.add("flac", "a.flac", title="T", artist=ARTIST, album_artist=ARTIST, album="abbey road")
    other = library.add("flac", "b.flac", title="U", artist=ARTIST, album_artist=ARTIST, album="abbey road")
    library.index()
    old_hash = album_of(library, path)
    FavoritesTable.insert_item({"type": "album", "hash": old_hash, "userid": 1, "extra": {}})

    body = preview(http, old_hash, "Abbey Road").get_json()
    assert body["hash_changes"] is False
    assert body["new_albumhash"] == old_hash

    status = do_rename(http, old_hash, "Abbey Road")

    assert status["result"]["files_failed"] == {}
    assert status["result"]["hash_changed"] is False
    assert status["result"]["album_moved"] is False
    assert status["new_albumhash"] == old_hash
    assert read_tags(path).album == "Abbey Road"
    assert read_tags(other).album == "Abbey Road"
    assert album_of(library, path) == old_hash
    assert [(f.type, f.hash) for f in FavoritesTable.get_all()] == [("album", old_hash)]


def test_the_new_title_can_become_an_album_that_exists_and_the_two_are_one(http, library):
    mine = library.add("flac", "a.flac", title="One", artist=ARTIST, album_artist=ARTIST, album="Album A")
    theirs = library.add("flac", "b.flac", title="Two", artist=ARTIST, album_artist=ARTIST, album="Album B")
    library.index()
    hash_a = album_of(library, mine)
    hash_b = album_of(library, theirs)
    FavoritesTable.insert_item({"type": "album", "hash": hash_a, "userid": 1, "extra": {}})
    FavoritesTable.insert_item({"type": "album", "hash": hash_b, "userid": 1, "extra": {}})
    CollectionTable.insert_one(
        {"name": "c", "userid": 1, "items": [{"type": "album", "hash": hash_a}, {"type": "album", "hash": hash_b}]}
    )

    body = preview(http, hash_a, "Album B").get_json()
    assert body["merge"] == {"title": "Album B", "albumhash": hash_b, "trackcount": 1}
    assert body["hash_changes"] is True
    assert body["new_albumhash"] == hash_b

    status = do_rename(http, hash_a, "Album B")

    assert status["new_albumhash"] == hash_b
    assert album_of(library, mine) == album_of(library, theirs) == hash_b
    assert hash_a not in AlbumStore.albummap
    assert len(AlbumStore.albummap[hash_b].trackhashes) == 2
    assert [(f.type, f.hash) for f in FavoritesTable.get_all()] == [("album", hash_b)]
    assert _collection_items() == [{"type": "album", "hash": hash_b}]


def test_the_hash_with_the_app_cleaning_titles_is_the_one_in_the_preview(http, library):
    library.env.config.mergeAlbums = True
    path = library.add(
        "flac", "a.flac", title="T", artist=ARTIST, album_artist=ARTIST, album="Abbey Road (Deluxe Edition)"
    )
    library.index()
    old_hash = album_of(library, path)

    body = preview(http, old_hash, "Let It Be (Super Deluxe Edition)").get_json()
    status = do_rename(http, old_hash, "Let It Be (Super Deluxe Edition)")

    # the app shows the clean title, the tag keeps all of it
    assert read_tags(path).album == "Let It Be (Super Deluxe Edition)"
    assert album_of(library, path) == body["new_albumhash"] == status["new_albumhash"]
    assert album_of(library, path) != old_hash
    assert AlbumStore.albummap[status["new_albumhash"]].album.title == "Let It Be"
    assert AlbumStore.albummap[status["new_albumhash"]].album.og_title == "Let It Be (Super Deluxe Edition)"


# SECTION: problems in the middle of an album


def test_a_failed_file_keeps_the_old_album_for_it_and_the_hash_does_not_move(http, library, monkeypatch):
    bad = library.add("flac", "bad.flac", title="Bad", artist=ARTIST, album_artist=ARTIST, album="Al")
    good = library.add("flac", "good.flac", title="Good", artist=ARTIST, album_artist=ARTIST, album="Al")
    library.index()
    old_hash = album_of(library, bad)
    bad_bytes = bad.read_bytes()
    FavoritesTable.insert_item({"type": "album", "hash": old_hash, "userid": 1, "extra": {}})

    real_write = albumrename.write_tags

    def flaky(path, *args, **kwargs):
        if Path(path).name == "bad.flac":
            raise tagwriter.TagWriteError("disk full")

        return real_write(path, *args, **kwargs)

    monkeypatch.setattr(albumrename, "write_tags", flaky)

    status = do_rename(http, old_hash, "New")
    result = status["result"]

    assert result["files_ok"] == 1
    assert list(result["files_failed"]) == [bad.as_posix()]
    assert "disk full" in result["files_failed"][bad.as_posix()]
    assert status["errors"] == result["files_failed"]
    assert bad.read_bytes() == bad_bytes
    assert read_tags(good).album == "New"
    assert result["album_moved"] is False
    # the old album stays, with the file that failed; its favorite stays with it
    assert album_of(library, bad) == old_hash
    assert album_of(library, good) != old_hash
    assert old_hash in AlbumStore.albummap
    assert [(f.type, f.hash) for f in FavoritesTable.get_all()] == [("album", old_hash)]


def test_a_file_without_the_album_tag_is_skipped_and_not_given_one(http, library):
    one = library.add("flac", "1.flac", title="One", artist=ARTIST, album_artist=ARTIST, album="Al")
    two = library.add("flac", "2.flac", title="Two", artist=ARTIST, album_artist=ARTIST, album="Al")
    three = library.add("mp3", "3.mp3", title="Three", artist=ARTIST, album_artist=ARTIST, album="Al")
    library.index()
    old_hash = album_of(library, one)

    audio = FLAC(two)
    del audio["album"]
    audio.save()
    tags = ID3(three)
    tags.delall("TALB")
    tags.save(v2_version=4)
    two_bytes, three_bytes = two.read_bytes(), three.read_bytes()

    body = preview(http, old_hash, "New").get_json()
    assert body["no_album_tag_count"] == 2
    assert body["files_to_rewrite"] == 1

    status = do_rename(http, old_hash, "New")

    assert read_tags(one).album == "New"
    assert two.read_bytes() == two_bytes
    assert three.read_bytes() == three_bytes
    assert read_tags(two).album is None
    assert read_tags(three).album is None
    assert set(status["result"]["files_failed"]) == {two.as_posix(), three.as_posix()}
    assert "no album tag" in status["result"]["files_failed"][two.as_posix()]
    assert status["result"]["album_moved"] is False
    assert old_hash in AlbumStore.albummap


def test_a_file_that_can_not_be_written_is_reported_and_the_others_go_on(http, library, monkeypatch):
    locked = library.add("flac", "locked.flac", title="L", artist=ARTIST, album_artist=ARTIST, album="Al")
    free = library.add("flac", "free.flac", title="F", artist=ARTIST, album_artist=ARTIST, album="Al")
    library.index()
    old_hash = album_of(library, free)
    real_access = albumrename.os.access

    monkeypatch.setattr(
        albumrename.os,
        "access",
        lambda p, mode, *a, **k: False if Path(p).name == "locked.flac" else real_access(p, mode, *a, **k),
    )

    body = preview(http, old_hash, "New").get_json()
    assert body["not_writable_count"] == 1
    assert body["not_writable"] == [locked.as_posix()]

    status = do_rename(http, old_hash, "New")

    assert read_tags(free).album == "New"
    assert read_tags(locked).album == "Al"
    assert "no permission" in status["result"]["files_failed"][locked.as_posix()]
    assert status["result"]["album_moved"] is False


def test_unsupported_files_fail_and_the_rest_goes_on(http, library):
    path = library.add("flac", "x.flac", title="T", artist=ARTIST, album_artist=ARTIST, album="Al")
    library.index()
    wav = library.env.root / "music" / "w.wav"
    import wave

    with wave.open(str(wav), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(8000)
        file.writeframes(b"\x00\x00" * 800)

    from musix.db.libdata import TrackTable
    from musix.lib.index import reload_stores
    from musix.lib.taglib import get_tags

    tags = get_tags(wav.as_posix(), config=library.env.config)
    tags["album"] = "Al"
    tags["artists"] = ARTIST
    tags["albumartists"] = ARTIST
    tags["albumhash"] = create_hash("Al", ARTIST)
    TrackTable.insert_one(tags)
    reload_stores()
    old_hash = album_of(library, path)

    body = preview(http, old_hash, "New").get_json()
    assert body["unsupported_count"] == 1

    status = do_rename(http, old_hash, "New")

    assert read_tags(path).album == "New"
    assert "unsupported format" in status["result"]["files_failed"][wav.as_posix()]


# SECTION: the text


@pytest.mark.parametrize(
    "title",
    [
        "Café — Édition spéciale",
        "Trilha 🎵 do Filme 🎬",
        'He said "hello" & she said \'bye\'',
        "Hits, Vol. 1, Deluxe",
        "日本語のアルバム",
    ],
)
@pytest.mark.parametrize("fmt", ["flac", "mp3", "m4a"])
def test_special_characters_and_commas_are_written_as_they_are(http, library, fmt, title):
    path = library.add(fmt, f"s.{fmt}", title="T", artist=ARTIST, album_artist=ARTIST, album="Plain")
    library.index()

    do_rename(http, album_of(library, path), title)

    assert read_tags(path).album == title
    assert TinyTag.get(path).album == title
    assert track_of(library, path).albumhash == create_hash(title, ARTIST)


# SECTION: the preview


def test_the_preview_writes_nothing_and_says_what_would_change(http, library, abbey):
    files = abbey["files"]
    before = {k: p.read_bytes() for k, p in files.items()}
    old_hash = album_of(library, files[(1, 1)])

    res = preview(http, old_hash, "  A New Title  ")

    assert res.status_code == 200
    body = res.get_json()
    assert body["current_title"] == "Abbey Road"
    assert body["new_title"] == "A New Title"
    assert body["album"]["albumartists"] == [ARTIST]
    assert body["files_total"] == body["tracks_count"] == 4
    assert body["files_to_rewrite"] == 4
    assert body["distinct_titles"] == ["Abbey Road"]
    assert body["hash_changes"] is True
    assert body["new_albumhash"] == create_hash("A New Title", ARTIST)
    assert body["merge"] is None
    assert len(body["samples"]) == 4
    assert body["samples"][0]["album_before"] == "Abbey Road"
    assert body["samples"][0]["album_after"] == "A New Title"

    assert {k: p.read_bytes() for k, p in files.items()} == before
    assert journal(library) == []
    assert album_of(library, files[(1, 1)]) == old_hash


def test_the_preview_shows_the_different_titles_the_files_have(http, library):
    one = library.add("flac", "1.flac", title="One", artist=ARTIST, album_artist=ARTIST, album="Abbey Road")
    two = library.add("flac", "2.flac", title="Two", artist=ARTIST, album_artist=ARTIST, album="abbey road")
    library.index()
    # the two spellings are the same album (the hash does not see the letter case)
    old_hash = album_of(library, one)
    assert album_of(library, two) == old_hash

    body = preview(http, old_hash, "Abbey Road").get_json()

    assert sorted(body["distinct_titles"]) == ["Abbey Road", "abbey road"]
    assert body["distinct_titles_count"] == 2
    assert body["files_to_rewrite"] == 1

    do_rename(http, old_hash, "Abbey Road")

    assert read_tags(one).album == read_tags(two).album == "Abbey Road"


def test_a_journal_line_for_each_file(http, library, abbey):
    old_hash = album_of(library, abbey["files"][(1, 1)])

    do_rename(http, old_hash, "Another")

    lines = journal(library)
    assert len(lines) == 4
    line = lines[0]
    assert line["action"] == "rename-album"
    assert line["album_old"] == "Abbey Road"
    assert line["album_new"] == "Another"
    assert line["albumhash_old"] == old_hash
    assert line["filepath"].endswith(".flac")


# SECTION: the routes


def test_confirm_is_needed(http, library, abbey):
    before = {k: p.read_bytes() for k, p in abbey["files"].items()}
    old_hash = album_of(library, abbey["files"][(1, 1)])

    res = rename(http, old_hash, "New", confirm=False)

    assert res.status_code == 400
    assert "confirm" in res.get_json()["error"]
    assert {k: p.read_bytes() for k, p in abbey["files"].items()} == before


@pytest.mark.parametrize("title", ["", "   ", "x" * 201, "two\nlines", "carriage\rreturn"])
def test_invalid_titles_are_400(http, library, abbey, title):
    old_hash = album_of(library, abbey["files"][(1, 1)])

    for route in (preview, rename):
        res = route(http, old_hash, title)

        assert res.status_code == 400, repr(title)
        assert res.get_json()["error"]


def test_the_same_title_is_400(http, library, abbey):
    old_hash = album_of(library, abbey["files"][(1, 1)])

    assert preview(http, old_hash, "Abbey Road").status_code == 400
    assert rename(http, old_hash, "Abbey Road").status_code == 400


def test_a_title_of_200_characters_is_accepted(http, library, abbey):
    old_hash = album_of(library, abbey["files"][(1, 1)])

    assert preview(http, old_hash, "x" * 200).status_code == 200


def test_unknown_album_is_404(http, library, abbey):
    assert preview(http, "0123456789abcdef", "Title").status_code == 404
    assert rename(http, "0123456789abcdef", "Title").status_code == 404


def test_only_one_job_at_a_time_in_the_whole_app(http, library, abbey, monkeypatch):
    old_hash = album_of(library, abbey["files"][(1, 1)])

    monkeypatch.setattr(albumrename.AlbumJobState, "running", True)
    res = rename(http, old_hash, "Another")
    assert res.status_code == 409
    assert "already running" in res.get_json()["error"]

    # an artist rename running stops an album rename too
    monkeypatch.setattr(albumrename.AlbumJobState, "running", False)
    monkeypatch.setattr(artistrename.JobState, "running", True)
    res = rename(http, old_hash, "Another")
    assert res.status_code == 409
    assert "artist rename is already running" in res.get_json()["error"]

    # and an album rename running stops an artist rename
    monkeypatch.setattr(artistrename.JobState, "running", False)
    monkeypatch.setattr(albumrename.AlbumJobState, "running", True)

    with pytest.raises(artistrename.RenameError) as error:
        artistrename.start_rename(create_hash(ARTIST, decode=True), "Someone", library.env.config)

    assert error.value.status == 409


def test_the_status_reports_the_progress(http, library, abbey):
    assert http.get("/album/rename/status").get_json()["running"] is False

    status = do_rename(http, album_of(library, abbey["files"][(1, 1)]), "Another")

    assert status["done"] == status["total"] == 4
    assert status["finished"] is True
    assert status["old_title"] == "Abbey Road"
    assert status["new_title"] == "Another"
    assert status["new_albumhash"] == create_hash("Another", ARTIST)


def test_the_routes_need_admin(http, library, abbey, monkeypatch):
    old_hash = album_of(library, abbey["files"][(1, 1)])
    monkeypatch.setattr(auth_api, "current_user", {"roles": []})

    assert preview(http, old_hash, "Another").status_code == 403
    assert rename(http, old_hash, "Another").status_code == 403


# SECTION: the modules


def test_the_new_modules_only_import_what_requirements_has():
    """
    The server image installs ``requirements.txt`` and nothing else (3.2.0 broke because a
    package was only in ``pyproject.toml``). Every package the rename code imports must be
    there.
    """
    root = Path(__file__).resolve().parent.parent
    requirements = {
        line.split("==")[0].split(">=")[0].strip().lower().replace("-", "_")
        for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    # the name of the module is not always the name of the package
    aliases = {"PIL": "pillow", "yaml": "pyyaml"}
    modules = ["albumrename.py", "renamecommon.py", "artistrename.py", "tagwriter.py", "trackrename.py", "rekey.py"]

    for module in modules:
        tree = ast.parse((root / "src" / "musix" / "lib" / module).read_text(encoding="utf-8"))
        names = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])

        for name in names - {"musix"} - set(sys.stdlib_module_names):
            package = aliases.get(name, name).lower().replace("-", "_")
            assert package in requirements, f"{module} imports {name}, which is not in requirements.txt"
