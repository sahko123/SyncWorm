import json
import subprocess
from pathlib import Path

import pytest

from audio_fixtures import broadband_signal, write_wav
from video_fixtures import make_synced_pair as _make_synced_pair
from syncworm import extraction, search as search_module
from syncworm.config import AudioChannelMode, SyncWormConfig
from syncworm.pipeline import run_pipeline, run_summary_to_dict

SAMPLE_RATE = 16000


def _base_config(tmp_path, **overrides) -> SyncWormConfig:
    kwargs = {
        "video_input_dir": tmp_path / "videos",
        "audio_pool_dir": tmp_path / "audio",
        "output_dir": tmp_path / "output",
        "confidence_threshold": 0.3,
        "correlation_sample_rate": SAMPLE_RATE,
        "audio_channel_mode": AudioChannelMode.PASSTHROUGH,
    }
    kwargs.update(overrides)
    return SyncWormConfig(**kwargs)


def test_multi_source_one_passes_one_fails(tmp_path):
    config = _base_config(tmp_path)
    video_path = config.video_input_dir / "clip.mp4"
    boom_path = config.audio_pool_dir / "boom.wav"
    _make_synced_pair(video_path, boom_path, video_duration=2.0, lead_in=0.0, seed=1)

    unrelated_path = config.audio_pool_dir / "unrelated.wav"
    write_wav(unrelated_path, broadband_signal(2.0, seed=99, sample_rate=SAMPLE_RATE), SAMPLE_RATE)

    summary = run_pipeline(config)

    job = summary.video_jobs[0]
    assert {r.candidate_name for r in job.matched_sources} == {"boom"}
    assert {r.candidate_name for r in job.search_results} == {"boom", "unrelated"}
    assert summary.unmatched_videos == []

    output_path = config.output_dir / "clip_synced.mp4"
    assert output_path.exists()
    streams = extraction.probe_audio_streams(output_path)
    assert len(streams) == 2  # scratch + boom


def test_unmatched_tracking(tmp_path):
    config = _base_config(tmp_path)

    matched_video = config.video_input_dir / "matched.mp4"
    boom_path = config.audio_pool_dir / "boom.wav"
    _make_synced_pair(matched_video, boom_path, video_duration=2.0, lead_in=0.0, seed=2)

    unmatched_video = config.video_input_dir / "unmatched.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=red:s=64x64:d=2",
            "-f", "lavfi", "-i", "sine=frequency=300:duration=2",
            "-shortest", "-c:v", "libx264", "-c:a", "aac",
            str(unmatched_video),
        ],
        capture_output=True, text=True,
    )

    orphan_path = config.audio_pool_dir / "orphan.wav"
    write_wav(orphan_path, broadband_signal(2.0, seed=50, sample_rate=SAMPLE_RATE), SAMPLE_RATE)

    summary = run_pipeline(config)

    video_names = {p.name for p in summary.unmatched_videos}
    assert video_names == {"unmatched.mp4"}

    audio_names = {p.name for p in summary.unmatched_audio_files}
    assert audio_names == {"orphan.wav"}

    assert not (config.output_dir / "unmatched_synced.mp4").exists()
    assert (config.output_dir / "matched_synced.mp4").exists()


def test_no_audio_track_handling(tmp_path, monkeypatch):
    config = _base_config(tmp_path)

    matched_video = config.video_input_dir / "matched.mp4"
    boom_path = config.audio_pool_dir / "boom.wav"
    _make_synced_pair(matched_video, boom_path, video_duration=2.0, lead_in=0.0, seed=3)

    silent_video = config.video_input_dir / "silent.mp4"
    silent_video.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=green:s=64x64:d=2", "-an", "-c:v", "libx264", str(silent_video)],
        capture_output=True, text=True,
    )

    real_extract = extraction.extract_audio_track

    def guarded_extract(video_path, *args, **kwargs):
        assert Path(video_path).name != "silent.mp4", "extraction must not run for a no-audio-track video"
        return real_extract(video_path, *args, **kwargs)

    monkeypatch.setattr(extraction, "extract_audio_track", guarded_extract)

    real_search = search_module.search_pool

    def guarded_search(video_filepath, *args, **kwargs):
        assert Path(video_filepath).name != "silent.mp4", "search must not run for a no-audio-track video"
        return real_search(video_filepath, *args, **kwargs)

    import syncworm.pipeline as pipeline_module
    monkeypatch.setattr(pipeline_module.search_module, "search_pool", guarded_search)

    summary = run_pipeline(config)

    no_audio_names = {p.name for p in summary.videos_with_no_audio_track}
    assert no_audio_names == {"silent.mp4"}
    assert "silent.mp4" not in {p.name for p in summary.unmatched_videos}
    assert (config.output_dir / "matched_synced.mp4").exists()


