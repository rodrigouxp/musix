import json
import os
from datetime import datetime, timedelta

import pytest
import requests
from flask_openapi3 import OpenAPI

from musix.api.plugins import lyrics as lyrics_api
from musix.lib import lyricsfinder
from musix.lib.lyricsfinder import (
    FoundLyrics,
    LrclibProvider,
    LyricsQuery,
    MusixmatchProvider,
    NotFound,
    ProviderError,
    clean_title,
    find_and_save,
    find_lyrics,
    first_artist,
    get_miss,
    record_miss,
    save_lyrics,
)

TRACKHASH = "0853280a12345678"
SYNCED = "[00:01.00]Is this the real life?\n[00:03.50]Is this just fantasy?\n"
PLAIN = "Is this the real life?\nIs this just fantasy?"


# # # # # # # # # # # # # # # # # # # #
#             The fakes               #
# # # # # # # # # # # # # # # # # # # #


class FakeResponse:
    def __init__(self, status_code=200, data=None, bad_json=False):
        self.status_code = status_code
        self._data = data
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._data


class FakeSession:
    """Answers with `handler(endpoint, params)`: a FakeResponse, or an exception to raise."""

    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, dict, dict]] = []

    def get(self, url, params=None, headers=None, timeout=None):
        endpoint = url.rsplit("/", 1)[-1]
        self.calls.append((endpoint, dict(params or {}), dict(headers or {})))
        answer = self.handler(endpoint, dict(params or {}))

        if isinstance(answer, Exception):
            raise answer

        return answer


class FakeProvider:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def lookup(self, query):
        self.calls += 1

        if isinstance(self.result, Exception):
            raise self.result

        return self.result


def item(track="Song", artist="Artist", duration=200, synced=SYNCED, plain=PLAIN, instrumental=False):
    return {
        "trackName": track,
        "artistName": artist,
        "duration": duration,
        "instrumental": instrumental,
        "syncedLyrics": synced,
        "plainLyrics": plain,
    }


def query(**kwargs) -> LyricsQuery:
    values = dict(trackhash="hash1", title="Song", artist="Artist", album="Album", duration=200, filepath="")
    values.update(kwargs)
    return LyricsQuery(**values)


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(lyricsfinder, "SERVER_BUSY_PAUSE", 0)


@pytest.fixture
def env(app_env, tmp_path):
    """The temporary library: a song in `music/` and the folder of the plugin data."""
    app_env.paths.lyrics_plugins_path = tmp_path / "plugins" / "lyrics"
    music = tmp_path / "music"
    music.mkdir()
    audio = music / "song.mp3"
    audio.write_bytes(b"audio")
    app_env.audio = audio
    app_env.lrc = music / "song.lrc"
    return app_env


# # # # # # # # # # # # # # # # # # # #
#        Title and artist             #
# # # # # # # # # # # # # # # # # # # #


@pytest.mark.parametrize(
    "title, expected",
    [
        ("CANDY (Remix)", "CANDY"),
        ("Bohemian Rhapsody - Remastered 2011", "Bohemian Rhapsody"),
        ("Heroes (We Could Be) (feat. Tove Lo)", "Heroes (We Could Be)"),
        ("(I Can't Get No) Satisfaction", "(I Can't Get No) Satisfaction"),
        ("Song - 2011 Remaster", "Song"),
        ("Song (Remastered 2011)", "Song"),
        ("Song (Club Remix)", "Song"),
        ("Song [feat. Someone]", "Song"),
        ("Song (ft. Someone)", "Song"),
        ("Song (Radio Edit)", "Song"),
        ("Song (Explicit)", "Song"),
        ("Song [Explicit]", "Song"),
        ("Song (Deluxe Edition)", "Song"),
        ("Song - Single Version", "Song"),
        ("Song (Bonus Track)", "Song"),
        ("Hello (feat. A) [Remastered 2015]", "Hello"),
        ("Song feat. Someone", "Song"),
        ("  Song  ", "Song"),
        ("Song (Live)", "Song (Live)"),
        ("(Remix)", "(Remix)"),
        ("Heroes (We Could Be)", "Heroes (We Could Be)"),
    ],
)
def test_clean_title(title, expected):
    assert clean_title(title) == expected


