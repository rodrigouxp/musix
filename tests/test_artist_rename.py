import json
import time
from pathlib import Path

import pytest
from flask_openapi3 import OpenAPI
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TPE1

from musix.api import artist as artist_api
from musix.api import auth as auth_api
from musix.db.userdata import (
    AlbumTypeTable,
    CollectionTable,
    FavoritesTable,
    LibDataTable,
    PlaylistTable,
    ScrobbleTable,
    SimilarArtistTable,
)
from musix.lib import artistrename, tagwriter
from musix.lib.artistlib import is_manual_artist_image
from musix.lib.tagwriter import read_tags
from musix.store.albums import AlbumStore
from musix.store.albumtypes import AlbumTypeStore
from musix.store.artists import ArtistStore
from musix.store.tracks import TrackStore
from musix.utils.hashing import create_hash


def h(name: str) -> str:
    return create_hash(name, decode=True)


STONES = "The Rolling Stones"


@pytest.fixture
def http(library, monkeypatch):
    monkeypatch.setattr(auth_api, "current_user", {"roles": ["admin"]})
    monkeypatch.setattr(tagwriter, "_default_config", lambda: library.env.config)
    monkeypatch.setattr(artistrename.JobState, "running", False)

    app = OpenAPI(__name__)
    app.register_api(artist_api.api)
    return app.test_client()


def preview(http, old: str, new: str):
    return http.post(f"/artist/{h(old)}/rename/preview", json={"name": new})


def rename(http, old: str, new: str, confirm=True):
    return http.post(f"/artist/{h(old)}/rename", json={"name": new, "confirm": confirm})


def wait_for_job(http, timeout=60):
    end = time.time() + timeout

    while time.time() < end:
        status = http.get("/artist/rename/status").get_json()

        if status["finished"] or (not status["running"] and status["result"]):
            return status

        time.sleep(0.05)

    raise AssertionError("the rename did not finish")


def do_rename(http, old: str, new: str):
    res = rename(http, old, new)
    assert res.status_code == 202, res.get_json()
    return wait_for_job(http)


def journal(library) -> list[dict]:
    path = library.env.paths.config_dir / "rename-journal.jsonl"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def track_of(library, path: Path):
    return library.track(path)


@pytest.fixture
def lucinha(library):
    """
    The album of Lucinha, with one track where the Rolling Stones take part,
    and an album of the Rolling Stones.
    """
    with_stones = library.add(
        "flac",
        "lucinha/01 with stones.flac",
        title="With Stones",
        artist=f"Lucinha; {STONES}",
        album_artist="Lucinha",
        album="Album of Lucinha",
    )
    solo = library.add(
        "flac",
        "lucinha/02 solo.flac",
        title="Solo",
        artist="Lucinha",
        album_artist="Lucinha",
        album="Album of Lucinha",
    )
    satisfaction = library.add(
        "flac",
        "stones/01 satisfaction.flac",
        title="Satisfaction",
        artist=STONES,
        album_artist=STONES,
        album="Hits",
    )
    library.index()
    return {"with_stones": with_stones, "solo": solo, "satisfaction": satisfaction}


# SECTION: the multi-artist rule


def test_lucinha_case(http, library, lucinha):
    lucinha_album = track_of(library, lucinha["solo"]).albumhash
    stones_album = track_of(library, lucinha["satisfaction"]).albumhash
    before_solo = lucinha["solo"].read_bytes()

    status = do_rename(http, STONES, "Rolling Stones")

    assert status["result"]["files_ok"] == 2
    assert status["result"]["files_failed"] == {}
    assert status["new_artisthash"] == h("Rolling Stones")

    tags = read_tags(lucinha["with_stones"])
    assert tags.albumartist == ["Lucinha"]  # the album stays hers
    assert tags.artist == ["Lucinha; Rolling Stones"]  # and she is still the artist
    assert read_tags(lucinha["satisfaction"]).artist == ["Rolling Stones"]
    assert read_tags(lucinha["satisfaction"]).albumartist == ["Rolling Stones"]

    # the album of Lucinha has the same hash; a file that has no X is not touched
    assert track_of(library, lucinha["with_stones"]).albumhash == lucinha_album
    assert track_of(library, lucinha["solo"]).albumhash == lucinha_album
    assert lucinha["solo"].read_bytes() == before_solo
    # the album of the artist changed owner name, so it has a new hash
    assert track_of(library, lucinha["satisfaction"]).albumhash != stones_album

    assert h(STONES) not in ArtistStore.artistmap
    assert h("Rolling Stones") in ArtistStore.artistmap


