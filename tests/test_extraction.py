import pytest

from syncworm.extraction import (
    AudioStreamInfo,
    ProbeError,
    extract_audio_track,
    has_audio_track,
    probe_audio_file,
    probe_audio_streams,
    resolve_scratch_track_index,
)


def test_has_audio_track_true(make_video_with_audio):
    video = make_video_with_audio()
    assert has_audio_track(video) is True


def test_has_audio_track_false(make_video_without_audio):
    video = make_video_without_audio()
    assert has_audio_track(video) is False


def test_probe_audio_streams_detects_duration_and_channels(make_video_with_audio):
    video = make_video_with_audio(duration=2.0)
    streams = probe_audio_streams(video)
    assert len(streams) == 1
    assert streams[0].index == 0
    assert streams[0].channels == 1
    assert streams[0].duration_seconds == pytest.approx(2.0, abs=0.2)


def test_probe_audio_file(make_audio_file):
    audio = make_audio_file(duration=1.5, channels=2)
    info = probe_audio_file(audio)
    assert info.channels == 2
    assert info.duration_seconds == pytest.approx(1.5, abs=0.2)


def test_probe_audio_file_raises_on_no_audio(make_video_without_audio):
    video = make_video_without_audio()
    with pytest.raises(ProbeError):
        probe_audio_file(video)


def test_extract_audio_track_produces_wav(make_video_with_audio, tmp_path):
    video = make_video_with_audio(duration=2.0)
    out_path = tmp_path / "extracted" / "scratch.wav"

    result_path = extract_audio_track(video, out_path, stream_index=0)

    assert result_path == out_path
    assert out_path.exists()
    info = probe_audio_file(out_path)
    assert info.duration_seconds == pytest.approx(2.0, abs=0.2)


def test_resolve_scratch_track_index_no_fallback():
    streams = [
        AudioStreamInfo(index=0, channels=2, sample_rate=48000, duration_seconds=10.0),
        AudioStreamInfo(index=1, channels=1, sample_rate=48000, duration_seconds=10.0),
    ]
    index, fell_back = resolve_scratch_track_index(streams, 1)
    assert index == 1
    assert fell_back is False


def test_resolve_scratch_track_index_falls_back_to_zero():
    streams = [
        AudioStreamInfo(index=0, channels=2, sample_rate=48000, duration_seconds=10.0),
    ]
    index, fell_back = resolve_scratch_track_index(streams, 1)
    assert index == 0
    assert fell_back is True
