import json
import wave
from pathlib import Path

import pytest
from flask_openapi3 import OpenAPI

from musix.api import auth as auth_api
from musix.api import track as track_api
from musix.db.libdata import TrackTable
from musix.db.userdata import (
    FavoritesTable,
    PlaylistTable,
    ScrobbleTable,
    UserTable,
)
from musix.lib import tagwriter
from musix.lib.index import reload_stores
from musix.lib.tagwriter import read_tags
from musix.lib.taglib import get_tags
from musix.lib.trackrename import (
    RenameError,
    sanitize_filename,
    safe_rename,
)
from musix.store.tracks import TrackStore


@pytest.fixture
def library(app_env, make_audio):
    """
    Makes music files and indexes them, the way the scanner does.
    """
    files: list[Path] = []

    class Library:
        env = app_env

        @staticmethod
        def add(fmt: str, name: str | None = None, **tags: str) -> Path:
            path = make_audio(fmt, name, **tags)
            files.append(path)
            return path

        @staticmethod
        def index():
            TrackTable.reset()

            for path in files:
                TrackTable.insert_one(get_tags(path.as_posix(), config=app_env.config))

            reload_stores()

        @staticmethod
        def track(path: Path):
            found = TrackStore.get_tracks_by_filepaths([path.as_posix()])
            return found[0] if found else None

    UserTable.insert_one({"username": "admin", "password": "x", "roles": ["admin"]})
    return Library


@pytest.fixture
def http(library, monkeypatch):
    monkeypatch.setattr(auth_api, "current_user", {"roles": ["admin"]})
    monkeypatch.setattr(tagwriter, "_default_config", lambda: library.env.config)

    app = OpenAPI(__name__)
    app.register_api(track_api.api)
    return app.test_client()


def rename(http, path: Path, title: str):
    return http.post("/track/rename", json={"filepath": path.as_posix(), "title": title})


def journal(library) -> list[dict]:
    path = library.env.paths.config_dir / "rename-journal.jsonl"

    if not path.exists():
        return []

    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# SECTION: file names


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Plain title", "Plain title.mp3"),
        ('A<B>C:D"E/F\\G|H?I*J', "A_B_C_D_E_F_G_H_I_J.mp3"),
        ("tab\there\x00nul\x1f", "tab_here_nul_.mp3"),
        ("Ends with dots...", "Ends with dots.mp3"),
        ("Ends with spaces   ", "Ends with spaces.mp3"),
        ("What?", "What_.mp3"),
        ("...", "_.mp3"),
        ("???", "___.mp3"),
        ("CON", "CON_.mp3"),
        ("con", "con_.mp3"),
        ("Lpt9", "Lpt9_.mp3"),
        ("COM1", "COM1_.mp3"),
        ("com5.live", "com5_.live.mp3"),
        ("CONSOLE", "CONSOLE.mp3"),
        (".hidden", "_.hidden.mp3"),
        ("$weird", "_$weird.mp3"),
        ("Ça va? Été — ünï", "Ça va_ Été — ünï.mp3"),
    ],
)
def test_sanitize_filename(title, expected):
    assert sanitize_filename(title, ".mp3") == expected


def test_a_long_title_fits_in_255_bytes():
    name = sanitize_filename("é" * 200, ".flac")

    assert len(name.encode("utf-8")) <= 255
    assert name.endswith(".flac")
    assert name.startswith("é")

    ascii_name = sanitize_filename("a" * 400, ".mp3")
    assert len(ascii_name.encode("utf-8")) == 255


def test_safe_rename_never_replaces_a_file(tmp_path):
    one = tmp_path / "one.txt"
    two = tmp_path / "two.txt"
    one.write_text("one")
    two.write_text("two")

    with pytest.raises(FileExistsError):
        safe_rename(one, two)

    assert one.read_text() == "one"
    assert two.read_text() == "two"

    safe_rename(one, tmp_path / "three.txt")
    assert not one.exists()
    assert (tmp_path / "three.txt").read_text() == "one"


def test_safe_rename_allows_a_change_of_letter_case(tmp_path):
    path = tmp_path / "song.txt"
    path.write_text("x")

    safe_rename(path, tmp_path / "SONG.txt")

    assert sorted(p.name for p in tmp_path.iterdir()) == ["SONG.txt"]