def test_preview_shows_the_owner_of_the_album_intact_and_writes_nothing(http, library, lucinha):
    before = {k: p.read_bytes() for k, p in lucinha.items()}

    res = preview(http, STONES, "Rolling Stones")

    assert res.status_code == 200
    body = res.get_json()
    assert body["tracks_in_artist_tag"] == 2
    assert body["albums_in_artist_tag"] == 2
    assert body["participant_count"] == 1
    assert body["tracks_as_participant"] == 1
    assert body["files_to_rewrite"] == 2
    assert body["merge"] is None
    assert body["new_artisthash"] == h("Rolling Stones")

    participant = next(s for s in body["samples"] if s["participant"])
    assert participant["artist_before"] == f"Lucinha; {STONES}"
    assert participant["artist_after"] == "Lucinha; Rolling Stones"
    assert participant["albumartist_before"] == "Lucinha"
    assert participant["albumartist_after"] == "Lucinha"

    assert {k: p.read_bytes() for k, p in lucinha.items()} == before
    assert journal(library) == []
    assert sorted(p.name for p in lucinha["solo"].parent.iterdir()) == [
        "01 with stones.flac",
        "02 solo.flac",
    ]


def test_owner_and_participant_in_the_same_album(http, library):
    owner = library.add(
        "flac", "a/one.flac", title="One", artist=STONES, album_artist=STONES, album="Mixed"
    )
    guest = library.add(
        "flac", "a/two.flac", title="Two", artist=f"Lucinha; {STONES}", album_artist=STONES, album="Mixed"
    )
    library.index()

    do_rename(http, STONES, "Rolling Stones")

    assert read_tags(owner).artist == ["Rolling Stones"]
    assert read_tags(owner).albumartist == ["Rolling Stones"]
    assert read_tags(guest).artist == ["Lucinha; Rolling Stones"]
    assert read_tags(guest).albumartist == ["Rolling Stones"]
    # both files are still in one album
    assert track_of(library, owner).albumhash == track_of(library, guest).albumhash


@pytest.mark.parametrize(
    "artist,expected",
    [
        ("X; A; B", "Y; A; B"),
        ("A; X; B", "A; Y; B"),
        ("A; B; X", "A; B; Y"),
        ("A / X / B", "A / Y / B"),
        ("A/X", "A/Y"),
    ],
)
def test_position_and_separator_stay(http, library, artist, expected):
    path = library.add("flac", "x.flac", title="T", artist=artist, album_artist="A", album="Al")
    library.index()

    do_rename(http, "X", "Y")

    assert read_tags(path).artist == [expected]


def test_vorbis_with_several_values_and_mp3_with_one_string_or_several(http, library):
    flac = library.add("flac", "v.flac", title="V", album="Al")
    audio = FLAC(flac)
    audio["artist"] = ["A", "X", "B"]
    audio["albumartist"] = ["A"]
    audio.save()
    single = library.add("mp3", "s.mp3", title="S", artist="A; X; B", album_artist="A", album="Al2")
    multi = library.add("mp3", "m.mp3", title="M", album_artist="A", album="Al3")
    tags = ID3(multi)
    tags.add(TPE1(encoding=3, text=["A", "X", "B"]))
    tags.save(v2_version=4)
    library.index()

    do_rename(http, "X", "Y")

    assert read_tags(flac).artist == ["A", "Y", "B"]
    assert read_tags(single).artist == ["A; Y; B"]
    assert read_tags(multi).artist == ["A", "Y", "B"]
    assert read_tags(flac).albumartist == ["A"]


def test_the_artists_tag_changes_with_the_artist(http, library):
    path = library.add("flac", "x.flac", title="T", artist="A; X", album_artist="A", album="Al")
    audio = FLAC(path)
    audio["artists"] = ["A", "X"]
    audio.save()
    library.index()

    do_rename(http, "X", "Y")

    tags = read_tags(path)
    assert tags.artist == ["A; Y"]
    assert tags.artists == ["A", "Y"]


