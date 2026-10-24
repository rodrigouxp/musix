from musix.lib import lyrics as lyrics_lib
from musix.lib.lyrics import Lyrics, get_lyrics_file, parse_lyrics_lines, parse_time_tag

SYNCED = """[ti:Song]
[ar:Queen]
[offset:+250]
[00:12.34]Is this the real life?
[00:15.00]Is this just fantasy?
[01:02.5]Caught in a landslide
[00:20.00][01:20.00]Chorus twice
[00:30.00]
[00:31.00]  spaced text
"""


def texts(lyrics: Lyrics) -> list[str]:
    return lyrics.format_unsynced_lyrics()


def test_a_normal_synced_lrc_reads_as_before():
    # the offset is 250 ms; the part after the dot is a fraction of the second (.34 is 340 ms, .5 is
    # 500 ms): the reader used to take it as milliseconds (34 and 5)
    lyrics = Lyrics(SYNCED)

    assert lyrics.is_synced
    assert lyrics.meta == {"title": "Song", "artist": "Queen", "offset": "+250"}
    assert lyrics.format_synced_lyrics() == [
        {"time": 12090.0, "text": "Is this the real life?"},
        {"time": 14750.0, "text": "Is this just fantasy?"},
        {"time": 62250.0, "text": "Caught in a landslide"},
        {"time": 19750.0, "text": "Chorus twice"},
        {"time": 79750.0, "text": "Chorus twice"},
        {"time": 29750.0, "text": ""},
        {"time": 30750.0, "text": "  spaced text"},
    ]


def test_a_plain_lyrics_is_not_synced():
    lyrics = Lyrics("Is this the real life?\nIs this just fantasy?\n\nCaught in a landslide")

    assert not lyrics.is_synced
    assert texts(lyrics) == ["Is this the real life?", "Is this just fantasy?", "", "Caught in a landslide"]


def test_section_lines_of_a_plain_lyrics_are_text_and_do_not_raise():
    lyrics = Lyrics("[Verse 1]\nla la\n[Chorus]\nlo lo\n[Verse 2: Freddie]\nli li")

    assert not lyrics.is_synced
    assert texts(lyrics) == ["[Verse 1]", "la la", "[Chorus]", "lo lo", "[Verse 2: Freddie]", "li li"]
    assert lyrics.meta == {}


def test_the_fraction_of_a_second_is_a_decimal():
    lyrics = Lyrics("[00:03.5]a\n[00:03.50]b\n[00:03.05]c\n[00:03.123]d\n[00:03]e")

    assert [line["time"] for line in lyrics.format_synced_lyrics()] == [3500.0, 3500.0, 3050.0, 3123.0, 3000.0]


def test_the_offset_of_one_lyrics_does_not_move_the_next_one():
    first = Lyrics("[offset:+500]\n[00:01.00]a")
    second = Lyrics("[00:01.00]b")

    assert first.format_synced_lyrics() == [{"time": 500.0, "text": "a"}]
    assert second.meta == {}
    assert second.format_synced_lyrics() == [{"time": 1000.0, "text": "b"}]


def test_the_meta_of_one_lyrics_does_not_leak():
    Lyrics("[ar:Queen]\n[00:01.00]a")

    assert Lyrics("Just text").meta == {}
    assert Lyrics().meta == {}


def test_an_offset_that_is_not_a_number_is_zero():
    lyrics = Lyrics("[offset:abc]\n[00:01.00]a")

    assert lyrics.format_synced_lyrics() == [{"time": 1000.0, "text": "a"}]


def test_odd_lines_do_not_break_the_parser():
    lines = parse_lyrics_lines("[Chorus]\n[ ]\n[]\n\n[00:12.34]\n[unclosed\ntext ] only")

    assert len(lines) == 7
    # [00:12.34] with no text is a time tag with an empty body
    assert parse_time_tag(lines) == [{"minute": "00", "seconds": "12.34", "body": ""}]


def test_a_synced_line_keeps_the_brackets_inside_its_text():
    lyrics = Lyrics("[00:05.00]Oh [ooh] yeah")

    assert lyrics.format_synced_lyrics() == [{"time": 5000.0, "text": "Oh [ooh] yeah"}]


def test_a_lyrics_with_a_bom():
    lyrics = Lyrics("﻿[00:01.00]a\n[00:02.00]b")

    assert lyrics.is_synced
    assert [line["text"] for line in lyrics.format_synced_lyrics()] == ["a", "b"]


def test_a_lrc_file_with_a_bom_is_read(tmp_path):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"x")
    (tmp_path / "song.lrc").write_bytes("﻿[00:01.00]a\n".encode("utf-8"))

    lyrics = get_lyrics_file(audio)

    assert lyrics.is_synced
    assert lyrics.format_synced_lyrics() == [{"time": 1000.0, "text": "a"}]


def test_the_meta_names_are_one_list():
    assert Lyrics.SUPPORTED_METATAGS is lyrics_lib.SUPPORTED_METATAGS
