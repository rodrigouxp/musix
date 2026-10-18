from typing import Any

from swingmusic.db.userdata import CollectionTable
from swingmusic.lib.pagelib import recover_page_items
from swingmusic.store.homepageentries import (
    GenericRecoverableEntry,
    HomepageEntry,
    RecentlyAddedHomepageEntry,
    RecentlyPlayedHomepageEntry,
)
from swingmusic.utils.auth import get_current_userid


class HomepageStore:
    """
    Stores the homepage items.
    """

    # INFO: map of entry names to entry objects
    entries: dict[str, HomepageEntry] = {
        "recently_played": RecentlyPlayedHomepageEntry(
            title="Recently played",
        ),
        "top_streamed_weekly_artists": GenericRecoverableEntry(
            title="Top artists this week",
            description="Your most played artists since Monday",
        ),
        "top_streamed_monthly_artists": GenericRecoverableEntry(
            title="Top artists this month",
            description="Your most played artists since the start of the month",
        ),
        "recently_added": RecentlyAddedHomepageEntry(
            title="Recently added",
            description="New music added to your library",
        ),
    }

    @classmethod
    def get_homepage_items(cls, limit: int):
        # return a dict of entry name to entry items
        pages = CollectionTable.get_all()
        pagedata = []

        for page in pages:
            pagedata.append(
                {
                    page["id"]: {
                        "id": page["id"],
                        "title": page["name"],
                        "description": page["extra"]["description"],
                        "items": recover_page_items(page["items"], for_homepage=True),
                        "url": f"collections/{page['id']}",
                    }
                }
            )

        homedata = [
            {entry: cls.entries[entry].get_items(get_current_userid(), limit)}
            for entry in cls.entries.keys()
            if len(cls.entries[entry].items)
        ]

        recently_added = homedata.pop()
        return homedata + pagedata + [recently_added]