def test_a_partial_name_does_not_match(http, library):
    path = library.add(
        "flac", "x.flac", title="T", artist="Stones; Rolling Stones", album_artist="Stones", album="Al"
    )
    other = library.add(
        "flac", "o.flac", title="O", artist="Rolling Stones", album_artist="Rolling Stones", album="Al2"
    )
    library.index()
    other_bytes = other.read_bytes()

    do_rename(http, "Stones", "Pebbles")

    assert read_tags(path).artist == ["Pebbles; Rolling Stones"]
    assert read_tags(path).albumartist == ["Pebbles"]
    assert other.read_bytes() == other_bytes


def test_the_new_name_already_in_the_tag_becomes_one_and_is_highlighted(http, library):
    path = library.add(
        "flac", "x.flac", title="T", artist="Lucinha; Rolling Stones", album_artist="Lucinha", album="Al"
    )
    library.index()

    body = preview(http, "Lucinha", "Rolling Stones").get_json()

    assert body["same_tag_collapses_count"] == 1
    assert body["same_tag_collapses"][0]["tags"] == ["artist"]
    assert body["merge"]["name"] == "Rolling Stones"

    do_rename(http, "Lucinha", "Rolling Stones")

    assert read_tags(path).artist == ["Rolling Stones"]
    assert read_tags(path).albumartist == ["Rolling Stones"]


def test_no_tag_is_created_when_the_file_did_not_have_it(http, library):
    path = library.add("flac", "x.flac", title="T", artist="X; A", album="Al")
    library.index()
    assert read_tags(path).albumartist is None

    body = preview(http, "X", "Y").get_json()
    assert body["no_albumartist_count"] == 1

    do_rename(http, "X", "Y")

    tags = read_tags(path)
    assert tags.artist == ["Y; A"]
    assert tags.albumartist is None
    assert tags.artists is None


def test_only_the_albumartist_tag_has_the_artist(http, library):
    path = library.add("flac", "x.flac", title="T", album_artist="X", album="Al")
    library.index()

    do_rename(http, "X", "Y")

    tags = read_tags(path)
    assert tags.albumartist == ["Y"]
    assert tags.artist is None


# SECTION: the title


def test_the_artist_only_in_the_title_changes_the_title_and_the_file_name(http, library):
    path = library.add(
        "flac",
        "01 - Song.flac",
        title="Song (feat. X)",
        artist="Lucinha",
        album_artist="Lucinha",
        album="Al",
    )
    library.index()
    assert [a["name"] for a in track_of(library, path).artists] == ["Lucinha", "X"]

    body = preview(http, "X", "Y").get_json()
    assert body["tracks_title_only"] == 1
    assert body["files_to_rename"] == 1

    do_rename(http, "X", "Y")

    new_path = path.with_name("Song (feat. Y).flac")
    assert not path.exists()
    assert new_path.exists()
    tags = read_tags(new_path)
    assert tags.title == "Song (feat. Y)"
    assert tags.artist == ["Lucinha"]
    assert [a["name"] for a in track_of(library, new_path).artists] == ["Lucinha", "Y"]


def test_the_artist_in_the_tag_and_in_the_title(http, library):
    path = library.add(
        "flac", "s.flac", title="Song [ft. X]", artist="Lucinha; X", album_artist="Lucinha", album="Al"
    )
    library.index()

    do_rename(http, "X", "Y")

    new_path = path.with_name("Song [ft. Y].flac")
    assert read_tags(new_path).title == "Song [ft. Y]"
    assert read_tags(new_path).artist == ["Lucinha; Y"]
    assert [a["name"] for a in track_of(library, new_path).artists] == ["Lucinha", "Y"]


def test_a_taken_file_name_is_a_conflict_and_that_file_is_skipped(http, library):
    path = library.add(
        "flac", "a.flac", title="Song (feat. X)", artist="Lucinha", album_artist="Lucinha", album="Al"
    )
    taken = library.add("flac", "Song (feat. Y).flac", title="Other", artist="B", album="Al2")
    other = library.add("flac", "o.flac", title="O", artist="X", album_artist="X", album="Al3")
    library.index()
    path_bytes = path.read_bytes()

    body = preview(http, "X", "Y").get_json()
    assert body["name_conflicts_count"] == 1
    assert body["name_conflicts"][0]["name"] == "Song (feat. Y).flac"

    status = do_rename(http, "X", "Y")

    assert path.read_bytes() == path_bytes
    assert path.as_posix() in status["result"]["files_failed"]
    assert "already exists" in status["result"]["files_failed"][path.as_posix()]
    assert taken.exists()
    assert read_tags(other).artist == ["Y"]


