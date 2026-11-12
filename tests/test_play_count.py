from types import SimpleNamespace

import pytest
from flask_openapi3 import OpenAPI

from musix.api import scrobble as scrobble_api
from musix.db.userdata import ScrobbleTable, UserTable
from musix.lib import mapstuff
from musix.lib.playcount import counts_as_play, most_played_first, play_threshold
from musix.store.albums import AlbumStore
from musix.store.artists import ArtistStore
from musix.store.tracks import TrackGroup, TrackStore
from musix.utils import auth as auth_utils


LONG = "long000000000000"
OTHER = "other00000000000"
SHORT = "short00000000000"


def make_track(trackhash: str, title: str, duration: int = 200):
    return SimpleNamespace(
        trackhash=trackhash,
        title=title,
        duration=duration,
        albumhash="album",
        artisthashes=["artist"],
        playcount=0,
        playduration=0,
        lastplayed=0,
        bitrate=320,
        filepath=f"/music/{trackhash}.flac",
        artists=[{"name": "Artist", "artisthash": "artist"}],
    )


@pytest.fixture
def stores(database, monkeypatch):
    """
    Three tracks in the store (one of them 8 seconds long) and two users.
    """
    tracks = {
        LONG: make_track(LONG, "Long song"),
        OTHER: make_track(OTHER, "Another song"),
        SHORT: make_track(SHORT, "Interlude", duration=8),
    }
    monkeypatch.setattr(
        TrackStore, "trackhashmap", {h: TrackGroup([t]) for h, t in tracks.items()}
    )
    monkeypatch.setattr(AlbumStore, "albummap", {})
    monkeypatch.setattr(ArtistStore, "artistmap", {})
    monkeypatch.setattr(scrobble_api, "RecentlyPlayed", lambda **kwargs: None)
    monkeypatch.setattr(auth_utils, "current_user", {"id": 2})
    UserTable.insert_one({"username": "one", "password": "x", "roles": []})
    UserTable.insert_one({"username": "two", "password": "x", "roles": []})
    return tracks


@pytest.fixture
def http(stores):
    app = OpenAPI(__name__)
    app.register_api(scrobble_api.api)
    return app.test_client()


def log(http, trackhash: str, duration: int, **extra):
    return http.post(
        "/logger/track/log",
        json={
            "trackhash": trackhash,
            "duration": duration,
            "timestamp": 1_700_000_000,
            "source": "al:album",
            **extra,
        },
    )


def scrobbles():
    return sorted(
        (s.trackhash, s.duration, s.userid) for s in ScrobbleTable.get_all_unfiltered()
    )


def test_the_threshold_is_30_seconds_or_half_of_the_track():
    assert play_threshold(200) == 30
    assert play_threshold(40) == 20
    assert play_threshold(8) == 4
    assert play_threshold(0) == 30
    assert counts_as_play(30, 200)
    assert not counts_as_play(29, 200)
    assert counts_as_play(4, 8)


def test_a_listen_of_30_seconds_is_a_play(http, stores):
    res = log(http, LONG, 30)

    assert res.status_code == 201
    assert res.json["counted"] is True
    assert res.json["playcount"] == 1
    assert res.json["help_text"] == "1 play"
    assert stores[LONG].playcount == 1
    assert scrobbles() == [(LONG, 30, 2)]


def test_a_skipped_track_is_not_a_play(http, stores):
    res = log(http, LONG, 12)

    assert res.status_code == 200
    assert res.json["counted"] is False
    assert res.json["help_text"] == "unplayed"
    assert stores[LONG].playcount == 0
    assert scrobbles() == []


def test_a_short_track_counts_at_half_of_its_length(http, stores):
    assert log(http, SHORT, 3).json["counted"] is False
    assert log(http, SHORT, 4).json["counted"] is True
    assert stores[SHORT].playcount == 1


def test_the_rest_of_the_listen_extends_the_play(http, stores):
    log(http, LONG, 30)
    res = log(http, LONG, 150, extend=True)

    assert res.status_code == 200
    assert res.json["playcount"] == 1
    assert stores[LONG].playcount == 1
    assert stores[LONG].playduration == 180
    assert scrobbles() == [(LONG, 180, 2)]


def test_the_extension_goes_to_the_latest_play_of_that_user(http, stores):
    ScrobbleTable.insert_one(
        {
            "trackhash": LONG,
            "duration": 30,
            "timestamp": 1_800_000_000,
            "source": "",
            "userid": 1,
            "extra": {},
        }
    )
    log(http, LONG, 30)
    log(http, LONG, 30)
    log(http, LONG, 100, extend=True)

    assert scrobbles() == [(LONG, 30, 1), (LONG, 30, 2), (LONG, 130, 2)]


def test_an_unknown_track_and_an_empty_listen_are_refused(http):
    assert log(http, "nope000000000000", 60).status_code == 404
    assert log(http, LONG, 0).status_code == 400


def test_at_boot_the_plays_of_every_user_are_mapped_and_skips_do_not_count(
    stores, monkeypatch
):
    # outside a request there is no user: the fallback is the user 1
    monkeypatch.setattr(auth_utils, "current_user", {"id": 1})

    for trackhash, duration, userid in [
        (LONG, 200, 1),
        (LONG, 45, 2),
        (LONG, 6, 2),  # a skip logged before the rule
        (OTHER, 9, 2),  # only skipped
        (SHORT, 5, 2),
        ("gone000000000000", 100, 2),  # a track that is not in the library any more
    ]:
        ScrobbleTable.insert_one(
            {
                "trackhash": trackhash,
                "duration": duration,
                "timestamp": 1_700_000_000 + duration,
                "source": "",
                "userid": userid,
                "extra": {},
            }
        )

    mapstuff.map_scrobble_data()

    assert stores[LONG].playcount == 2
    assert stores[LONG].playduration == 251
    assert stores[OTHER].playcount == 0
    assert stores[OTHER].playduration == 9
    assert stores[SHORT].playcount == 1


def test_most_played_first_breaks_ties_by_time_and_then_by_title():
    a = make_track("a", "Zebra")
    b = make_track("b", "apple")
    c = make_track("c", "Mango")
    d = make_track("d", "Banana")
    a.playcount, c.playcount = 3, 3
    c.playduration = 500
    a.playduration = 100

    assert [t.title for t in most_played_first([a, b, c, d])] == [
        "Mango",
        "Zebra",
        "apple",
        "Banana",
    ]
