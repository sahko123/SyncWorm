import json
import subprocess

import pytest

from audio_fixtures import broadband_signal, write_wav
from syncworm.bake import BakeError, bake, choose_default_source, mirrored_output_path
from syncworm.models import BakeSource

SAMPLE_RATE = 16000


def _ffprobe_audio_streams(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_entries", "stream=codec_type:stream_tags=title,name:stream_disposition=default",
            "-select_streams", "a",
            str(path),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["streams"]


def _title(stream):
    # ffmpeg's "title" metadata key is stored as the "name" tag in MP4 containers.
    tags = stream.get("tags", {})
    return tags.get("title") or tags.get("name")


def test_mirrored_output_path_preserves_subfolder_structure(tmp_path):
    video_input_dir = tmp_path / "videos"
    output_dir = tmp_path / "output"
    video_path = video_input_dir / "DayOne" / "CamA" / "clip001.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.touch()

    result = mirrored_output_path(video_path, video_input_dir, output_dir, "{stem}_synced{suffix}")

    assert result == output_dir / "DayOne" / "CamA" / "clip001_synced.mp4"


def test_mirrored_output_path_rejects_collision_with_input(tmp_path):
    video_input_dir = tmp_path / "videos"
    video_path = video_input_dir / "clip001.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.touch()

    with pytest.raises(BakeError):
        mirrored_output_path(video_path, video_input_dir, video_input_dir, "{stem}{suffix}")


def test_choose_default_source_uses_priority_list():
    sources = [
        BakeSource(name="boom", filepath="boom.wav", confidence_score=0.5),
        BakeSource(name="lav1", filepath="lav1.wav", confidence_score=0.9),
    ]
    chosen = choose_default_source(sources, ["lav1", "boom"])
    assert chosen.name == "lav1"


def test_choose_default_source_falls_back_when_preferred_missing():
    sources = [
        BakeSource(name="boom", filepath="boom.wav", confidence_score=0.5),
    ]
    chosen = choose_default_source(sources, ["lav1", "boom"])
    assert chosen.name == "boom"


def test_choose_default_source_uses_highest_confidence_without_priority():
    sources = [
        BakeSource(name="boom", filepath="boom.wav", confidence_score=0.5),
        BakeSource(name="lav1", filepath="lav1.wav", confidence_score=0.9),
    ]
    chosen = choose_default_source(sources, None)
    assert chosen.name == "lav1"


def test_choose_default_source_empty_list_returns_none():
    assert choose_default_source([], ["lav1"]) is None


def test_bake_produces_correct_track_layout(make_video_with_audio, tmp_path):
    video_path = make_video_with_audio(name="clip.mp4", duration=2.0)

    boom_path = tmp_path / "boom_processed.wav"
    lav1_path = tmp_path / "lav1_processed.wav"
    write_wav(boom_path, broadband_signal(2.0, seed=1, sample_rate=SAMPLE_RATE), SAMPLE_RATE)
    write_wav(lav1_path, broadband_signal(2.0, seed=2, sample_rate=SAMPLE_RATE), SAMPLE_RATE)

    sources = [
        BakeSource(name="boom", filepath=boom_path, confidence_score=0.5),
        BakeSource(name="lav1", filepath=lav1_path, confidence_score=0.9),
    ]

    output_path = tmp_path / "output" / "clip_synced.mp4"
    bake(
        video_path,
        output_path,
        scratch_track_index=0,
        matched_sources=sources,
        keep_original_audio_track=True,
        source_priority=None,
    )

    assert output_path.exists()
    streams = _ffprobe_audio_streams(output_path)
    assert len(streams) == 3  # scratch + boom + lav1

    scratch, boom, lav1 = streams
    assert _title(scratch) == "Scratch (Camera Original)"
    assert scratch["disposition"]["default"] == 0

    assert _title(boom) == "Synced - boom"
    assert boom["disposition"]["default"] == 0

    assert _title(lav1) == "Synced - lav1"
    assert lav1["disposition"]["default"] == 1  # highest confidence, no priority list given


def test_bake_without_keeping_scratch_track(make_video_with_audio, tmp_path):
    video_path = make_video_with_audio(name="clip.mp4", duration=2.0)

    boom_path = tmp_path / "boom_processed.wav"
    write_wav(boom_path, broadband_signal(2.0, seed=1, sample_rate=SAMPLE_RATE), SAMPLE_RATE)
    sources = [BakeSource(name="boom", filepath=boom_path, confidence_score=0.5)]

    output_path = tmp_path / "output" / "clip_synced.mp4"
    bake(
        video_path,
        output_path,
        scratch_track_index=0,
        matched_sources=sources,
        keep_original_audio_track=False,
    )

    streams = _ffprobe_audio_streams(output_path)
    assert len(streams) == 1
    assert _title(streams[0]) == "Synced - boom"
    assert streams[0]["disposition"]["default"] == 1
