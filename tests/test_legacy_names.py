from pathlib import Path

from musix.utils.legacy_names import migrate_legacy_names


def _touch(path: Path, text: str = "x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_old_config_folder_is_renamed(tmp_path: Path):
    parent = tmp_path / "config"
    home = tmp_path / "home"
    home.mkdir()
    _touch(parent / "swingmusic" / "settings.json", "{}")

    migrate_legacy_names(parent, home)

    assert not (parent / "swingmusic").exists()
    assert (parent / "musix" / "settings.json").read_text() == "{}"


def test_hidden_folder_is_used_when_parent_is_home(tmp_path: Path):
    home = tmp_path / "home"
    _touch(home / ".swingmusic" / "settings.json", "{}")

    migrate_legacy_names(home, home)

    assert not (home / ".swingmusic").exists()
    assert (home / ".musix" / "settings.json").exists()


def test_database_and_wal_files_are_renamed(tmp_path: Path):
    parent = tmp_path / "config"
    home = tmp_path / "home"
    home.mkdir()
    old = parent / "swingmusic"
    _touch(old / "swingmusic.db", "db")
    _touch(old / "swingmusic.db-wal", "wal")
    _touch(old / "swingmusic.db-shm", "shm")
    _touch(old / "userdata.db", "keep")

    migrate_legacy_names(parent, home)

    new = parent / "musix"
    assert (new / "musix.db").read_text() == "db"
    assert (new / "musix.db-wal").read_text() == "wal"
    assert (new / "musix.db-shm").read_text() == "shm"
    assert (new / "userdata.db").read_text() == "keep"
    assert not list(new.glob("swingmusic.db*"))


def test_logs_folder_inside_the_config_folder_is_renamed(tmp_path: Path):
    parent = tmp_path / "config"
    home = tmp_path / "home"
    home.mkdir()
    _touch(parent / "swingmusic" / "swingmusic" / "logs" / "log.jsonl")

    migrate_legacy_names(parent, home)

    assert (parent / "musix" / "musix" / "logs" / "log.jsonl").exists()
    assert not (parent / "musix" / "swingmusic").exists()


def test_existing_new_folder_is_left_alone(tmp_path: Path):
    parent = tmp_path / "config"
    home = tmp_path / "home"
    home.mkdir()
    _touch(parent / "swingmusic" / "swingmusic.db", "old")
    _touch(parent / "musix" / "musix.db", "new")

    migrate_legacy_names(parent, home)

    assert (parent / "swingmusic" / "swingmusic.db").read_text() == "old"
    assert (parent / "musix" / "musix.db").read_text() == "new"
    assert not (parent / "musix" / "swingmusic.db").exists()


def test_existing_musix_db_is_not_overwritten(tmp_path: Path):
    parent = tmp_path / "config"
    home = tmp_path / "home"
    home.mkdir()
    _touch(parent / "swingmusic" / "swingmusic.db", "old")
    _touch(parent / "swingmusic" / "musix.db", "new")

    migrate_legacy_names(parent, home)

    assert (parent / "musix" / "musix.db").read_text() == "new"
    assert (parent / "musix" / "swingmusic.db").read_text() == "old"


def test_backup_folder_in_home_is_renamed(tmp_path: Path):
    parent = tmp_path / "config"
    home = tmp_path / "home"
    _touch(home / "swingmusic.backup" / "b1" / "data.json")

    migrate_legacy_names(parent, home)

    assert (home / "musix.backup" / "b1" / "data.json").exists()
    assert not (home / "swingmusic.backup").exists()


def test_nothing_to_migrate_is_a_noop(tmp_path: Path):
    parent = tmp_path / "config"
    home = tmp_path / "home"
    home.mkdir()

    migrate_legacy_names(parent, home)

    assert not parent.exists()