def test_clean_title_never_gives_an_empty_title():
    assert clean_title("(feat. X)") == "(feat. X)"
    assert clean_title("") == ""


@pytest.mark.parametrize(
    "artist, expected",
    [
        ("Drake feat. Rihanna", "Drake"),
        ("Simon & Garfunkel", "Simon"),
        ("AC/DC", "AC/DC"),
        ("Queen", "Queen"),
        ("  Queen ", "Queen"),
    ],
)
def test_first_artist(artist, expected):
    assert first_artist(artist) == expected


# # # # # # # # # # # # # # # # # # # #
#             LRCLIB                  #
# # # # # # # # # # # # # # # # # # # #


def test_lrclib_gets_the_synced_lyrics_with_the_data_of_the_track():
    session = FakeSession(lambda endpoint, params: FakeResponse(200, item()))

    result = LrclibProvider(session).lookup(query())

    assert result == FoundLyrics(SYNCED, True, "lrclib")
    endpoint, params, headers = session.calls[0]
    assert endpoint == "get"
    assert params == {"track_name": "Song", "artist_name": "Artist", "album_name": "Album", "duration": 200}
    assert headers["User-Agent"].startswith("MUSIX/")
    assert "github.com/rodrigouxp/musix" in headers["User-Agent"]


def test_lrclib_with_only_plain_lyrics():
    session = FakeSession(lambda endpoint, params: FakeResponse(200, item(synced=None)))

    assert LrclibProvider(session).lookup(query()) == FoundLyrics(PLAIN, False, "lrclib")


def test_lrclib_instrumental():
    session = FakeSession(lambda endpoint, params: FakeResponse(200, item(synced=None, plain=None, instrumental=True)))

    assert LrclibProvider(session).lookup(query()) == NotFound("instrumental")


def test_lrclib_with_empty_lyrics_is_not_found():
    session = FakeSession(lambda endpoint, params: FakeResponse(200, item(synced="  \n", plain="")) if endpoint == "get" else FakeResponse(200, []))

    assert LrclibProvider(session).lookup(query()) == NotFound("not_found")


def test_lrclib_tries_the_clean_title_when_the_first_get_is_a_404():
    def handler(endpoint, params):
        if endpoint == "get" and params["track_name"] == "Song":
            return FakeResponse(200, item())
        return FakeResponse(404, {"message": "Failed to find specified track"})

    session = FakeSession(handler)

    result = LrclibProvider(session).lookup(query(title="Song (Remastered 2011)", artist="Artist feat. Other"))

    assert result == FoundLyrics(SYNCED, True, "lrclib")
    assert [c[0] for c in session.calls] == ["get", "get"]
    # the second one: the clean title, the first artist, no album
    assert session.calls[1][1] == {"track_name": "Song", "artist_name": "Artist", "duration": 200}


def test_lrclib_asks_once_more_when_the_server_is_busy():
    answers = iter([FakeResponse(503, {}), FakeResponse(200, item())])
    session = FakeSession(lambda endpoint, params: next(answers))

    assert LrclibProvider(session).lookup(query()) == FoundLyrics(SYNCED, True, "lrclib")
    assert len(session.calls) == 2


def test_lrclib_goes_on_to_the_next_step_when_one_is_busy():
    def handler(endpoint, params):
        if endpoint == "get" and "album_name" in params:
            return FakeResponse(503, {"name": "ServerOverloaded"})
        return FakeResponse(200, item())

    session = FakeSession(handler)

    assert LrclibProvider(session).lookup(query(title="Song (Remix)")) == FoundLyrics(SYNCED, True, "lrclib")
    # the first step: asked, and once more because the server was busy; then the second step works
    assert [c[0] for c in session.calls] == ["get", "get", "get"]


