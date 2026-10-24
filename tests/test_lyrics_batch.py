import threading
from types import SimpleNamespace

import pytest
from flask_openapi3 import OpenAPI

from musix.api import auth as auth_api
from musix.api.plugins import lyrics as lyrics_api
from musix.lib import lyricsbatch
from musix.lib.lyricsbatch import LyricsBatch, RateLimiter, missing_tracks
from musix.lib.lyricsfinder import FoundLyrics, NotFound, ProviderError, get_miss, record_miss
from musix.store.tracks import TrackGroup, TrackStore

SYNCED = "[00:01.00]one\n[00:02.00]two\n"
PLAIN = "one\ntwo\n"


class ScriptedProvider:
    """Answers by the title of the song. `answers` maps a title to a result or an exception."""

    name = "scripted"

    def __init__(self, answers):
        self.answers = answers
        self.asked: list[str] = []
        self.on_ask = None

    def lookup(self, query):
        self.asked.append(query.title)

        if self.on_ask:
            self.on_ask(query)

        answer = self.answers.get(query.title, NotFound("not_found"))

        if isinstance(answer, list):
            answer = answer.pop(0)

        if isinstance(answer, Exception):
            raise answer

        return answer


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(lyricsbatch, "REQUEST_INTERVAL", 0)
    monkeypatch.setattr("musix.lib.lyricsfinder.SERVER_BUSY_PAUSE", 0)


@pytest.fixture
def lib(app_env, tmp_path, monkeypatch):
    """A fake library: `lib.add("Title")` puts a song in the store and a file in `music/`."""
    app_env.paths.lyrics_plugins_path = tmp_path / "plugins" / "lyrics"
    music = tmp_path / "music"
    music.mkdir()
    groups: dict[str, TrackGroup] = {}
    monkeypatch.setattr(TrackStore, "trackhashmap", groups)

    class Lib:
        env = app_env
        folder = music
        counter = 0

        @classmethod
        def add(cls, title, *, artist="Artist", bitrate=320, trackhash=None, extra=None, name=None):
            cls.counter += 1
            trackhash = trackhash or f"{cls.counter:016x}"
            path = music / f"{name or title}-{cls.counter}.mp3"
            path.write_bytes(b"audio")
            track = SimpleNamespace(
                trackhash=trackhash,
                title=title,
                artists=[{"name": artist, "artisthash": "x"}],
                album="Album",
                duration=200,
                filepath=path.as_posix(),
                bitrate=bitrate,
                extra=extra or {},
            )
            groups.setdefault(trackhash, TrackGroup([])).append(track)
            return track

        @staticmethod
        def lrc(track):
            return TrackLrc(track)

    return Lib


class TrackLrc:
    def __init__(self, track):
        from pathlib import Path

        self.path = Path(track.filepath).with_suffix(".lrc")

    def exists(self):
        return self.path.is_file()

    def text(self):
        return self.path.read_text(encoding="utf-8")


def make_batch(provider, sleeps=None):
    return LyricsBatch(
        providers_factory=lambda: [provider],
        sleep=(sleeps.append if sleeps is not None else (lambda seconds: None)),
    )


def run(batch):
    assert batch.start()
    batch.join(10)
    return batch.status()


# # # # # # # # # # # # # # # # # # # #
#         What is missing             #
# # # # # # # # # # # # # # # # # # # #


def test_it_counts_only_the_songs_without_lyrics(lib):
    missing = lib.add("Missing")
    with_lrc = lib.add("With lrc")
    lib.lrc(with_lrc).path.write_text(SYNCED, encoding="utf-8")
    lib.add("With tag", extra={"lyrics": "words in the tag"})
    lib.add("Recent miss", trackhash="a" * 16)
    record_miss("a" * 16, "not_found")
    empty = lib.add("Empty lrc")
    lib.lrc(empty).path.write_text("  \n", encoding="utf-8")

    # a duplicate (same trackhash, other file): the .lrc of one of them is enough
    first = lib.add("Duplicate", trackhash="b" * 16, bitrate=128)
    lib.add("Duplicate", trackhash="b" * 16, bitrate=320, name="copy")
    lib.lrc(first).path.write_text(PLAIN, encoding="utf-8")

    tracks, total = missing_tracks()

    assert total == 6 + 0  # six trackhashes (the duplicate is one)
    assert sorted(t.title for t in tracks) == ["Empty lrc", "Missing"]
    assert missing in tracks


def test_a_song_with_many_files_is_looked_up_with_the_best_one(lib):
    lib.add("Song", trackhash="c" * 16, bitrate=128, name="low")
    best = lib.add("Song", trackhash="c" * 16, bitrate=320, name="high")

    tracks, total = missing_tracks()

    assert total == 1
    assert tracks == [best]


# # # # # # # # # # # # # # # # # # # #
#             The job                 #
# # # # # # # # # # # # # # # # # # # #


