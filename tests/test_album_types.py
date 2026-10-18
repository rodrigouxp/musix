from types import SimpleNamespace

import pytest
from flask_openapi3 import OpenAPI
from sqlalchemy import create_engine

from musix.api import album as album_api
from musix.api import artist as artist_api
from musix.api import auth as auth_api
from musix.db import create_all_tables
from musix.db.engine import DbEngine
from musix.db.userdata import AlbumTypeTable
from musix.models.album import Album
from musix.serializers.album import serialize_for_card
from musix.store.albums import AlbumStore
from musix.store.albumtypes import AlbumTypeStore
from musix.store.artists import ArtistStore
from musix.store.tracks import TrackStore

ARTISTHASH = "a" * 16


def make_album(title: str, albumhash: str, artist: str = "Black Sabbath") -> Album:
    return Album(
        albumartists=[{"name": artist, "artisthash": ARTISTHASH}],
        albumhash=albumhash,
        artisthashes=[ARTISTHASH],
        base_title=title,
        color="",
        blurhash="",
        created_date=0,
        date=0,
        duration=0,
        genres=[],
        genrehashes=[],
        og_title=title,
        title=title,
        trackcount=1,
        lastplayed=0,
        playcount=0,
        playduration=0,
        extra={},
    )


def make_track(title: str, albumhash: str, n: int = 1):
    return SimpleNamespace(title=title, albumhash=albumhash, trackhash=f"{albumhash}{n}")


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setattr(DbEngine, "_engine", engine)
    create_all_tables()
    AlbumTypeStore.overrides = {}
    yield
    AlbumTypeStore.overrides = {}
    engine.dispose()


@pytest.mark.parametrize(
    "title",
    [
        "Something EP",
        "Something - Single",
        "Something (Single Version)",
        "Original Motion Picture Soundtrack",
        "Something: The Album",
        "Live at Wembley",
        "MTV Unplugged",
    ],
)
def test_titles_never_give_a_type(title):
    album = make_album(title, "1" * 16)
    album.check_type([make_track(title, album.albumhash)])

    assert album.type == "album"


def test_title_track_alone_is_not_a_single():
    album = make_album("Heaven And Hell", "2" * 16)
    album.check_type([make_track("Heaven and Hell", album.albumhash)])

    assert album.type == "album"


def test_compilations_are_still_detected():
    album = make_album("Greatest Hits", "3" * 16)
    album.check_type([])

    assert album.type == "compilation"


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setattr(auth_api, "current_user", {"roles": ["admin"]})

    app = OpenAPI(__name__)
    app.register_api(album_api.api)
    app.register_api(artist_api.api)
    return app.test_client()


def put_albums_in_store(monkeypatch, albums: list[Album]):
    entries = {
        a.albumhash: SimpleNamespace(album=a, trackhashes={a.albumhash + "1"})
        for a in albums
    }
    monkeypatch.setattr(AlbumStore, "albummap", entries)
    return entries


def test_mark_replace_and_remove_persist_after_reload(http, monkeypatch):
    album = make_album("Heaven And Hell", "4" * 16)
    put_albums_in_store(monkeypatch, [album])

    res = http.post(f"/album/{album.albumhash}/type", json={"kind": "ep"})
    assert res.status_code == 200
    assert res.get_json() == {"ok": True, "kind": "ep"}
    assert album.type == "ep"

    # marking again replaces the old mark: one mark per album
    res = http.post(f"/album/{album.albumhash}/type", json={"kind": "live album"})
    assert res.get_json() == {"ok": True, "kind": "live album"}
    assert AlbumTypeTable.get_all() == [(album.albumhash, "live album")]

    # reload the in-memory store from the database
    AlbumTypeStore.overrides = {}
    AlbumTypeStore.load(AlbumTypeTable.get_all())
    album.check_type()
    assert album.type == "live album"

    res = http.post(f"/album/{album.albumhash}/type", json={"kind": None})
    assert res.get_json() == {"ok": True, "kind": None}
    assert album.type == "album"

    AlbumTypeStore.load(AlbumTypeTable.get_all())
    assert AlbumTypeTable.get_all() == []
    assert AlbumTypeStore.get(album.albumhash) is None


def test_type_of_unknown_album_is_404(http, monkeypatch):
    put_albums_in_store(monkeypatch, [])

    res = http.post(f"/album/{'5' * 16}/type", json={"kind": "ep"})

    assert res.status_code == 404


def test_invalid_kind_is_400(http, monkeypatch):
    album = make_album("Anything", "6" * 16)
    put_albums_in_store(monkeypatch, [album])

    res = http.post(f"/album/{album.albumhash}/type", json={"kind": "single"})

    assert res.status_code == 400
    assert AlbumTypeTable.get_all() == []


def test_type_requires_admin(http, monkeypatch):
    album = make_album("Anything", "7" * 16)
    put_albums_in_store(monkeypatch, [album])
    monkeypatch.setattr(auth_api, "current_user", {"roles": []})

    res = http.post(f"/album/{album.albumhash}/type", json={"kind": "ep"})

    assert res.status_code == 403


def test_artist_lists_hold_only_marked_albums(http, monkeypatch):
    plain = make_album("Never Say Die!", "8" * 16)
    ep = make_album("Heaven And Hell", "9" * 16)
    soundtrack = make_album("Some Movie", "b" * 16)
    live = make_album("Reunion", "c" * 16)
    comp = make_album("Greatest Hits", "d" * 16)
    unmarked_ep_title = make_album("Looks Like An EP", "e" * 16)
    albums = [plain, ep, soundtrack, live, comp, unmarked_ep_title]

    # the track list is deliberately unordered: the tracks of one album are not
    # next to each other (this is what used to break the grouping)
    tracks = []
    for a in albums:
        tracks.append(make_track(a.title, a.albumhash, 1))
        tracks.append(make_track("Other song", "f" * 16, 9))
        tracks.append(make_track("Second song", a.albumhash, 2))

    monkeypatch.setattr(
        ArtistStore,
        "artistmap",
        {
            ARTISTHASH: SimpleNamespace(
                albumhashes={a.albumhash for a in albums},
                trackhashes={t.trackhash for t in tracks},
                artist=SimpleNamespace(name="Black Sabbath"),
            )
        },
    )
    monkeypatch.setattr(
        AlbumStore,
        "get_albums_by_hashes",
        classmethod(lambda cls, hashes: [a for a in albums if a.albumhash in set(hashes)]),
    )
    monkeypatch.setattr(
        TrackStore, "get_tracks_by_trackhashes", classmethod(lambda cls, h: tracks)
    )

    for album, kind in ((ep, "ep"), (soundtrack, "soundtrack"), (live, "live album")):
        AlbumTypeStore.set(album.albumhash, kind)

    res = http.get(f"/artist/{ARTISTHASH}/albums")
    data = res.get_json()

    def hashes(key):
        return {a["albumhash"] for a in data[key]}

    assert res.status_code == 200
    assert hashes("singles_and_eps") == {ep.albumhash}
    assert hashes("soundtracks") == {soundtrack.albumhash}
    assert hashes("live_albums") == {live.albumhash}
    assert hashes("compilations") == {comp.albumhash}
    assert hashes("albums") == {plain.albumhash, unmarked_ep_title.albumhash}
    assert all(a["album_type"] == "ep" for a in data["singles_and_eps"])


def test_card_keeps_card_type_and_sends_the_real_one():
    album = make_album("Heaven And Hell", "1a" * 8)
    AlbumTypeStore.set(album.albumhash, "soundtrack")

    card = serialize_for_card(album)

    assert card["type"] == "album"
    assert card["album_type"] == "soundtrack"