def test_lrclib_that_found_nothing_and_was_busy_once_does_not_say_not_found():
    def handler(endpoint, params):
        if endpoint == "get" and "album_name" in params:
            return FakeResponse(503, {})
        return FakeResponse(404, {}) if endpoint == "get" else FakeResponse(200, [])

    with pytest.raises(ProviderError) as error:
        LrclibProvider(FakeSession(handler)).lookup(query(title="Song (Remix)"))

    assert error.value.rate_limited is True


def test_lrclib_does_not_repeat_the_get_when_the_title_is_already_clean():
    session = FakeSession(lambda endpoint, params: FakeResponse(404, {}) if endpoint == "get" else FakeResponse(200, []))

    assert LrclibProvider(session).lookup(query()) == NotFound("not_found")
    assert [c[0] for c in session.calls] == ["get", "search"]


def test_lrclib_search_takes_a_result_in_time_with_the_audio():
    def handler(endpoint, params):
        if endpoint == "get":
            return FakeResponse(404, {})
        return FakeResponse(200, [item(duration=202.5, synced=None)])

    session = FakeSession(handler)

    assert LrclibProvider(session).lookup(query()) == FoundLyrics(PLAIN, False, "lrclib")
    assert session.calls[-1][1] == {"track_name": "Song", "artist_name": "Artist"}


def test_lrclib_search_leaves_out_a_result_of_another_duration():
    def handler(endpoint, params):
        if endpoint == "get":
            return FakeResponse(404, {})
        return FakeResponse(200, [item(duration=204), item(duration=150), item(duration=260)])

    assert LrclibProvider(FakeSession(handler)).lookup(query()) == NotFound("not_found")


def test_lrclib_search_prefers_synced_and_then_the_closest_duration():
    answers = [
        item(duration=202, synced=None),
        item(duration=203, synced="[00:01.00]far synced"),
        item(duration=200.5, synced="[00:01.00]near synced"),
    ]

    def handler(endpoint, params):
        return FakeResponse(404, {}) if endpoint == "get" else FakeResponse(200, answers)

    result = LrclibProvider(FakeSession(handler)).lookup(query())

    assert result == FoundLyrics("[00:01.00]near synced", True, "lrclib")


def test_lrclib_search_without_duration_takes_the_first_synced():
    def handler(endpoint, params):
        return FakeResponse(404, {}) if endpoint == "get" else FakeResponse(200, [item(duration=10), item(duration=500)])

    assert LrclibProvider(FakeSession(handler)).lookup(query(duration=0)).synced


@pytest.mark.parametrize(
    "answer, rate_limited",
    [
        (requests.ConnectionError("down"), False),
        (requests.Timeout("slow"), False),
        (FakeResponse(429, {}), True),
        (FakeResponse(503, {}), True),
        (FakeResponse(403, {}), False),
        (FakeResponse(200, bad_json=True), False),
    ],
)
def test_lrclib_that_cannot_answer_raises_provider_error(answer, rate_limited):
    provider = LrclibProvider(FakeSession(lambda endpoint, params: answer))

    with pytest.raises(ProviderError) as error:
        provider.lookup(query())

    assert error.value.rate_limited is rate_limited


# # # # # # # # # # # # # # # # # # # #
#         The chain of providers      #
# # # # # # # # # # # # # # # # # # # #


def test_the_first_provider_that_has_the_lyrics_wins():
    first = FakeProvider(FoundLyrics(SYNCED, True, "lrclib"))
    second = FakeProvider(FoundLyrics(SYNCED, True, "musixmatch"))

    assert find_lyrics(query(), [first, second]).source == "lrclib"
    assert second.calls == 0


