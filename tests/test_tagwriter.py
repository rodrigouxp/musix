import hashlib
import os
from io import BytesIO
from pathlib import Path

import mutagen
import pytest
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TPE1, TPE2, TXXX
from PIL import Image

from musix.lib import tagwriter
from musix.lib.tagwriter import (
    TagChanges,
    TagVerificationError,
    TagWriteError,
    UnsupportedFormat,
    append_artists,
    artist_elements,
    assert_artists_preserved,
    read_tags,
    replace_artist_element,
    write_tags,
)
from musix.utils.hashing import create_hash
from musix.utils.parsers import split_artists


def h(name: str) -> str:
    return create_hash(name, decode=True)


def png(color=(200, 30, 30), size=(64, 64)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


# SECTION: the pure artist functions


@pytest.mark.parametrize(
    "value",
    [
        "Lucinha; The Rolling Stones",
        "A;B;C",
        "A / B ; C",
        "AC/DC",
        "AC/DC; Queen",
        "Queen / AC/DC",
        "Earth, Wind & Fire; Someone",
        "Tyler, The Creator",
        "  spaced ;  names  ",
        ";leading;;double;",
        "Beyoncé; Sigur Rós",
        "",
        "Solo",
    ],
)
def test_elements_are_the_artists_the_app_sees(value, config):
    spans = artist_elements(value, config)

    assert [value[a:b] for a, b in spans] == split_artists(value, config)


def test_lucinha_case(config):
    result = replace_artist_element(
        ["Lucinha; The Rolling Stones"], h("The Rolling Stones"), "Rolling Stones", config
    )

    assert result == ["Lucinha; Rolling Stones"]


@pytest.mark.parametrize(
    "tag,expected",
    [
        (["X; A; B"], ["Y; A; B"]),  # at the start
        (["A; X; B"], ["A; Y; B"]),  # in the middle
        (["A; B; X"], ["A; B; Y"]),  # at the end
        (["X"], ["Y"]),  # alone
        (["A / X ;B"], ["A / Y ;B"]),  # separators and spaces stay
        (["A/X/B"], ["A/Y/B"]),
        ([" X ; A"], [" Y ; A"]),
        (["A", "X", "B"], ["A", "Y", "B"]),  # several values (Vorbis)
        (["A; X", "B"], ["A; Y", "B"]),
        (["A; B"], ["A; B"]),  # nothing to swap
    ],
)
def test_replace_element_in_each_position(tag, expected, config):
    assert replace_artist_element(tag, h("X"), "Y", config) == expected


def test_partial_names_do_not_match(config):
    tag = ["Rolling Stones; The Stones; Stones Roses"]

    assert replace_artist_element(tag, h("Stones"), "Pebbles", config) == tag


def test_all_spellings_of_the_old_artist_are_replaced(config):
    result = replace_artist_element(["Juice WRLD; A; juice wrld"], h("Juice WRLD"), "JW", config)

    # one artist can not be there twice
    assert result == ["JW; A"]


def test_new_name_already_in_the_tag_collapses_to_one(config):
    assert replace_artist_element(
        ["Lucinha; Rolling Stones"], h("Lucinha"), "Rolling Stones", config
    ) == ["Rolling Stones"]
    assert replace_artist_element(["A; Stones; B; X"], h("X"), "Stones", config) == ["A; Stones; B"]
    assert replace_artist_element(["Y; A; X"], h("X"), "Y", config) == ["Y; A"]
    assert replace_artist_element(["A", "X", "Y"], h("X"), "Y", config) == ["A", "Y"]
    assert replace_artist_element(["X", "Y"], h("X"), "Y", config) == ["Y"]


def test_case_only_rename(config):
    assert replace_artist_element(["juice wrld; A"], h("Juice WRLD"), "Juice WRLD", config) == [
        "Juice WRLD; A"
    ]


def test_elements_in_the_ignore_list_survive(config):
    result = replace_artist_element(["AC/DC; X; Queen"], h("X"), "Y", config)

    assert result == ["AC/DC; Y; Queen"]


def test_append_artists_keeps_representation(config):
    assert append_artists(["Lucinha"], ["Mick", "Keith"], config) == ["Lucinha; Mick; Keith"]
    assert append_artists(["Lucinha", "Bob"], ["Mick"], config) == ["Lucinha", "Bob", "Mick"]
    assert append_artists(["Lucinha; Mick"], ["mick"], config) == ["Lucinha; Mick"]


def test_check_passes_for_a_good_rename(config):
    assert_artists_preserved(
        ["Lucinha; The Rolling Stones"],
        ["Lucinha; Rolling Stones"],
        h("The Rolling Stones"),
        "Rolling Stones",
        config,
    )
    assert_artists_preserved(None, None, h("X"), "Y", config)
    assert_artists_preserved(["A; B"], ["A; B"], h("X"), "Y", config)
    assert_artists_preserved(["A; X; Y"], ["A; Y"], h("X"), "Y", config)


@pytest.mark.parametrize(
    "before,after",
    [
        (["A; X; B"], ["A; Y"]),  # B was lost
        (["A; X; B"], ["B; Y; A"]),  # moved
        (["A; X; B"], ["A; Y; b"]),  # text changed
        (["A; X; B"], ["A; Y; B; C"]),  # something added
        (["A; X; B"], ["A; X; B"]),  # not renamed
        (["A; X; B"], ["A; B; Y"]),  # the new name moved
        (["A; B"], ["A; B; Y"]),  # added an artist that was not there
        (["A; X"], None),
        (None, ["A"]),
        (["A; X"], ["A; Y; Y"]),
    ],
)
def test_check_fails_when_someone_is_lost_moved_or_changed(before, after, config):
    with pytest.raises(TagVerificationError):
        assert_artists_preserved(before, after, h("X"), "Y", config)


# SECTION: writing files


def dir_files(path: Path) -> list[str]:
    return sorted(p.name for p in path.parent.iterdir())


@pytest.fixture(params=["mp3", "flac", "m4a", "ogg", "opus"])
def audio(request, make_audio):
    return request.param, make_audio(
        request.param,
        title="Old title",
        artist="Lucinha; The Rolling Stones",
        album_artist="Lucinha",
        album="An Album",
        genre="Rock",
        comment="keep me",
    )


def test_writes_the_title_and_nothing_else(audio, config):
    fmt, path = audio
    before = read_tags(path)

    after = write_tags(path, TagChanges(title="New: title?"), config=config)

    assert after.title == "New: title?"
    assert after.artist == before.artist
    assert after.albumartist == before.albumartist
    assert after.others == before.others
    assert dir_files(path) == [path.name]

    # the reader of the app agrees
    from tinytag import TinyTag

    tags = TinyTag.get(path)
    assert tags.title == "New: title?"
    assert tags.album == "An Album"
    assert tags.genre == "Rock"


def test_writes_artist_tags_by_element(audio, config):
    fmt, path = audio
    before = read_tags(path)
    old = h("The Rolling Stones")

    changes = TagChanges(
        artist=replace_artist_element(before.artist, old, "Rolling Stones", config),
        albumartist=replace_artist_element(before.albumartist, old, "Rolling Stones", config),
    )
    after = write_tags(path, changes, swap=(old, "Rolling Stones"), config=config)

    assert after.artist == ["Lucinha; Rolling Stones"]
    assert after.albumartist == ["Lucinha"]
    assert after.others == before.others


def test_does_not_create_artist_tags_the_file_did_not_have(make_audio, config):
    path = make_audio("flac", title="T", artist="Lucinha; The Rolling Stones", album="A")
    assert read_tags(path).albumartist is None

    after = write_tags(
        path, TagChanges(albumartist=["Rolling Stones"], artists=["x"]), config=config
    )

    assert after.albumartist is None
    assert after.artists is None
    assert "albumartist" not in {k.lower() for k in mutagen.File(path).tags.keys()}


def test_creates_an_artist_tag_only_when_asked(make_audio, config):
    path = make_audio("flac", title="T", artist="Lucinha", album="A")

    after = write_tags(
        path,
        TagChanges(albumartist=["Lucinha"]),
        create_missing=["albumartist"],
        config=config,
    )

    assert after.albumartist == ["Lucinha"]


def test_artists_tag_is_updated_when_it_exists(make_audio, config):
    path = make_audio("flac", title="T", artist="Lucinha; The Rolling Stones", album="A")
    audio = FLAC(path)
    audio["artists"] = ["Lucinha", "The Rolling Stones"]
    audio.save()
    before = read_tags(path)
    old = h("The Rolling Stones")

    changes = TagChanges(
        artist=replace_artist_element(before.artist, old, "Rolling Stones", config),
        artists=replace_artist_element(before.artists, old, "Rolling Stones", config),
    )
    after = write_tags(path, changes, swap=(old, "Rolling Stones"), config=config)

    assert after.artists == ["Lucinha", "Rolling Stones"]
    assert after.artist == ["Lucinha; Rolling Stones"]


def test_vorbis_multi_values_stay_multi_values(make_audio, config):
    path = make_audio("flac", title="T", album="A")
    audio = FLAC(path)
    audio["artist"] = ["Lucinha", "The Rolling Stones", "Bob"]
    audio["albumartist"] = ["Lucinha"]
    audio.save()
    before = read_tags(path)
    old = h("The Rolling Stones")

    changes = TagChanges(artist=replace_artist_element(before.artist, old, "Rolling Stones", config))
    after = write_tags(path, changes, swap=(old, "Rolling Stones"), config=config)

    assert after.artist == ["Lucinha", "Rolling Stones", "Bob"]
    assert FLAC(path)["artist"] == ["Lucinha", "Rolling Stones", "Bob"]


def test_id3_multi_values_and_single_strings(make_audio, config):
    multi = make_audio("mp3", title="T", album="A")
    tags = ID3(multi)
    tags.add(TPE1(encoding=3, text=["Lucinha", "The Rolling Stones"]))
    tags.add(TPE2(encoding=3, text=["Lucinha"]))
    tags.save(v2_version=4)
    single = make_audio(
        "mp3", title="T", artist="Bob; The Rolling Stones", album="A", album_artist="Bob"
    )
    old = h("The Rolling Stones")

    for path, expected in ((multi, ["Lucinha", "Rolling Stones"]), (single, ["Bob; Rolling Stones"])):
        before = read_tags(path)
        changes = TagChanges(
            artist=replace_artist_element(before.artist, old, "Rolling Stones", config),
            albumartist=replace_artist_element(before.albumartist, old, "Rolling Stones", config),
        )
        after = write_tags(path, changes, swap=(old, "Rolling Stones"), config=config)
        assert after.artist == expected
        assert after.albumartist == before.albumartist


def test_an_id3v23_tag_stays_v23(make_audio, config):
    path = make_audio("mp3", title="T", artist="A", album="B")
    tags = ID3(path)
    tags.save(v2_version=3)
    assert ID3(path).version[:2] == (2, 3)

    write_tags(path, TagChanges(title="New"), config=config)

    assert ID3(path).version[:2] == (2, 3)
    assert read_tags(path).title == "New"


def test_id3_keeps_unrelated_frames(make_audio, config):
    path = make_audio("mp3", title="T", artist="A", album="B")
    tags = ID3(path)
    tags.add(TXXX(encoding=3, desc="MOOD", text=["calm"]))
    tags.save()
    before = read_tags(path)

    write_tags(path, TagChanges(title="New"), config=config)

    assert ID3(path)["TXXX:MOOD"].text == ["calm"]
    assert read_tags(path).others == before.others


@pytest.mark.parametrize("fmt", ["mp3", "flac", "m4a", "ogg", "opus"])
def test_embeds_the_front_cover(make_audio, config, fmt):
    path = make_audio(fmt, title="T", artist="A", album="B", comment="keep")
    before = read_tags(path)
    image = png((10, 200, 10))

    after = write_tags(path, TagChanges(cover=(image, "image/png")), config=config)

    assert after.covers == [hashlib.md5(image).hexdigest()]
    assert after.others == before.others
    assert after.title == "T"

    # the reader of the app finds it too
    from tinytag import TinyTag

    assert TinyTag.get(path, image=True).images.any.data == image

    # a second cover replaces the first one
    second = png((200, 10, 10))
    after = write_tags(path, TagChanges(cover=(second, "image/png")), config=config)
    assert after.covers == [hashlib.md5(second).hexdigest()]


def test_unsupported_formats_are_refused_and_untouched(tmp_path, config):
    wav = tmp_path / "song.wav"
    wav.write_bytes(b"RIFF....WAVEfmt ")
    wma = tmp_path / "song.wma"
    wma.write_bytes(b"not really wma")

    for path in (wav, wma):
        before = path.read_bytes()

        with pytest.raises(UnsupportedFormat, match="unsupported format"):
            write_tags(path, TagChanges(title="x"), config=config)

        assert path.read_bytes() == before

    assert sorted(p.name for p in tmp_path.iterdir()) == ["song.wav", "song.wma"]


def test_missing_file_is_refused(tmp_path, config):
    with pytest.raises(TagWriteError):
        write_tags(tmp_path / "nope.mp3", TagChanges(title="x"), config=config)


def test_a_failure_in_the_middle_leaves_the_original_and_no_temp_file(
    make_audio, config, monkeypatch
):
    path = make_audio("flac", title="Old", artist="A", album="B")
    original = path.read_bytes()
    mtime = path.stat().st_mtime_ns

    def boom(self):
        raise OSError("disk full")

    monkeypatch.setattr(tagwriter._VorbisAdapter, "save", boom)

    with pytest.raises(TagWriteError, match="disk full"):
        write_tags(path, TagChanges(title="New"), config=config)

    assert path.read_bytes() == original
    assert path.stat().st_mtime_ns == mtime
    assert dir_files(path) == [path.name]


def test_a_copy_that_does_not_read_back_is_not_used(make_audio, config, monkeypatch):
    path = make_audio("flac", title="Old", artist="A", album="B")
    original = path.read_bytes()

    real_apply = tagwriter._apply

    def sloppy(adapter, before, changes, create_missing):
        expected = real_apply(adapter, before, changes, create_missing)
        # something else changes in the copy
        adapter.tags["comment"] = ["changed behind our back"]
        return expected

    monkeypatch.setattr(tagwriter, "_apply", sloppy)

    with pytest.raises(TagVerificationError, match="other tags changed"):
        write_tags(path, TagChanges(title="New"), config=config)

    assert path.read_bytes() == original
    assert dir_files(path) == [path.name]


def test_the_artist_check_rejects_a_bad_swap_and_keeps_the_original(make_audio, config):
    path = make_audio("flac", title="T", artist="Lucinha; The Rolling Stones; Bob", album="B")
    original = path.read_bytes()

    # asks for a swap that drops Bob
    with pytest.raises(TagVerificationError):
        write_tags(
            path,
            TagChanges(artist=["Lucinha; Rolling Stones"]),
            swap=(h("The Rolling Stones"), "Rolling Stones"),
            config=config,
        )

    assert path.read_bytes() == original
    assert dir_files(path) == [path.name]


def test_a_failed_replace_leaves_the_original(make_audio, config, monkeypatch):
    path = make_audio("mp3", title="Old", artist="A", album="B")
    original = path.read_bytes()

    def no_replace(src, dst):
        raise PermissionError("file in use")

    monkeypatch.setattr(os, "replace", no_replace)

    with pytest.raises(TagWriteError, match="file in use"):
        write_tags(path, TagChanges(title="New"), config=config)

    assert path.read_bytes() == original
    assert dir_files(path) == [path.name]


def test_the_original_is_never_opened_for_writing(make_audio, config, monkeypatch):
    path = make_audio("flac", title="Old", artist="A", album="B")
    opened_for_write = []
    real_open = open

    def watching_open(file, mode="r", *args, **kwargs):
        if Path(str(file)) == path and any(c in mode for c in "wa+x"):
            opened_for_write.append(mode)

        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", watching_open)
    write_tags(path, TagChanges(title="New"), config=config)

    assert opened_for_write == []
    assert read_tags(path).title == "New"


def test_the_permissions_are_kept(make_audio, config):
    path = make_audio("flac", title="Old", artist="A", album="B")
    os.chmod(path, 0o640)
    mode = path.stat().st_mode & 0o777

    write_tags(path, TagChanges(title="New"), config=config)

    # Windows only has read-only or not: what matters is that it is the same as before
    assert path.stat().st_mode & 0o777 == mode
