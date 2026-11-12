"""
What counts as a play.

A track counts as played when it was listened for 30 seconds or for half of its
length, whichever is shorter. Shorter listens (a track that was skipped) do not
count: before this rule any listen of 5 seconds counted, so the tracks that were
skipped the most climbed the "most played" lists.
"""

PLAY_SECONDS = 30


def play_threshold(track_duration: int | float | None) -> float:
    """
    The seconds a track has to be listened for to count as a play.
    """
    if not track_duration or track_duration <= 0:
        return PLAY_SECONDS

    return min(PLAY_SECONDS, track_duration / 2)


def counts_as_play(listened: int | float, track_duration: int | float | None) -> bool:
    return listened >= play_threshold(track_duration)


def plays_text(playcount: int) -> str:
    """
    "unplayed", "1 play", "12 plays": the text next to a track in the lists of an artist.
    """
    if playcount == 0:
        return "unplayed"

    return f"{playcount} play{'' if playcount == 1 else 's'}"


def most_played_first(tracks: list):
    """
    Sorts tracks for a "most played" list: by plays, then by the time listened,
    then by title (A to Z), so tracks with the same number of plays keep a stable
    and readable order.
    """
    return sorted(
        tracks,
        key=lambda t: (-t.playcount, -t.playduration, t.title.casefold()),
    )
