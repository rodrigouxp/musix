import dataclasses
from dataclasses import dataclass

from musix.models.track import Track
from musix.store.albumtypes import AlbumTypeStore
from musix.utils.hashing import create_hash
from musix.utils.auth import get_current_userid
from musix.utils.parsers import get_base_title_and_versions, normalize_search_text


@dataclass(slots=True)
class Album:
    """
    Creates an album object
    """

    albumartists: list[dict[str, str]]
    albumhash: str
    artisthashes: list[str]
    base_title: str
    color: str
    blurhash: str
    created_date: int
    date: int
    duration: int
    genres: list[dict[str, str]]
    genrehashes: list[str]
    og_title: str
    title: str
    trackcount: int
    lastplayed: int
    playcount: int
    playduration: int
    extra: dict
    pathhash: str = ""

    id: int = -1
    type: str = "album"
    image: str = ""
    _score: float = 0
    _search_title: str = ""
    _search_texts: list[str] = dataclasses.field(default_factory=list)
    versions: list[str] = dataclasses.field(default_factory=list)
    fav_userids: list[int] = dataclasses.field(default_factory=list)
    weakhash: str = ""

    @property
    def is_favorite(self):
        return get_current_userid() in self.fav_userids

    def toggle_favorite_user(self, userid: int):
        """
        Adds or removes the given user from the list of users
        who have favorited the album.
        """
        if userid in self.fav_userids:
            self.fav_userids.remove(userid)
        else:
            self.fav_userids.append(userid)

    def __post_init__(self):
        self.image = self.albumhash + ".webp" + "?pathhash=" + self.pathhash
        self.populate_versions()
        self.weakhash = create_hash(
            self.og_title, ",".join(a["name"] for a in self.albumartists)
        )
        self._search_title = normalize_search_text(self.title)
        self._search_texts = [
            normalize_search_text(a["name"] + " " + self.title)
            for a in self.albumartists
        ]

    def populate_versions(self):
        _, self.versions = get_base_title_and_versions(self.og_title, get_versions=True)

        if "super_deluxe" in self.versions:
            self.versions.remove("deluxe")

        # at this point, we should know the type of album
        if "original" in self.versions and self.type == "soundtrack":
            self.versions.remove("original")

        self.versions = [v.replace("_", " ") for v in self.versions]

    def check_type(self, tracks: list[Track] | None = None):
        """
        Works out the type of the album.

        Only two things set a type: a mark the user put on the album by hand
        (see ``AlbumTypeStore``) and the compilation check. Nothing is
        guessed from the title or from the number of tracks.
        """
        kind = AlbumTypeStore.get(self.albumhash)

        if kind:
            self.type = kind
            return

        if self.is_compilation():
            self.type = "compilation"
            return

        self.type = "album"

    def is_compilation(self) -> bool:
        """
        Checks if the album is a compilation.
        """
        artists = [a["name"] for a in self.albumartists]
        artists = "".join(artists).lower()

        if "various artists" in artists:
            return True

        substrings = {
            "the essential",
            "best of",
            "greatest hits",
            "#1 hits",
            "number ones",
            "super hits",
            "collection",
            "anthology",
            "great hits",
            "biggest hits",
            "the hits",
            "the ultimate",
            "compilation",
        }

        for substring in substrings:
            if substring in self.title.lower():
                return True

        return False