# SECTION: the hashes


def test_hashes_follow_the_artist(http, library, lucinha):
    stones_track = track_of(library, lucinha["satisfaction"])
    guest_track = track_of(library, lucinha["with_stones"])
    old_album = stones_track.albumhash
    old_track = stones_track.trackhash
    old_guest = guest_track.trackhash
    new_name = "Rolling Stones"

    FavoritesTable.insert_item({"type": "track", "hash": old_track, "userid": 1, "extra": {}})
    FavoritesTable.insert_item({"type": "track", "hash": old_guest, "userid": 1, "extra": {}})
    FavoritesTable.insert_item({"type": "album", "hash": old_album, "userid": 1, "extra": {}})
    FavoritesTable.insert_item({"type": "artist", "hash": h(STONES), "userid": 1, "extra": {}})
    ScrobbleTable.add(
        {"trackhash": old_track, "duration": 30, "timestamp": 1, "source": "al:" + old_album, "userid": 1, "extra": {}}
    )
    ScrobbleTable.add(
        {"trackhash": old_guest, "duration": 30, "timestamp": 2, "source": "ar:" + h(STONES), "userid": 1, "extra": {}}
    )
    PlaylistTable.insert_one(
        {"name": "p", "last_updated": 1, "userid": 1, "settings": {}, "trackhashes": ["x", old_track, old_guest]}
    )
    CollectionTable.insert_one(
        {
            "name": "c",
            "userid": 1,
            "items": [
                {"type": "album", "hash": old_album},
                {"type": "artist", "hash": h(STONES)},
            ],
        }
    )
    AlbumTypeTable.set_kind(old_album, "live album")
    AlbumTypeStore.set(old_album, "live album")
    LibDataTable.insert_one(
        {"itemhash": "artist" + h(STONES), "itemtype": "artist", "color": "rgb(1, 2, 3)", "extra": {}}
    )
    LibDataTable.insert_one(
        {"itemhash": "album" + old_album, "itemtype": "album", "color": "rgb(4, 5, 6)", "extra": {}}
    )
    SimilarArtistTable.insert_one(
        {"artisthash": h("Lucinha"), "similar_artists": [{"artisthash": h(STONES), "name": STONES}]}
    )
    SimilarArtistTable.insert_one({"artisthash": h(STONES), "similar_artists": []})

    # the photo of the artist, chosen by hand, and the thumbnail of the album
    paths = library.env.paths
    for folder in (paths.sm_artist_img_path, paths.md_artist_img_path, paths.lg_artist_img_path):
        (folder / f"{h(STONES)}.webp").write_bytes(b"photo")
    from musix.lib.artistlib import set_manual_artist_image

    set_manual_artist_image(h(STONES), True)
    (paths.og_thumb_path / f"{old_album}.webp").write_bytes(b"thumb")
    (paths.sm_thumb_path / f"{old_album}.webp").write_bytes(b"thumb")

    status = do_rename(http, STONES, new_name)
    assert status["result"]["files_failed"] == {}

    new_artist = h(new_name)
    new_stones_track = track_of(library, lucinha["satisfaction"])
    new_guest = track_of(library, lucinha["with_stones"])
    assert new_stones_track.trackhash != old_track
    assert new_guest.trackhash != old_guest
    assert new_stones_track.albumhash != old_album

    favorites = {(f.type, f.hash) for f in FavoritesTable.get_all()}
    assert favorites == {
        ("track", new_stones_track.trackhash),
        ("track", new_guest.trackhash),
        ("album", new_stones_track.albumhash),
        ("artist", new_artist),
    }
    scrobbles = {(s.trackhash, s.source) for s in ScrobbleTable.get_all(0, None, userid=1)}
    assert scrobbles == {
        (new_stones_track.trackhash, "al:" + new_stones_track.albumhash),
        (new_guest.trackhash, "ar:" + new_artist),
    }
    assert list(PlaylistTable.get_all(current_user=False))[0].trackhashes == [
        "x",
        new_stones_track.trackhash,
        new_guest.trackhash,
    ]
    assert _collection_items() == [
        {"type": "album", "hash": new_stones_track.albumhash},
        {"type": "artist", "hash": new_artist},
    ]
    assert AlbumTypeTable.get_all() == [(new_stones_track.albumhash, "live album")]
    assert AlbumTypeStore.get(new_stones_track.albumhash) == "live album"
    assert {r.itemhash for r in _libdata_rows()} == {"artist" + new_artist, "album" + new_stones_track.albumhash}
    assert {r.artisthash for r in SimilarArtistTable.get_all()} == {h("Lucinha"), new_artist}
    lucinha_similar = next(r for r in SimilarArtistTable.get_all() if r.artisthash == h("Lucinha"))
    assert [e["artisthash"] for e in lucinha_similar.similar_artists] == [new_artist]

    for folder in (paths.sm_artist_img_path, paths.md_artist_img_path, paths.lg_artist_img_path):
        assert not (folder / f"{h(STONES)}.webp").exists()
        assert (folder / f"{new_artist}.webp").read_bytes() == b"photo"

    assert is_manual_artist_image(new_artist)
    assert not is_manual_artist_image(h(STONES))
    assert (paths.og_thumb_path / f"{new_stones_track.albumhash}.webp").read_bytes() == b"thumb"
    assert not (paths.og_thumb_path / f"{old_album}.webp").exists()

    # the stores in memory know it
    assert 1 in ArtistStore.artistmap[new_artist].artist.fav_userids
    assert TrackStore.trackhashmap[new_stones_track.trackhash].tracks[0].is_favorite is not None


