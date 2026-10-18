"""
Moves data created under the old Swing Music names to the MUSIX names.

Runs before the config folder is created and before the database is
opened. Nothing is ever deleted: folders and files are only renamed, and
when the new name is already taken nothing is touched.
"""

import logging
from pathlib import Path

log = logging.getLogger(__name__)

OLD_NAME = "swingmusic"
NEW_NAME = "musix"

DB_SUFFIXES = ("", "-wal", "-shm")


def _config_folder(config_parent: Path, home: Path, name: str) -> Path:
    prefix = "." if config_parent == home else ""
    return config_parent / f"{prefix}{name}"


def _rename(old: Path, new: Path) -> bool:
    """
    Renames `old` to `new` unless `new` exists. Returns True if renamed.
    """
    if not old.exists():
        return False

    if new.exists():
        log.warning("Not migrating %s: %s already exists", old, new)
        return False

    old.rename(new)
    log.info("Migrated %s -> %s", old, new)
    return True


def migrate_config_dir(config_parent: Path, home: Path) -> None:
    """
    Renames the old config folder (`swingmusic` or `.swingmusic`) inside
    `config_parent` to the new one, then renames the database (and its
    -wal / -shm files) and the logs folder inside it.

    Does nothing if the new config folder already exists.
    """
    old_dir = _config_folder(config_parent, home, OLD_NAME)
    new_dir = _config_folder(config_parent, home, NEW_NAME)

    if not old_dir.exists():
        return

    if new_dir.exists():
        log.warning(
            "Both %s and %s exist. Using %s and leaving the old folder untouched.",
            old_dir,
            new_dir,
            new_dir,
        )
        return

    old_dir.rename(new_dir)
    log.info("Migrated %s -> %s", old_dir, new_dir)

    for suffix in DB_SUFFIXES:
        old_db = new_dir / f"{OLD_NAME}.db{suffix}"
        new_db = new_dir / f"{NEW_NAME}.db{suffix}"

        if not new_db.exists():
            _rename(old_db, new_db)

    # the logs live in <config folder>/<app name>/logs
    _rename(new_dir / OLD_NAME, new_dir / NEW_NAME)


def migrate_backup_dir(home: Path) -> None:
    """
    Renames ~/swingmusic.backup to ~/musix.backup.
    """
    _rename(home / f"{OLD_NAME}.backup", home / f"{NEW_NAME}.backup")


def migrate_legacy_names(config_parent: Path, home: Path) -> None:
    """
    Entry point. Never raises: a failed rename is logged and the app
    starts with a fresh MUSIX folder instead of refusing to boot.
    """
    try:
        migrate_config_dir(config_parent, home)
        migrate_backup_dir(home)
    except OSError as e:
        log.error("Could not migrate the data from the old Swing Music names: %s", e)