# SECTION: the route


@pytest.mark.parametrize("fmt", ["mp3", "flac", "m4a", "ogg", "opus"])
def test_rename_writes_tag_and_file_with_the_same_text(http, library, fmt):
    path = library.add(
        fmt, f"01 - Old name.{fmt}", title="Old title", artist="Lucinha", album="Album", album_artist="Lucinha"
    )
    library.index()
    old_hash = library.track(path).trackhash

    res = rename(http, path, "  A New Title  ")

    assert res.status_code == 200
    body = res.get_json()
    new_path = path.with_name(f"A New Title.{fmt}")
    assert body["ok"] is True
    assert body["old_trackhash"] == old_hash
    assert body["new_trackhash"] != old_hash
    assert body["track"]["title"] == "A New Title"
    assert body["track"]["filepath"] == new_path.as_posix()
    assert body["track"]["trackhash"] == body["new_trackhash"]

    # the same text in the tag and in the name of the file
    assert not path.exists()
    assert new_path.exists()
    assert read_tags(new_path).title == "A New Title"
    assert sorted(p.name for p in new_path.parent.iterdir()) == [new_path.name]

    # the stores know the new track and not the old one
    assert library.track(new_path).trackhash == body["new_trackhash"]
    assert old_hash not in TrackStore.trackhashmap

    lines = journal(library)
    assert len(lines) == 1
    assert lines[0]["filepath_old"] == path.as_posix()
    assert lines[0]["filepath_new"] == new_path.as_posix()
    assert lines[0]["title_old"] == "Old title"
    assert lines[0]["title_new"] == "A New Title"


def test_invalid_characters_become_underscores_in_the_name_only(http, library):
    path = library.add("mp3", "song.mp3", title="Old", artist="Lucinha", album="Album")
    library.index()

    res = rename(http, path, 'Why: "this" / that?')

    assert res.status_code == 200
    new_path = path.with_name("Why_ _this_ _ that_.mp3")
    assert new_path.exists()
    # the tag has exactly what was typed
    assert read_tags(new_path).title == 'Why: "this" / that?'


def test_409_when_the_name_is_taken_and_nothing_changes(http, library):
    path = library.add("flac", "one.flac", title="One", artist="A", album="B")
    other = library.add("flac", "Taken.flac", title="Other", artist="A", album="B")
    library.index()
    before = path.read_bytes()
    other_before = other.read_bytes()
    old_hash = library.track(path).trackhash

    res = rename(http, path, "Taken")

    assert res.status_code == 409
    assert "Taken.flac" in res.get_json()["error"]
    assert path.read_bytes() == before
    assert other.read_bytes() == other_before
    assert library.track(path).trackhash == old_hash
    assert journal(library) == []


def test_favorite_plays_and_playlist_follow_the_track(http, library):
    path = library.add("mp3", "song.mp3", title="Old", artist="Lucinha", album="Album")
    library.index()
    old_hash = library.track(path).trackhash
    FavoritesTable.insert_item({"type": "track", "hash": old_hash, "userid": 1, "extra": {}})
    ScrobbleTable.add(
        {"trackhash": old_hash, "duration": 30, "timestamp": 1, "source": "tr:" + old_hash, "userid": 1, "extra": {}}
    )
    ScrobbleTable.add(
        {"trackhash": old_hash, "duration": 30, "timestamp": 2, "source": "al:albumhash", "userid": 1, "extra": {}}
    )
    PlaylistTable.insert_one(
        {
            "name": "mine",
            "last_updated": 1,
            "userid": 1,
            "settings": {},
            "trackhashes": ["before", old_hash, "after"],
        }
    )

    res = rename(http, path, "Brand New")

    new_hash = res.get_json()["new_trackhash"]
    assert new_hash != old_hash
    assert [f.hash for f in FavoritesTable.get_all()] == [new_hash]
    scrobbles = list(ScrobbleTable.get_all(0, None, userid=1))
    assert {s.trackhash for s in scrobbles} == {new_hash}
    assert {s.source for s in scrobbles} == {"tr:" + new_hash, "al:albumhash"}
    assert list(PlaylistTable.get_all(current_user=False))[0].trackhashes == ["before", new_hash, "after"]
    # and the stores in memory have them on the new hash
    track = TrackStore.trackhashmap[new_hash].tracks[0]
    assert 1 in track.fav_userids
    assert track.playcount == 2