def _libdata_rows():
    from sqlalchemy import select

    from musix.db.engine import DbEngine

    with DbEngine.manager() as conn:
        return conn.execute(select(LibDataTable)).scalars().all()


def test_merge_with_an_existing_artist_does_not_duplicate_links(http, library):
    old_a = library.add("flac", "a.flac", title="A song", artist="Old", album_artist="Old", album="Al")
    new_a = library.add("flac", "b.flac", title="B song", artist="New", album_artist="New", album="Bl")
    library.index()
    FavoritesTable.insert_item({"type": "artist", "hash": h("Old"), "userid": 1, "extra": {}})
    FavoritesTable.insert_item({"type": "artist", "hash": h("New"), "userid": 1, "extra": {}})
    CollectionTable.insert_one(
        {
            "name": "c",
            "userid": 1,
            "items": [{"type": "artist", "hash": h("Old")}, {"type": "artist", "hash": h("New")}],
        }
    )
    LibDataTable.insert_one({"itemhash": "artist" + h("Old"), "itemtype": "artist", "color": "old", "bio": "bio of old", "extra": {}})
    LibDataTable.insert_one({"itemhash": "artist" + h("New"), "itemtype": "artist", "color": "new", "extra": {}})

    body = preview(http, "Old", "New").get_json()
    assert body["merge"]["name"] == "New"

    do_rename(http, "Old", "New")

    assert [(f.type, f.hash) for f in FavoritesTable.get_all()] == [("artist", h("New"))]
    collection = _collection_items()
    assert collection == [{"type": "artist", "hash": h("New")}]
    rows = {r.itemhash: r for r in _libdata_rows()}
    assert set(rows) == {"artist" + h("New")}
    assert rows["artist" + h("New")].color == "new"
    assert rows["artist" + h("New")].bio == "bio of old"
    assert [a["name"] for a in track_of(library, old_a).artists] == ["New"]
    assert len(ArtistStore.artistmap[h("New")].trackhashes) == 2
    del new_a


def _collection_items():
    from sqlalchemy import select

    from musix.db.engine import DbEngine

    with DbEngine.manager() as conn:
        return conn.execute(select(CollectionTable.items)).scalar()


# SECTION: failures