def build_scenario(lib):
    synced1 = lib.add("Synced one")
    synced2 = lib.add("Synced two")
    plain = lib.add("Plain")
    missing = lib.add("Missing")
    unwritable = lib.add("Unwritable")
    # a folder where the .lrc goes: the file cannot be written
    lib.lrc(unwritable).path.mkdir()

    provider = ScriptedProvider(
        {
            "Synced one": FoundLyrics(SYNCED, True, "lrclib"),
            "Synced two": FoundLyrics(SYNCED, True, "musixmatch"),
            "Plain": FoundLyrics(PLAIN, False, "lrclib"),
            "Missing": NotFound("not_found"),
            "Unwritable": FoundLyrics(SYNCED, True, "lrclib"),
        }
    )
    return provider, (synced1, synced2, plain, missing, unwritable)


def test_a_full_run_and_a_second_one(lib):
    provider, (synced1, synced2, plain, missing, unwritable) = build_scenario(lib)
    batch = make_batch(provider)

    status = run(batch)

    assert (status["running"], status["finished"], status["cancelled"], status["aborted_reason"]) == (False, True, False, None)
    assert (status["total"], status["done"]) == (5, 5)
    assert (status["found_synced"], status["found_plain"], status["not_found"], status["instrumental"]) == (2, 1, 1, 0)
    assert status["errors"] == {unwritable.filepath: "write_failed"}
    assert status["current"] is None
    assert lib.lrc(synced1).text() == SYNCED
    assert lib.lrc(plain).text() == PLAIN
    assert not lib.lrc(missing).exists()
    assert get_miss(missing.trackhash) == "not_found"

    # again: the ones with lyrics and the "not found" are left alone; the one that failed is tried again
    provider.asked.clear()
    status = run(batch)

    assert provider.asked == ["Unwritable"]
    assert status["total"] == 1
    assert status["errors"] == {unwritable.filepath: "write_failed"}


def test_it_never_replaces_a_lrc_that_has_text(lib):
    song = lib.add("Mine")
    provider = ScriptedProvider({"Mine": FoundLyrics(SYNCED, True, "lrclib")})
    batch = make_batch(provider)
    lib.lrc(song).path.write_text("my own words\n", encoding="utf-8")

    status = run(batch)

    # it was not even a candidate
    assert status["total"] == 0
    assert provider.asked == []
    assert lib.lrc(song).text() == "my own words\n"


def test_the_current_song_is_shown_while_it_runs(lib):
    lib.add("Hero", artist="Queen")
    seen = []
    provider = ScriptedProvider({})
    batch = make_batch(provider)
    provider.on_ask = lambda query: seen.append(batch.status()["current"])

    run(batch)

    assert seen == ["Queen - Hero"]


def test_cancel_stops_after_the_song_in_progress(lib):
    for n in range(5):
        lib.add(f"Song {n}")

    provider = ScriptedProvider({})
    batch = make_batch(provider)
    provider.on_ask = lambda query: batch.cancel() if len(provider.asked) == 2 else None

    status = run(batch)

    assert len(provider.asked) == 2
    assert status["done"] == 2
    assert (status["cancelled"], status["finished"], status["running"]) == (True, True, False)
    assert status["aborted_reason"] is None


def test_three_network_failures_in_a_row_abort_the_job(lib):
    for n in range(6):
        lib.add(f"Song {n}")

    provider = ScriptedProvider({f"Song {n}": ProviderError("down") for n in range(6)})
    status = run(make_batch(provider))

    assert status["aborted_reason"] == "network"
    assert (status["done"], status["total"]) == (3, 6)
    assert len(provider.asked) == 3
    assert len(status["errors"]) == 3 and set(status["errors"].values()) == {"network"}
    # the failures are not "not found": nothing is remembered
    assert all(get_miss(t.trackhash) is None for g in TrackStore.trackhashmap.values() for t in g.tracks)


def test_a_success_between_failures_resets_the_count(lib):
    for n in range(5):
        lib.add(f"Song {n}")

    answers = {
        "Song 0": ProviderError("down"),
        "Song 1": ProviderError("down"),
        "Song 2": FoundLyrics(PLAIN, False, "lrclib"),
        "Song 3": ProviderError("down"),
        "Song 4": ProviderError("down"),
    }
    status = run(make_batch(ScriptedProvider(answers)))

    assert status["aborted_reason"] is None
    assert status["done"] == 5


def test_too_many_requests_wait_and_try_again(lib):
    lib.add("Busy")
    sleeps: list[float] = []
    provider = ScriptedProvider(
        {"Busy": [ProviderError("429", rate_limited=True), ProviderError("429", rate_limited=True), FoundLyrics(SYNCED, True, "lrclib")]}
    )

    status = run(make_batch(provider, sleeps))

    assert sleeps == [4.0, 8.0]
    assert provider.asked == ["Busy"] * 3
    assert status["found_synced"] == 1
    assert status["errors"] == {}


def test_it_gives_up_on_a_song_after_three_retries(lib):
    song = lib.add("Busy")
    sleeps: list[float] = []
    provider = ScriptedProvider({"Busy": [ProviderError("429", rate_limited=True)] * 4})

    status = run(make_batch(provider, sleeps))

    assert sleeps == [4.0, 8.0, 16.0]
    assert provider.asked == ["Busy"] * 4
    assert status["errors"] == {song.filepath: "network"}
    assert get_miss(song.trackhash) is None