def test_a_favorite_that_already_exists_on_the_new_hash_is_joined(http, library):
    one = library.add("mp3", "one.mp3", title="One", artist="Lucinha", album="Album")
    two = library.add("mp3", "two.mp3", title="Two", artist="Lucinha", album="Album")
    library.index()
    one_hash = library.track(one).trackhash
    two_hash = library.track(two).trackhash
    FavoritesTable.insert_item({"type": "track", "hash": one_hash, "userid": 1, "extra": {}})
    FavoritesTable.insert_item({"type": "track", "hash": two_hash, "userid": 1, "extra": {}})
    PlaylistTable.insert_one(
        {"name": "p", "last_updated": 1, "userid": 1, "settings": {}, "trackhashes": [one_hash, two_hash]}
    )

    # "One" is renamed "Two" (in another folder name, so no file clash)
    (one.parent / "sub").mkdir()
    res = rename(http, one, "Two!")
    assert res.status_code == 200
    # "Two!" has a different hash than "Two", so make the clash by hash directly
    from musix.lib.rekey import rekey_hash

    new_hash = res.get_json()["new_trackhash"]
    rekey_hash("track", new_hash, two_hash)

    assert [f.hash for f in FavoritesTable.get_all()] == [two_hash]
    assert list(PlaylistTable.get_all(current_user=False))[0].trackhashes == [two_hash]


def test_the_feat_part_of_the_old_title_goes_to_the_artist_tag(http, library):
    path = library.add(
        "flac",
        "song.flac",
        title="Song (feat. Mick)",
        artist="Lucinha",
        album="Album",
        album_artist="Lucinha",
    )
    library.index()
    track = library.track(path)
    assert [a["name"] for a in track.artists] == ["Lucinha", "Mick"]
    assert track.title.strip() == "Song"
    albumhash = track.albumhash
    old_hash = track.trackhash

    # the field starts with the title on the screen: "Song"
    res = rename(http, path, "Song (Live)")

    assert res.status_code == 200
    new_path = path.with_name("Song (Live).flac")
    tags = read_tags(new_path)
    assert tags.title == "Song (Live)"
    assert tags.artist == ["Lucinha; Mick"]
    assert tags.albumartist == ["Lucinha"]
    new_track = library.track(new_path)
    assert [a["name"] for a in new_track.artists] == ["Lucinha", "Mick"]
    assert new_track.albumhash == albumhash
    assert new_track.trackhash != old_hash


def test_the_same_title_on_screen_keeps_the_hash_when_a_feat_moves(http, library):
    path = library.add(
        "flac", "Song.flac", title="Song (feat. Mick)", artist="Lucinha", album="Album", album_artist="Lucinha"
    )
    library.index()
    old_hash = library.track(path).trackhash

    res = rename(http, path, "Song")

    assert res.status_code == 200
    assert res.get_json()["new_trackhash"] == old_hash
    assert read_tags(path).artist == ["Lucinha; Mick"]


def test_a_missing_album_artist_is_pinned_when_the_artist_tag_grows(http, library):
    path = library.add("flac", "song.flac", title="Song (feat. Mick)", artist="Lucinha", album="Album")
    library.index()
    albumhash = library.track(path).albumhash
    assert read_tags(path).albumartist is None

    res = rename(http, path, "Song")

    assert res.status_code == 200
    tags = read_tags(path.with_name("Song.flac"))
    assert tags.artist == ["Lucinha; Mick"]
    # without this the album would change owner (the app takes it from the artist)
    assert tags.albumartist == ["Lucinha"]
    assert library.track(path.with_name("Song.flac")).albumhash == albumhash


def test_a_feat_already_in_the_artist_tag_is_not_added_twice(http, library):
    path = library.add(
        "flac", "song.flac", title="Song (feat. Mick)", artist="Lucinha; mick", album="Album", album_artist="Lucinha"
    )
    library.index()

    rename(http, path, "Other")

    assert read_tags(path.with_name("Other.flac")).artist == ["Lucinha; mick"]


