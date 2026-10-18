"""
Contains the single-track metadata routes.
"""

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from musix.api.apischemas import TrackHashSchema
from musix.serializers.track import serialize_track
from musix.store.tracks import TrackStore

bp_tag = Tag(name="Track", description="Single track metadata")
# NOTE: blueprint name must differ from the "/file" blueprint, which is also
# named "track" internally.
api = APIBlueprint("trackmeta", __name__, url_prefix="/track", abp_tags=[bp_tag])


class GetTrackQuery(BaseModel):
    filepath: str = Field(
        "",
        description="Optional filepath to select a specific duplicate file "
        "indexed under this trackhash. Must belong to the trackhash.",
    )


@api.get("/<trackhash>")
def get_track_by_hash(path: TrackHashSchema, query: GetTrackQuery):
    """
    Get a single track by its trackhash

    Returns the best (highest-bitrate) track for the trackhash. An optional
    `filepath` selects a specific duplicate file, which must belong to the
    trackhash.
    """
    trackhash = path.trackhash
    filepath = query.filepath

    # 404 if the trackhash is not indexed (None only happens for unknown hash)
    base = TrackStore.get_track(trackhash)
    if base is None:
        return {"error": "Track not found"}, 404

    if filepath:
        # the filepath must belong to this trackhash
        if not TrackStore.is_valid_track_filepath(trackhash, filepath):
            return {"error": "Invalid filepath"}, 400
        track = TrackStore.get_track(trackhash, filepath)
    else:
        track = base

    return serialize_track(track)
