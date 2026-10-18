from abc import ABC
from typing import Any

from swingmusic.lib.home.recover_items import recover_items


class HomepageEntry(ABC):
    """
    Base class for all homepage entries.

    items is a dict of userid to a dict of stuff.
    """

    title: str
    description: str
    items: dict[int, Any]

    def __init__(self, title: str, description: str):
        self.title = title
        self.description = description

    def get_items(self, userid: int, limit: int | None = None):
        """
        Return usable items for the homepage.
        """
        ...


class RecentlyPlayedHomepageEntry(HomepageEntry):
    """
    A homepage entry for recently played.
    """

    items: dict[int, list[dict[str, Any]]]

    def __init__(self, title: str, description: str = ""):
        super().__init__(title, description)
        self.items = {}

    def add_new_user(self, userid: int):
        """
        Add a new user to the homepage entry.
        """
        self.items[userid] = []

    def get_items(self, userid: int, limit: int | None = None):
        items = self.items.get(userid, [])[:limit]

        return {
            "title": self.title,
            "description": self.description,
            "items": recover_items(items),
        }


class RecentlyAddedHomepageEntry(RecentlyPlayedHomepageEntry):
    """
    A homepage entry for recently added.
    """

    def get_items(self, userid: int, limit: int | None = None):
        return super().get_items(0, limit)


class GenericRecoverableEntry(RecentlyPlayedHomepageEntry):
    """
    A homepage entry for top streamed.
    """

    # NOTE: This extends RecentlyPlayedHomepageEntry because
    # the shape of the data is the same.
    pass

