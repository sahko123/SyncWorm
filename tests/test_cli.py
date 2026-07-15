import json

import pytest

from video_fixtures import make_synced_pair
from syncworm.cli import build_arg_parser, build_config, main
from syncworm.config import AudioChannelMode


def test_build_config_requires_dirs_without_config_file():
    parser = build_arg_parser()
    args = parser.parse_args([])
    with pytest.raises(SystemExit):
        build_config(args)


def test_build_config_from_cli_flags(tmp_path):
    video_dir = tmp_path / "videos"
    audio_dir = tmp_path / "audio"
    output_dir = tmp_path / "output"
    video_dir.mkdir()
    audio_dir.mkdir()

    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "--video-input-dir", str(video_dir),
            "--audio-pool-dir", str(audio_dir),
            "--output-dir", str(output_dir),
            "--confidence-threshold", "0.5",
            "--audio-channel-mode", "dual_mono",
        ]
    )

    config = build_config(args)
    assert config.confidence_threshold == 0.5
    assert config.audio_channel_mode == AudioChannelMode.DUAL_MONO
    assert config.dry_run is False


def test_dry_run_flag_overrides_config_file(tmp_path):
    video_dir = tmp_path / "videos"
    audio_dir = tmp_path / "audio"
    output_dir = tmp_path / "output"
    video_dir.mkdir()
    audio_dir.mkdir()

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "video_input_dir": str(video_dir),
                "audio_pool_dir": str(audio_dir),
                "output_dir": str(output_dir),
                "dry_run": False,
            }
        )
    )

    parser = build_arg_parser()
    args = parser.parse_args(["--config", str(config_path), "--dry-run"])
    config = build_config(args)
    assert config.dry_run is True


def test_cli_flags_override_config_file(tmp_path):
    video_dir = tmp_path / "videos"
    audio_dir = tmp_path / "audio"
    output_dir = tmp_path / "output"
    video_dir.mkdir()
    audio_dir.mkdir()

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "video_input_dir": str(video_dir),
                "audio_pool_dir": str(audio_dir),
                "output_dir": str(output_dir),
                "confidence_threshold": 0.2,
            }
        )
    )

    parser = build_arg_parser()
    args = parser.parse_args(["--config", str(config_path), "--confidence-threshold", "0.8"])
    config = build_config(args)
    assert config.confidence_threshold == 0.8


def test_build_config_from_single_input_dir(tmp_path):
    input_dir = tmp_path / "shoot"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    parser = build_arg_parser()
    args = parser.parse_args([str(input_dir), "--output-dir", str(output_dir)])

    config = build_config(args)
    assert config.video_input_dir == input_dir
    assert config.audio_pool_dir == input_dir


def test_video_input_dir_override_wins_over_input_dir(tmp_path):
    input_dir = tmp_path / "shoot"
    video_dir = tmp_path / "videos_only"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    video_dir.mkdir()

    parser = build_arg_parser()
    args = parser.parse_args(
        [str(input_dir), "--video-input-dir", str(video_dir), "--output-dir", str(output_dir)]
    )

    config = build_config(args)
    assert config.video_input_dir == video_dir
    assert config.audio_pool_dir == input_dir  # still falls back to input_dir


def test_build_config_missing_output_dir_still_required(tmp_path):
    input_dir = tmp_path / "shoot"
    input_dir.mkdir()

    parser = build_arg_parser()
    args = parser.parse_args([str(input_dir)])
    with pytest.raises(SystemExit):
        build_config(args)


def test_main_end_to_end_with_single_input_dir(tmp_path, capsys):
    input_dir = tmp_path / "shoot"
    output_dir = tmp_path / "output"

    video_path = input_dir / "clip.mp4"
    boom_path = input_dir / "boom.wav"
    make_synced_pair(video_path, boom_path, video_duration=2.0, lead_in=0.0, seed=43)

    exit_code = main(
        [str(input_dir), "--output-dir", str(output_dir), "--audio-channel-mode", "passthrough"]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "boom" in captured.out
    assert (output_dir / "clip_synced.mp4").exists()


def test_main_end_to_end_writes_report_and_summary(tmp_path, capsys):
    video_dir = tmp_path / "videos"
    audio_dir = tmp_path / "audio"
    output_dir = tmp_path / "output"

    video_path = video_dir / "clip.mp4"
    boom_path = audio_dir / "boom.wav"
    make_synced_pair(video_path, boom_path, video_duration=2.0, lead_in=0.0, seed=42)

    exit_code = main(
        [
            "--video-input-dir", str(video_dir),
            "--audio-pool-dir", str(audio_dir),
            "--output-dir", str(output_dir),
            "--audio-channel-mode", "passthrough",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "boom" in captured.out
    assert "Run summary written to" in captured.out

    summary_path = output_dir / "syncworm_run_summary.json"
    assert summary_path.exists()
    data = json.loads(summary_path.read_text())
    assert data["video_jobs"][0]["matched_sources"][0]["candidate_name"] == "boom"

    assert (output_dir / "clip_synced.mp4").exists()