def test_the_wait_has_a_limit(monkeypatch, lib):
    monkeypatch.setattr(lyricsbatch, "BACKOFF_BASE", 40.0)
    lib.add("Busy")
    sleeps: list[float] = []
    provider = ScriptedProvider({"Busy": [ProviderError("503", rate_limited=True)] * 4})

    run(make_batch(provider, sleeps))

    assert sleeps == [40.0, 60.0, 60.0]


def test_errors_keep_only_the_last_ones(monkeypatch, lib):
    monkeypatch.setattr(lyricsbatch, "MAX_ERRORS_KEPT", 3)
    monkeypatch.setattr(lyricsbatch, "NETWORK_FAILURES_TO_ABORT", 99)

    for n in range(5):
        lib.add(f"Song {n}")

    status = run(make_batch(ScriptedProvider({f"Song {n}": ProviderError("down") for n in range(5)})))

    assert len(status["errors"]) == 3
    assert status["done"] == 5


def test_a_bug_in_a_provider_does_not_leave_the_job_running(lib):
    lib.add("Song")
    provider = ScriptedProvider({})
    provider.on_ask = lambda query: (_ for _ in ()).throw(RuntimeError("boom"))

    status = run(make_batch(provider))

    assert status["running"] is False and status["finished"] is True


def test_the_limiter_waits_between_requests():
    waits: list[float] = []
    limiter = RateLimiter(0.5, sleep=waits.append)

    limiter.wait()
    limiter.wait()
    limiter.wait()

    assert waits[0] <= 0.5 and 0.3 < waits[0]
    assert len(waits) == 2
    assert waits[1] > waits[0]


# # # # # # # # # # # # # # # # # # # #
#              The API                #
# # # # # # # # # # # # # # # # # # # #


@pytest.fixture
def http(lib, monkeypatch):
    state = {"on": True, "provider": ScriptedProvider({})}
    monkeypatch.setattr(auth_api, "current_user", {"roles": ["admin"]})
    monkeypatch.setattr(lyrics_api, "lyrics_plugin_on", lambda: state["on"])
    monkeypatch.setattr(lyricsbatch, "batch", LyricsBatch(providers_factory=lambda: [state["provider"]], sleep=lambda s: None))

    app = OpenAPI(__name__)
    app.register_api(lyrics_api.api)
    client = app.test_client()
    client.state = state
    return client


def test_the_api_count(http, lib):
    lib.add("One")
    lib.add("Two", extra={"lyrics": "x"})

    res = http.get("/plugins/lyrics/missing/count")

    assert res.status_code == 200
    assert res.json == {"missing": 1, "total": 2, "plugin_on": True}


def test_the_api_start_status_and_the_result(http, lib):
    song = lib.add("One")
    http.state["provider"] = ScriptedProvider({"One": FoundLyrics(SYNCED, True, "lrclib")})

    started = http.post("/plugins/lyrics/missing/start")
    lyricsbatch.batch.join(10)
    status = http.get("/plugins/lyrics/missing/status")

    assert started.status_code == 200
    assert started.json["total"] == 1
    assert status.json["finished"] is True and status.json["found_synced"] == 1
    assert lib.lrc(song).text() == SYNCED


def test_the_api_start_with_the_plugin_off_is_a_400(http, lib):
    lib.add("One")
    http.state["on"] = False

    res = http.post("/plugins/lyrics/missing/start")

    assert res.status_code == 400
    assert res.json["reason"] == "plugin_off"
    assert not lyricsbatch.batch.status()["running"]


def test_the_api_start_while_running_is_a_409_and_cancel_stops_it(http, lib):
    for n in range(3):
        lib.add(f"Song {n}")

    release = threading.Event()
    entered = threading.Event()
    provider = ScriptedProvider({})

    def block(query):
        entered.set()
        release.wait(10)

    provider.on_ask = block
    http.state["provider"] = provider

    assert http.post("/plugins/lyrics/missing/start").status_code == 200
    assert entered.wait(10)

    assert http.post("/plugins/lyrics/missing/start").status_code == 409
    assert http.get("/plugins/lyrics/missing/status").json["running"] is True

    cancelled = http.post("/plugins/lyrics/missing/cancel")
    release.set()
    lyricsbatch.batch.join(10)
    status = http.get("/plugins/lyrics/missing/status").json

    assert cancelled.status_code == 200
    assert status["cancelled"] is True and status["running"] is False
    assert status["done"] == 1


@pytest.mark.parametrize(
    "method, url",
    [
        ("get", "/plugins/lyrics/missing/count"),
        ("post", "/plugins/lyrics/missing/start"),
        ("get", "/plugins/lyrics/missing/status"),
        ("post", "/plugins/lyrics/missing/cancel"),
    ],
)
def test_the_api_is_only_for_admins(http, lib, monkeypatch, method, url):
    lib.add("One")
    monkeypatch.setattr(auth_api, "current_user", {"roles": []})

    res = getattr(http, method)(url)

    assert res.status_code == 403
    assert not lyricsbatch.batch.status()["running"]