def test_the_backup_provider_is_asked_when_the_first_has_nothing():
    first = FakeProvider(NotFound("not_found"))
    second = FakeProvider(FoundLyrics(SYNCED, True, "musixmatch"))

    assert find_lyrics(query(), [first, second]) == FoundLyrics(SYNCED, True, "musixmatch")


def test_the_backup_provider_is_asked_when_the_first_is_down():
    first = FakeProvider(ProviderError("down"))
    second = FakeProvider(FoundLyrics(SYNCED, True, "musixmatch"))

    assert find_lyrics(query(), [first, second]).source == "musixmatch"


def test_instrumental_stops_the_chain():
    second = FakeProvider(FoundLyrics(SYNCED, True, "musixmatch"))

    assert find_lyrics(query(), [FakeProvider(NotFound("instrumental")), second]) == NotFound("instrumental")
    assert second.calls == 0


def test_when_every_provider_fails_it_is_a_network_error():
    result = find_lyrics(query(), [FakeProvider(ProviderError("a")), FakeProvider(ProviderError("b", rate_limited=True))])

    assert result == NotFound("network", cacheable=False, rate_limited=True)


def test_nothing_found_is_a_final_not_found_unless_a_provider_was_down():
    assert find_lyrics(query(), [FakeProvider(NotFound("not_found")), FakeProvider(NotFound("not_found"))]) == NotFound("not_found")

    partial = find_lyrics(query(), [FakeProvider(NotFound("not_found")), FakeProvider(ProviderError("down"))])
    assert partial == NotFound("not_found", cacheable=False)


class FakeMusixmatch:
    def __init__(self, candidates=None, lrc=None, fail=False):
        self.candidates = candidates if candidates is not None else []
        self.lrc = lrc
        self.fail = fail
        self.network_error = False
        self.asked = []

    def get_lrc(self, title, artist):
        self.asked.append((title, artist))
        self.network_error = self.fail
        return self.candidates

    def get_lrc_by_id(self, track_id):
        return self.lrc


def test_the_musixmatch_adapter_gives_synced_lyrics_and_asks_with_the_clean_title():
    candidates = [
        {"track_id": 1, "title": "Other", "album": "Other", "artist": "Artist", "image": ""},
        {"track_id": 2, "title": "Song", "album": "Album", "artist": "Artist", "image": ""},
    ]
    fake = FakeMusixmatch(candidates, lrc=SYNCED)

    result = MusixmatchProvider(fake).lookup(query(title="Song (Remix)"))

    assert result == FoundLyrics(SYNCED, True, "musixmatch")
    assert fake.asked == [("Song", "Artist")]


def test_the_musixmatch_adapter_with_no_result_or_an_empty_lyrics():
    assert MusixmatchProvider(FakeMusixmatch([])).lookup(query()) == NotFound("not_found")

    candidate = {"track_id": 1, "title": "Song", "album": "Album", "artist": "Artist", "image": ""}
    assert MusixmatchProvider(FakeMusixmatch([candidate], lrc="  \n")).lookup(query()) == NotFound("not_found")


def test_the_musixmatch_adapter_that_cannot_ask_raises_provider_error():
    with pytest.raises(ProviderError):
        MusixmatchProvider(FakeMusixmatch([], fail=True)).lookup(query())


# # # # # # # # # # # # # # # # # # # #
#        The "not found" memory       #
# # # # # # # # # # # # # # # # # # # #


def test_a_miss_is_remembered_for_30_days(env):
    now = datetime(2026, 10, 24, 12, 0, 0)
    record_miss("h", "not_found", now=now - timedelta(days=29))
    assert get_miss("h", now) == "not_found"

    record_miss("h", "not_found", now=now - timedelta(days=31))
    assert get_miss("h", now) is None


def test_instrumental_is_remembered_for_a_year(env):
    now = datetime(2026, 10, 24, 12, 0, 0)
    record_miss("h", "instrumental", now=now - timedelta(days=364))
    assert get_miss("h", now) == "instrumental"

    record_miss("h", "instrumental", now=now - timedelta(days=366))
    assert get_miss("h", now) is None