def test_a_write_failure_does_not_stop_the_others_and_keeps_the_artist(http, library, monkeypatch):
    bad = library.add("flac", "bad.flac", title="Bad", artist="X", album_artist="X", album="Al")
    good = library.add("flac", "good.flac", title="Good", artist="X", album_artist="X", album="Al")
    library.index()
    bad_bytes = bad.read_bytes()
    FavoritesTable.insert_item({"type": "artist", "hash": h("X"), "userid": 1, "extra": {}})

    real_write = artistrename.write_tags

    def flaky(path, *args, **kwargs):
        if Path(path).name == "bad.flac":
            raise tagwriter.TagWriteError("disk full")

        return real_write(path, *args, **kwargs)

    monkeypatch.setattr(artistrename, "write_tags", flaky)

    status = do_rename(http, "X", "Y")

    result = status["result"]
    assert result["files_ok"] == 1
    assert list(result["files_failed"]) == [bad.as_posix()]
    assert "disk full" in result["files_failed"][bad.as_posix()]
    assert status["errors"] == result["files_failed"]
    assert bad.read_bytes() == bad_bytes
    assert read_tags(good).artist == ["Y"]
    # the failed file is still X, so X stays and its data stays with it
    assert result["artist_moved"] is False
    assert h("X") in ArtistStore.artistmap
    assert [(f.type, f.hash) for f in FavoritesTable.get_all()] == [("artist", h("X"))]
    assert sorted(p.name for p in bad.parent.iterdir()) == ["bad.flac", "good.flac"]


def test_unsupported_files_fail_and_the_rest_goes_on(http, library):
    path = library.add("flac", "x.flac", title="T", artist="X", album_artist="X", album="Al")
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
    tags["artists"] = "X"
    tags["albumartists"] = "X"
    TrackTable.insert_one(tags)
    reload_stores()

    body = preview(http, "X", "Y").get_json()
    assert body["unsupported_count"] == 1

    status = do_rename(http, "X", "Y")

    assert read_tags(path).artist == ["Y"]
    assert wav.as_posix() in status["result"]["files_failed"]
    assert "unsupported format" in status["result"]["files_failed"][wav.as_posix()]


def test_a_journal_line_for_each_file(http, library, lucinha):
    do_rename(http, STONES, "Rolling Stones")

    lines = journal(library)
    assert len(lines) == 2
    guest = next(l for l in lines if l["filepath_old"].endswith("01 with stones.flac"))
    assert guest["action"] == "rename-artist"
    assert guest["artist_old"] == STONES
    assert guest["artist_new"] == "Rolling Stones"
    assert guest["artist_tag_old"] == [f"Lucinha; {STONES}"]
    assert guest["artist_tag_new"] == ["Lucinha; Rolling Stones"]
    assert guest["albumartist_tag_old"] == ["Lucinha"]
    assert guest["albumartist_tag_new"] == ["Lucinha"]


# SECTION: the routes


def test_confirm_is_needed(http, library, lucinha):
    before = {k: p.read_bytes() for k, p in lucinha.items()}

    res = rename(http, STONES, "Rolling Stones", confirm=False)

    assert res.status_code == 400
    assert "confirm" in res.get_json()["error"]
    assert {k: p.read_bytes() for k, p in lucinha.items()} == before


@pytest.mark.parametrize(
    "name",
    ["", "   ", "x" * 201, "A; B", "A / B", "Tyler, The Creator"],
)
def test_invalid_names_are_400(http, library, lucinha, name):
    for route in (preview, rename):
        res = route(http, STONES, name)

        assert res.status_code == 400, name
        assert res.get_json()["error"]


def test_an_exception_name_like_ac_dc_is_accepted(http, library, lucinha):
    res = preview(http, STONES, "AC/DC")

    assert res.status_code == 200


def test_the_same_name_is_400(http, library, lucinha):
    assert rename(http, STONES, STONES).status_code == 400


def test_unknown_artist_is_404(http, library, lucinha):
    assert preview(http, "Nobody", "Somebody").status_code == 404
    assert rename(http, "Nobody", "Somebody").status_code == 404


def test_only_one_job_at_a_time(http, library, lucinha, monkeypatch):
    monkeypatch.setattr(artistrename.JobState, "running", True)

    res = rename(http, STONES, "Rolling Stones")

    assert res.status_code == 409
    assert "already running" in res.get_json()["error"]


def test_the_status_reports_the_progress(http, library, lucinha):
    assert http.get("/artist/rename/status").get_json()["running"] is False

    status = do_rename(http, STONES, "Rolling Stones")

    assert status["done"] == status["total"] == 2
    assert status["finished"] is True
    assert status["new_artisthash"] == h("Rolling Stones")


def test_the_routes_need_admin(http, library, lucinha, monkeypatch):
    monkeypatch.setattr(auth_api, "current_user", {"roles": []})

    assert preview(http, STONES, "Rolling Stones").status_code == 403
    assert rename(http, STONES, "Rolling Stones").status_code == 403
