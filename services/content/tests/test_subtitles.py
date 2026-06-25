# subtitles 모듈(오프셋·SRT 직렬화) 검증.
from popory_content.subtitles import scene_offsets, to_srt


def test_scene_offsets_subtracts_transition_overlap():
    # 장면 길이 [10,8,6], 전이 0.4 → 누적에서 전이마다 0.4 차감.
    assert scene_offsets([10.0, 8.0, 6.0], 0.4) == [0.0, 9.6, 17.2]


def test_scene_offsets_single_scene():
    assert scene_offsets([12.5], 0.4) == [0.0]


def test_to_srt_formats_timecodes_and_numbers():
    srt = to_srt([(0.0, 1.5, "안녕"), (1.5, 3.25, "반가워")])
    assert srt == (
        "1\n00:00:00,000 --> 00:00:01,500\n안녕\n\n"
        "2\n00:00:01,500 --> 00:00:03,250\n반가워\n\n"
    )


def test_to_srt_skips_empty_text_and_renumbers():
    srt = to_srt([(0.0, 1.0, "  "), (1.0, 2.0, "본문")])
    assert srt.startswith("1\n00:00:01,000 --> 00:00:02,000\n본문\n")
