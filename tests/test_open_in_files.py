import pytest
from flask_openapi3 import OpenAPI

from musix.api import folder as folder_api
from musix.utils.paths import files_url_template, to_host_path

TEMPLATE = "{origin}/modules/icewhale_files/index.html#/files/{path}"


@pytest.fixture
def host_paths(monkeypatch):
    monkeypatch.setenv("MUSIX_HOST_PATHS", "/music=/HD_1_TB/Músicas")


class TestToHostPath:
    def test_replaces_the_prefix(self, host_paths):
        assert to_host_path("/music/2Pac/[1991] 2Pacalypse Now") == "/HD_1_TB/Músicas/2Pac/[1991] 2Pacalypse Now"

    def test_the_folder_of_the_pair_itself(self, host_paths):
        assert to_host_path("/music") == "/HD_1_TB/Músicas"
        assert to_host_path("/music/") == "/HD_1_TB/Músicas"

    def test_a_folder_that_only_starts_with_the_same_text_does_not_match(self, host_paths):
        assert to_host_path("/music2/song.mp3") is None
        assert to_host_path("/musical") is None

    def test_the_first_pair_that_holds_the_path_wins(self, monkeypatch):
        monkeypatch.setenv("MUSIX_HOST_PATHS", "/music/live=/HD_2/Live ; /music=/HD_1/Músicas;/other=/HD_3")

        assert to_host_path("/music/live/a") == "/HD_2/Live/a"
        assert to_host_path("/music/studio/a") == "/HD_1/Músicas/studio/a"
        assert to_host_path("/other/x") == "/HD_3/x"

    def test_without_configuration(self, monkeypatch):
        monkeypatch.delenv("MUSIX_HOST_PATHS", raising=False)

        assert to_host_path("/music/a") is None

    def test_broken_pairs_are_ignored(self, monkeypatch):
        monkeypatch.setenv("MUSIX_HOST_PATHS", "nothing;=/x;/y=;/music=/HD")

        assert to_host_path("/music/a") == "/HD/a"
        assert to_host_path("/y/a") is None

    def test_accents_and_spaces_are_kept(self, host_paths):
        assert to_host_path("/music/Música Brasileira/Ação e Reação") == "/HD_1_TB/Músicas/Música Brasileira/Ação e Reação"

    def test_the_template(self, monkeypatch):
        monkeypatch.delenv("MUSIX_FILES_URL", raising=False)
        assert files_url_template() is None

        monkeypatch.setenv("MUSIX_FILES_URL", f" {TEMPLATE} ")
        assert files_url_template() == TEMPLATE


@pytest.fixture
def http(app_env, host_paths, monkeypatch):
    monkeypatch.setenv("MUSIX_FILES_URL", TEMPLATE)
    music = app_env.root / "music"
    album = music / "2Pac" / "[1991] 2Pacalypse Now"
    album.mkdir(parents=True)
    (album / "song.mp3").write_bytes(b"x")
    monkeypatch.setenv("MUSIX_HOST_PATHS", f"{music.as_posix()}=/HD_1_TB/Músicas")

    app = OpenAPI(__name__)
    app.register_api(folder_api.api)
    client = app.test_client()
    client.album = album
    client.music = music
    return client


def show(http, path):
    return http.get("/folder/show-in-files", query_string={"path": str(path)})


def test_a_song_gives_the_folder_where_it_is(http):
    res = show(http, http.album / "song.mp3")

    assert res.status_code == 200
    assert res.json == {
        "success": True,
        "url_template": TEMPLATE,
        "path": "/HD_1_TB/Músicas/2Pac/[1991] 2Pacalypse Now",
    }


def test_a_folder_gives_itself(http):
    res = show(http, http.music / "2Pac")

    assert res.status_code == 200
    assert res.json["path"] == "/HD_1_TB/Músicas/2Pac"


def test_without_the_variables_it_is_a_501(http, monkeypatch):
    monkeypatch.delenv("MUSIX_FILES_URL")
    assert show(http, http.album).status_code == 501
    assert show(http, http.album).json["error"] == "not_configured"

    monkeypatch.setenv("MUSIX_FILES_URL", TEMPLATE)
    monkeypatch.delenv("MUSIX_HOST_PATHS")
    assert show(http, http.album).status_code == 501
    assert show(http, http.album).json["error"] == "not_configured"


def test_a_folder_that_no_pair_holds_is_a_501_not_mapped(http, monkeypatch):
    monkeypatch.setenv("MUSIX_HOST_PATHS", "/somewhere/else=/HD")

    res = show(http, http.album)

    assert res.status_code == 501
    assert res.json["error"] == "not_mapped"


def test_outside_of_the_root_dirs_is_a_403(http, app_env):
    outside = app_env.root / "private"
    outside.mkdir()

    assert show(http, outside).status_code == 403


def test_a_path_that_does_not_exist_is_a_404(http):
    assert show(http, http.music / "nothing here").status_code == 404