def test_temporary_failures_are_not_remembered(env):
    for reason in ("network", "write_failed", "plugin_off"):
        record_miss("h", reason)

    assert get_miss("h") is None
    assert not (env.paths.lyrics_plugins_path / "misses.json").exists()


def test_a_corrupted_memory_file_is_an_empty_one(env):
    folder = env.paths.lyrics_plugins_path
    folder.mkdir(parents=True)
    (folder / "misses.json").write_text("{not json", encoding="utf-8")

    assert get_miss("h") is None

    record_miss("h", "not_found")
    assert get_miss("h") == "not_found"
    assert json.loads((folder / "misses.json").read_text(encoding="utf-8"))["h"]["reason"] == "not_found"


def test_an_old_entry_with_a_wrong_date_is_ignored(env):
    folder = env.paths.lyrics_plugins_path
    folder.mkdir(parents=True)
    (folder / "misses.json").write_text(json.dumps({"h": {"reason": "not_found", "date": "yesterday"}}), encoding="utf-8")

    assert get_miss("h") is None


# # # # # # # # # # # # # # # # # # # #
#            Saving the file          #
# # # # # # # # # # # # # # # # # # # #


def test_the_lyrics_are_saved_as_they_came_with_a_final_new_line(env):
    text = "[00:01.00]Olá, coração\r\n[00:02.00]Ação e reação"

    assert save_lyrics(env.audio.as_posix(), FoundLyrics(text, True, "lrclib")) is None

    saved = env.lrc.read_bytes()
    assert saved == "[00:01.00]Olá, coração\n[00:02.00]Ação e reação\n".encode("utf-8")
    assert [p.name for p in env.audio.parent.iterdir() if p.name.endswith(".tmp")] == []


def test_a_lrc_with_text_is_never_replaced(env):
    env.lrc.write_text("my own lyrics\n", encoding="utf-8")

    assert save_lyrics(env.audio.as_posix(), FoundLyrics(SYNCED, True, "lrclib")) == "exists"
    assert env.lrc.read_text(encoding="utf-8") == "my own lyrics\n"


@pytest.mark.parametrize("content", ["", "   \n\n"])
def test_an_empty_lrc_counts_as_none(env, content):
    env.lrc.write_text(content, encoding="utf-8")

    assert save_lyrics(env.audio.as_posix(), FoundLyrics(PLAIN, False, "lrclib")) is None
    assert env.lrc.read_text(encoding="utf-8") == PLAIN + "\n"


def test_plain_lyrics_are_replaced_by_synced_ones_only_when_asked(env):
    env.lrc.write_text(PLAIN + "\n", encoding="utf-8")
    synced = FoundLyrics(SYNCED, True, "lrclib")

    assert save_lyrics(env.audio.as_posix(), synced) == "exists"
    assert save_lyrics(env.audio.as_posix(), synced, replace_unsynced=True) is None
    assert env.lrc.read_text(encoding="utf-8") == SYNCED


def test_synced_lyrics_are_never_replaced_not_even_when_asked(env):
    env.lrc.write_text(SYNCED, encoding="utf-8")

    for lyrics in (FoundLyrics(PLAIN, False, "lrclib"), FoundLyrics("[00:09.00]other", True, "lrclib")):
        assert save_lyrics(env.audio.as_posix(), lyrics, replace_unsynced=True) == "exists"

    assert env.lrc.read_text(encoding="utf-8") == SYNCED


def test_it_does_not_write_outside_of_the_root_dirs(env, tmp_path):
    outside = tmp_path / "private" / "song.mp3"
    outside.parent.mkdir()
    outside.write_bytes(b"x")

    assert save_lyrics(outside.as_posix(), FoundLyrics(SYNCED, True, "lrclib")) == "write_failed"
    assert not (outside.parent / "song.lrc").exists()


