"""
Album types that were set by hand.

An album is only ever an "ep", a "soundtrack" or a "live album" when the user
marks it so. The marks live in the ``album_type_override`` table and are kept
here in memory, so ``Album.check_type`` never has to touch the database.

This module must not import models or database code: ``models.album`` imports
it.
"""

from typing import Iterable

ALBUM_KINDS = ("ep", "soundtrack", "live album")


class AlbumTypeStore:
    overrides: dict[str, str] = {}

    @classmethod
    def load(cls, rows: Iterable[tuple[str, str]]):
        """
        Replaces everything in memory with the given ``(albumhash, kind)`` rows.
        """
        cls.overrides = {
            albumhash: kind for albumhash, kind in rows if kind in ALBUM_KINDS
        }

    @classmethod
    def get(cls, albumhash: str) -> str | None:
        return cls.overrides.get(albumhash)

    @classmethod
    def set(cls, albumhash: str, kind: str | None):
        """
        Marks an album with ``kind``, replacing any earlier mark.
        ``None`` removes the mark.
        """
        if kind is None:
            cls.overrides.pop(albumhash, None)
        else:
            cls.overrides[albumhash] = kind