def test_shared_source_matches_multiple_videos(tmp_path):
    config = _base_config(tmp_path)
    shared_path = config.audio_pool_dir / "shared.wav"

    video_a = config.video_input_dir / "cam_a.mp4"
    video_b = config.video_input_dir / "cam_b.mp4"

    # shared.wav covers both videos' scratch windows (2s each) plus a 0.3s
    # lead-in, so video_a and video_b can each independently match it at a
    # different offset — simulating one continuous recorder covering two cameras.
    shared_base = broadband_signal(2.0 + 0.3, seed=7, sample_rate=SAMPLE_RATE)
    shared_path.parent.mkdir(parents=True, exist_ok=True)
    write_wav(shared_path, shared_base, SAMPLE_RATE)

    scratch_a = shared_base[: int(round(2.0 * SAMPLE_RATE))]
    scratch_a_wav = video_a.parent / "_scratch_a.wav"
    video_a.parent.mkdir(parents=True, exist_ok=True)
    write_wav(scratch_a_wav, scratch_a, SAMPLE_RATE)
    result_a = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=orange:s=64x64:d=2",
            "-i", str(scratch_a_wav),
            "-shortest", "-c:v", "libx264", "-c:a", "aac",
            str(video_a),
        ],
        capture_output=True, text=True,
    )
    assert result_a.returncode == 0, result_a.stderr

    lead_in_b = 0.3
    lead_in_samples = int(round(lead_in_b * SAMPLE_RATE))
    scratch_b = shared_base[lead_in_samples : lead_in_samples + int(round(2.0 * SAMPLE_RATE))]
    scratch_b_wav = video_b.parent / "_scratch_b.wav"
    video_b.parent.mkdir(parents=True, exist_ok=True)
    write_wav(scratch_b_wav, scratch_b, SAMPLE_RATE)

    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=purple:s=64x64:d=2",
            "-i", str(scratch_b_wav),
            "-shortest", "-c:v", "libx264", "-c:a", "aac",
            str(video_b),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    summary = run_pipeline(config)

    jobs_by_name = {j.video_filepath.name: j for j in summary.video_jobs}
    matches_a = {r.candidate_name: r for r in jobs_by_name["cam_a.mp4"].matched_sources}
    matches_b = {r.candidate_name: r for r in jobs_by_name["cam_b.mp4"].matched_sources}

    assert "shared" in matches_a
    assert "shared" in matches_b
    # each video independently recovers its own correct offset against the same file
    assert matches_a["shared"].offset_seconds == pytest.approx(0.0, abs=0.02)
    assert matches_b["shared"].offset_seconds == pytest.approx(lead_in_b, abs=0.02)
    assert "shared" not in {p.name.removesuffix(".wav") for p in summary.unmatched_audio_files}


def test_scratch_track_index_fallback(tmp_path, caplog):
    config = _base_config(tmp_path, scratch_track_index=1)
    video_path = config.video_input_dir / "clip.mp4"
    boom_path = config.audio_pool_dir / "boom.wav"
    _make_synced_pair(video_path, boom_path, video_duration=2.0, lead_in=0.0, seed=8)

    with caplog.at_level("WARNING"):
        summary = run_pipeline(config)

    job = summary.video_jobs[0]
    assert job.scratch_track_fallback is True
    assert job.scratch_track_index_used == 0
    assert {r.candidate_name for r in job.matched_sources} == {"boom"}
    assert any("falling back to 0" in message for message in caplog.messages)


def test_dry_run_produces_summary_without_media_files(tmp_path):
    config = _base_config(tmp_path, dry_run=True)
    video_path = config.video_input_dir / "clip.mp4"
    boom_path = config.audio_pool_dir / "boom.wav"
    _make_synced_pair(video_path, boom_path, video_duration=2.0, lead_in=0.0, seed=9)

    summary = run_pipeline(config)

    job = summary.video_jobs[0]
    assert {r.candidate_name for r in job.matched_sources} == {"boom"}

    assert not config.output_dir.exists() or not any(config.output_dir.rglob("*.mp4"))

    as_dict = run_summary_to_dict(summary)
    json.dumps(as_dict)  # must be JSON-serializable
    assert as_dict["video_jobs"][0]["matched_sources"][0]["candidate_name"] == "boom"
