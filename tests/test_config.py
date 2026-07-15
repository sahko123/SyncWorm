import json

import pytest
from pydantic import ValidationError

from syncworm.config import AudioChannelMode, SyncWormConfig


def _base_kwargs(tmp_path, output_subdir="output"):
    video_dir = tmp_path / "videos"
    audio_dir = tmp_path / "audio"
    output_dir = tmp_path / output_subdir
    video_dir.mkdir(exist_ok=True)
    audio_dir.mkdir(exist_ok=True)
    return {
        "video_input_dir": video_dir,
        "audio_pool_dir": audio_dir,
        "output_dir": output_dir,
    }


def test_defaults_applied(tmp_path):
    config = SyncWormConfig(**_base_kwargs(tmp_path))
    assert config.scratch_track_index == 0
    assert config.confidence_threshold == 0.3
    assert config.keep_original_audio_track is True
    assert config.audio_channel_mode == AudioChannelMode.DUAL_MONO
    assert config.dry_run is False
    assert config.run_summary_path == config.output_dir / "syncworm_run_summary.json"


def test_output_dir_equal_to_input_rejected(tmp_path):
    kwargs = _base_kwargs(tmp_path)
    kwargs["output_dir"] = kwargs["video_input_dir"]
    with pytest.raises(ValidationError):
        SyncWormConfig(**kwargs)


def test_output_dir_nested_inside_input_rejected(tmp_path):
    kwargs = _base_kwargs(tmp_path)
    kwargs["output_dir"] = kwargs["audio_pool_dir"] / "nested_output"
    with pytest.raises(ValidationError):
        SyncWormConfig(**kwargs)


def test_input_dir_nested_inside_output_rejected(tmp_path):
    kwargs = _base_kwargs(tmp_path)
    kwargs["video_input_dir"] = kwargs["output_dir"] / "videos"
    with pytest.raises(ValidationError):
        SyncWormConfig(**kwargs)


def test_negative_scratch_track_index_rejected(tmp_path):
    kwargs = _base_kwargs(tmp_path)
    kwargs["scratch_track_index"] = -1
    with pytest.raises(ValidationError):
        SyncWormConfig(**kwargs)


def test_output_naming_requires_stem_placeholder(tmp_path):
    kwargs = _base_kwargs(tmp_path)
    kwargs["output_naming"] = "no_placeholder_here"
    with pytest.raises(ValidationError):
        SyncWormConfig(**kwargs)


def test_input_dir_populates_both_video_and_audio_dirs(tmp_path):
    input_dir = tmp_path / "shoot"
    input_dir.mkdir()
    output_dir = tmp_path / "output"

    config = SyncWormConfig(input_dir=input_dir, output_dir=output_dir)

    assert config.video_input_dir == input_dir
    assert config.audio_pool_dir == input_dir


def test_explicit_dirs_override_input_dir(tmp_path):
    input_dir = tmp_path / "shoot"
    video_dir = tmp_path / "videos_only"
    input_dir.mkdir()
    video_dir.mkdir()
    output_dir = tmp_path / "output"

    config = SyncWormConfig(input_dir=input_dir, video_input_dir=video_dir, output_dir=output_dir)

    assert config.video_input_dir == video_dir
    assert config.audio_pool_dir == input_dir


def test_missing_both_input_dir_and_split_dirs_rejected(tmp_path):
    with pytest.raises(ValidationError):
        SyncWormConfig(output_dir=tmp_path / "output")


def test_load_from_json_file(tmp_path):
    kwargs = _base_kwargs(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "video_input_dir": str(kwargs["video_input_dir"]),
                "audio_pool_dir": str(kwargs["audio_pool_dir"]),
                "output_dir": str(kwargs["output_dir"]),
                "confidence_threshold": 0.5,
            }
        )
    )
    config = SyncWormConfig.load(config_path)
    assert config.confidence_threshold == 0.5