def test_a_folder_that_cannot_be_written_is_write_failed(env, monkeypatch):
    def fail(*args, **kwargs):
        raise PermissionError("read only")

    monkeypatch.setattr(os, "replace", fail)

    assert save_lyrics(env.audio.as_posix(), FoundLyrics(SYNCED, True, "lrclib")) == "write_failed"
    assert not env.lrc.exists()
    assert [p.name for p in env.audio.parent.iterdir() if p.name.endswith(".tmp")] == []


# # # # # # # # # # # # # # # # # # # #
#            Find and save            #
# # # # # # # # # # # # # # # # # # # #


def test_find_and_save_saves_and_reports(env):
    provider = FakeProvider(FoundLyrics(SYNCED, True, "lrclib"))

    result = find_and_save(query(filepath=env.audio.as_posix()), providers=[provider])

    assert (result.reason, result.synced, result.source) == (None, True, "lrclib")
    assert env.lrc.read_text(encoding="utf-8") == SYNCED


def test_a_song_without_lyrics_is_not_looked_up_again_by_the_app(env):
    provider = FakeProvider(NotFound("not_found"))
    q = query(filepath=env.audio.as_posix())

    assert find_and_save(q, providers=[provider]).reason == "not_found"
    assert find_and_save(q, providers=[provider]).reason == "not_found"

    assert provider.calls == 1


def test_the_user_pressing_the_button_ignores_the_memory_and_clears_it_when_found(env):
    q = query(filepath=env.audio.as_posix())
    record_miss(q.trackhash, "not_found")
    provider = FakeProvider(FoundLyrics(PLAIN, False, "lrclib"))

    result = find_and_save(q, use_cache=False, providers=[provider])

    assert result.reason is None and result.text == PLAIN
    assert provider.calls == 1
    assert get_miss(q.trackhash) is None


def test_a_network_failure_is_not_remembered(env):
    provider = FakeProvider(ProviderError("down"))
    q = query(filepath=env.audio.as_posix())

    assert find_and_save(q, providers=[provider]).reason == "network"
    assert get_miss(q.trackhash) is None

    assert find_and_save(q, providers=[provider]).reason == "network"
    assert provider.calls == 2


def test_instrumental_is_remembered(env):
    provider = FakeProvider(NotFound("instrumental"))
    q = query(filepath=env.audio.as_posix())

    assert find_and_save(q, providers=[provider]).reason == "instrumental"
    assert find_and_save(q, providers=[provider]).reason == "instrumental"
    assert provider.calls == 1


def test_outside_of_the_root_dirs_nothing_is_asked(env, tmp_path):
    provider = FakeProvider(FoundLyrics(SYNCED, True, "lrclib"))
    outside = tmp_path / "private" / "song.mp3"

    result = find_and_save(query(filepath=outside.as_posix()), providers=[provider])

    assert result.reason == "write_failed"
    assert provider.calls == 0


def test_a_write_failure_says_the_path(env, monkeypatch):
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(PermissionError()))
    provider = FakeProvider(FoundLyrics(SYNCED, True, "lrclib"))

    result = find_and_save(query(filepath=env.audio.as_posix()), providers=[provider])

    assert result.reason == "write_failed"
    assert result.detail == env.lrc.as_posix()


def test_a_lyrics_that_must_not_be_replaced_is_reported_as_it_is(env):
    env.lrc.write_text(SYNCED, encoding="utf-8")
    provider = FakeProvider(FoundLyrics(PLAIN, False, "lrclib"))

    result = find_and_save(query(filepath=env.audio.as_posix()), replace_unsynced=True, providers=[provider])

    assert result.reason is None
    assert result.synced is True
    assert env.lrc.read_text(encoding="utf-8") == SYNCED


# # # # # # # # # # # # # # # # # # # #
#              The API                #
# # # # # # # # # # # # # # # # # # # #


