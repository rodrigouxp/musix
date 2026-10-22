from types import SimpleNamespace

import pytest

from musix.db.userdata import CollectionTable
from musix.store.homepage import HomepageStore


def entry(name, items):
    return SimpleNamespace(items=items, get_items=lambda userid, limit: {"title": name, "items": items})


@pytest.fixture
def no_pages(monkeypatch):
    monkeypatch.setattr(CollectionTable, "get_all", classmethod(lambda cls: []))


def keys(result):
    return [next(iter(item)) for item in result]


def test_nothing_to_show_is_an_empty_list_not_an_error(monkeypatch, no_pages):
    monkeypatch.setattr(
        HomepageStore,
        "entries",
        {"recently_played": entry("played", []), "recently_added": entry("added", [])},
    )

    assert HomepageStore.get_homepage_items(limit=7) == []


def test_recently_added_goes_last_when_there_is_one(monkeypatch, no_pages):
    monkeypatch.setattr(
        HomepageStore,
        "entries",
        {
            "recently_added": entry("added", [1]),
            "recently_played": entry("played", [1]),
            "top": entry("top", [1]),
        },
    )

    assert keys(HomepageStore.get_homepage_items(limit=7)) == ["recently_played", "top", "recently_added"]


def test_without_recently_added_the_others_stay(monkeypatch, no_pages):
    # before: the last of the others was taken for "recently added" and moved
    monkeypatch.setattr(
        HomepageStore,
        "entries",
        {
            "recently_played": entry("played", [1]),
            "top": entry("top", [1]),
            "recently_added": entry("added", []),
        },
    )

    assert keys(HomepageStore.get_homepage_items(limit=7)) == ["recently_played", "top"]


def test_recently_played_playlist_with_no_plays_is_empty_not_an_error(monkeypatch):
    from musix.db.userdata import ScrobbleTable
    from musix.lib.home import recentlyplayed
    from musix.store.tracks import TrackStore

    monkeypatch.setattr(ScrobbleTable, "get_all", classmethod(lambda cls, *args, **kwargs: []))
    monkeypatch.setattr(TrackStore, "get_tracks_by_trackhashes", classmethod(lambda cls, hashes: []))
    monkeypatch.setattr(recentlyplayed, "get_first_4_images", lambda tracks=[], trackhashes=[]: [])

    playlist, tracks = recentlyplayed.get_recently_played_playlist()

    assert tracks == []
    assert playlist.id == "recentlyplayed"
