from flask_openapi3 import Tag
from flask_openapi3 import APIBlueprint
from pydantic import Field
from musix.api.apischemas import TrackHashSchema
from musix.api.auth import admin_required
from musix.lib import lyricsbatch
from musix.lib.lyrics import Lyrics as Lyrics_class
from musix.lib.lyricsfinder import LyricsQuery, find_and_save, lyrics_plugin_on
from musix.settings import Defaults

bp_tag = Tag(name="Lyrics Plugin", description="Online lyrics finder (LRCLIB and Musixmatch)")
api = APIBlueprint(
    "lyricsplugin", __name__, url_prefix="/plugins/lyrics", abp_tags=[bp_tag]
)


class LyricsSearchBody(TrackHashSchema):
    title: str = Field(description="The track title ", example=Defaults.API_TRACKNAME)
    artist: str = Field(
        description="The track artist ", example=Defaults.API_ARTISTNAME
    )
    album: str = Field(
        description="The track track album ", example=Defaults.API_ALBUMNAME
    )
    filepath: str = Field(
        description="Track filepath to save the lyrics file relative to",
        example="/home/cwilvx/temp/crazy song.mp3",
    )
    duration: int | None = Field(
        None,
        description="The duration of the track in seconds (the lyrics of another version are left out)",
    )
    auto: bool = Field(
        False,
        description="The search was started by the app, not by the user: a song that had no lyrics "
        "online recently is not looked up again",
    )
    replace_unsynced: bool = Field(
        False,
        description="A .lrc with plain lyrics may be replaced by synced ones",
    )


@api.post("/search")
def search_lyrics(body: LyricsSearchBody):
    """
    Search for lyrics online

    Looks the lyrics up on LRCLIB (then Musixmatch) and saves them as the .lrc of the song. Always answers
    200: `lyrics` is the synced list when the lyrics found are synced (plain ones are saved too: the
    client loads them again with `POST /lyrics`), and `reason` says why there is nothing:
    plugin_off, not_found, instrumental, network or write_failed.
    """
    answer = {
        "trackhash": body.trackhash,
        "lyrics": None,
        "synced": False,
        "source": None,
        "reason": None,
    }

    if not lyrics_plugin_on():
        answer["reason"] = "plugin_off"
        return answer, 200

    query = LyricsQuery(
        trackhash=body.trackhash,
        title=body.title,
        artist=body.artist,
        album=body.album,
        duration=body.duration or 0,
        filepath=body.filepath,
    )
    result = find_and_save(
        query, use_cache=body.auto, replace_unsynced=body.replace_unsynced
    )

    answer["reason"] = result.reason
    answer["source"] = result.source

    if result.reason == "write_failed":
        answer["path"] = result.detail

    if result.text:
        lyrics = Lyrics_class(result.text)

        if lyrics.is_synced:
            answer["lyrics"] = lyrics.format_synced_lyrics()
            answer["synced"] = True

    return answer, 200


@api.get("/missing/count")
@admin_required()
def count_missing_lyrics():
    """
    How many songs have no lyrics

    A song has lyrics with a .lrc with text, lyrics in its tags or the .lrc of a duplicate. The songs
    that had no lyrics online recently are not counted (they are not looked up again for a while).
    """
    missing, total = lyricsbatch.missing_tracks()

    return {"missing": len(missing), "total": total, "plugin_on": lyrics_plugin_on()}


@api.post("/missing/start")
@admin_required()
def start_missing_lyrics():
    """
    Find missing lyrics

    Starts the job that looks up, in the background, the lyrics of the songs that have none, and
    saves them as .lrc files next to the songs. 409 when it is running already, 400 with the plugin off.
    """
    if lyricsbatch.batch.status()["running"]:
        return {"reason": "already_running"}, 409

    if not lyrics_plugin_on():
        return {"reason": "plugin_off"}, 400

    if not lyricsbatch.batch.start():
        return {"reason": "already_running"}, 409

    return lyricsbatch.batch.status(), 200


@api.get("/missing/status")
@admin_required()
def missing_lyrics_status():
    """
    The progress of the job that looks up the missing lyrics
    """
    return lyricsbatch.batch.status()


@api.post("/missing/cancel")
@admin_required()
def cancel_missing_lyrics():
    """
    Stops the job after the song in progress
    """
    lyricsbatch.batch.cancel()

    return lyricsbatch.batch.status()