@pytest.fixture
def http(env, monkeypatch):
    providers: list = []
    state = {"on": True}
    monkeypatch.setattr(lyrics_api, "lyrics_plugin_on", lambda: state["on"])
    monkeypatch.setattr(lyricsfinder, "default_providers", lambda: providers)

    app = OpenAPI(__name__)
    app.register_api(lyrics_api.api)
    client = app.test_client()
    client.providers = providers
    client.state = state
    client.audio = env.audio
    client.lrc = env.lrc
    return client


def search(http, **extra):
    body = {
        "trackhash": TRACKHASH,
        "title": "Song",
        "artist": "Artist",
        "album": "Album",
        "filepath": http.audio.as_posix(),
    }
    body.update(extra)
    return http.post("/plugins/lyrics/search", json=body)


def test_the_api_with_synced_lyrics(http):
    http.providers.append(FakeProvider(FoundLyrics(SYNCED, True, "lrclib")))

    res = search(http, duration=200)

    assert res.status_code == 200
    assert res.json["reason"] is None
    assert res.json["synced"] is True
    assert res.json["source"] == "lrclib"
    assert res.json["trackhash"] == TRACKHASH
    assert res.json["lyrics"] == [{"time": 1000.0, "text": "Is this the real life?"}, {"time": 3500.0, "text": "Is this just fantasy?"}]
    assert http.lrc.exists()


def test_the_api_with_plain_lyrics_saves_them_and_lets_the_client_load_them(http):
    http.providers.append(FakeProvider(FoundLyrics(PLAIN, False, "lrclib")))

    res = search(http)

    assert res.status_code == 200
    assert res.json["lyrics"] is None
    assert res.json["synced"] is False
    assert res.json["source"] == "lrclib"
    assert res.json["reason"] is None
    assert http.lrc.read_text(encoding="utf-8") == PLAIN + "\n"


def test_the_api_says_why_there_is_nothing(http):
    http.providers.append(FakeProvider(NotFound("not_found")))
    assert search(http).json["reason"] == "not_found"

    http.providers[:] = [FakeProvider(NotFound("instrumental"))]
    assert search(http, trackhash="1853280a12345678").json["reason"] == "instrumental"

    http.providers[:] = [FakeProvider(ProviderError("down"))]
    assert search(http, trackhash="2853280a12345678").json["reason"] == "network"


def test_the_api_with_the_plugin_off(http):
    http.state["on"] = False
    provider = FakeProvider(FoundLyrics(SYNCED, True, "lrclib"))
    http.providers.append(provider)

    res = search(http)

    assert res.status_code == 200
    assert res.json["reason"] == "plugin_off"
    assert res.json["lyrics"] is None
    assert provider.calls == 0


def test_the_api_automatic_search_respects_the_memory_and_the_button_does_not(http):
    provider = FakeProvider(NotFound("not_found"))
    http.providers.append(provider)

    assert search(http, auto=True).json["reason"] == "not_found"
    assert search(http, auto=True).json["reason"] == "not_found"
    assert provider.calls == 1

    assert search(http).json["reason"] == "not_found"
    assert provider.calls == 2


def test_the_api_write_failure_says_the_path(http, monkeypatch):
    http.providers.append(FakeProvider(FoundLyrics(SYNCED, True, "lrclib")))
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(PermissionError()))

    res = search(http)

    assert res.json["reason"] == "write_failed"
    assert res.json["path"] == http.lrc.as_posix()


def test_the_api_replaces_plain_lyrics_only_when_asked(http):
    http.lrc.write_text(PLAIN + "\n", encoding="utf-8")
    http.providers.append(FakeProvider(FoundLyrics(SYNCED, True, "lrclib")))

    search(http)
    assert http.lrc.read_text(encoding="utf-8") == PLAIN + "\n"

    res = search(http, replace_unsynced=True)
    assert http.lrc.read_text(encoding="utf-8") == SYNCED
    assert res.json["synced"] is True