def test_a_failed_write_leaves_tag_and_file_as_they_were(http, library, monkeypatch):
    path = library.add("flac", "song.flac", title="Old", artist="Lucinha", album="Album")
    library.index()
    original = path.read_bytes()
    old_hash = library.track(path).trackhash

    def boom(self):
        raise OSError("disk full")

    monkeypatch.setattr(tagwriter._VorbisAdapter, "save", boom)

    res = rename(http, path, "New")

    assert res.status_code == 500
    assert "disk full" in res.get_json()["error"]
    assert path.read_bytes() == original
    assert sorted(p.name for p in path.parent.iterdir()) == ["song.flac"]
    assert library.track(path).trackhash == old_hash
    assert journal(library) == []


def test_only_the_chosen_file_changes_when_the_track_has_duplicates(http, library):
    one = library.add("flac", "a/song.flac", title="Same", artist="Lucinha", album="Album")
    two = library.add("flac", "b/song.flac", title="Same", artist="Lucinha", album="Album")
    library.index()
    old_hash = library.track(one).trackhash
    assert library.track(two).trackhash == old_hash
    FavoritesTable.insert_item({"type": "track", "hash": old_hash, "userid": 1, "extra": {}})
    two_before = two.read_bytes()

    res = rename(http, one, "Different")

    assert res.status_code == 200
    assert two.read_bytes() == two_before
    assert library.track(two).trackhash == old_hash
    assert library.track(one.with_name("Different.flac")).trackhash == res.get_json()["new_trackhash"]
    # the other file still has its favorite
    assert [f.hash for f in FavoritesTable.get_all()] == [old_hash]


def test_a_title_that_matches_the_file_name_only_changes_the_tag(http, library):
    path = library.add("flac", "Song.flac", title="Old", artist="Lucinha", album="Album")
    library.index()

    res = rename(http, path, "Song")

    assert res.status_code == 200
    assert read_tags(path).title == "Song"
    assert sorted(p.name for p in path.parent.iterdir()) == ["Song.flac"]


def test_the_numbered_prefix_goes_away(http, library):
    path = library.add("mp3", "03 - Song.mp3", title="Song", artist="Lucinha", album="Album")
    library.index()

    res = rename(http, path, "Song")

    assert res.status_code == 200
    assert sorted(p.name for p in path.parent.iterdir()) == ["Song.mp3"]


@pytest.mark.parametrize(
    "title,status",
    [("", 400), ("   ", 400), ("x" * 201, 400), ("x" * 200, 200)],
)
def test_the_title_is_checked(http, library, title, status):
    path = library.add("mp3", "song.mp3", title="Old", artist="Lucinha", album="Album")
    library.index()

    res = rename(http, path, title)

    assert res.status_code == status


def test_unknown_file_is_404(http, library, tmp_path):
    library.index()

    res = http.post("/track/rename", json={"filepath": (tmp_path / "nope.mp3").as_posix(), "title": "x"})

    assert res.status_code == 404


def test_unsupported_format_is_refused_and_untouched(http, library):
    wav = library.env.root / "music" / "song.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(wav), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(8000)
        file.writeframes(b"\x00\x00" * 8000)


    TrackTable.insert_one(get_tags(wav.as_posix(), config=library.env.config))
    reload_stores()
    before = wav.read_bytes()

    res = rename(http, wav, "New")

    assert res.status_code == 400
    assert "unsupported format" in res.get_json()["error"]
    assert wav.read_bytes() == before
    assert sorted(p.name for p in wav.parent.iterdir()) == ["song.wav"]


def test_rename_requires_admin(http, library, monkeypatch):
    path = library.add("mp3", "song.mp3", title="Old", artist="Lucinha", album="Album")
    library.index()
    monkeypatch.setattr(auth_api, "current_user", {"roles": []})

    res = rename(http, path, "New")

    assert res.status_code == 403
    assert path.exists()


def test_rename_error_carries_the_status():
    error = RenameError(409, "taken")

    assert (error.status, error.message) == (409, "taken")
