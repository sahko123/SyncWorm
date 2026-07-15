"""Config schema and loading for a SyncWorm run."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, model_validator


class AudioChannelMode(str, Enum):
    MONO = "mono"
    DUAL_MONO = "dual_mono"
    PASSTHROUGH = "passthrough"


class SyncWormConfig(BaseModel):
    input_dir: Path | None = None  # single folder scanned for both video and audio, by extension
    video_input_dir: Path | None = None  # overrides input_dir for video scanning if set
    audio_pool_dir: Path | None = None  # overrides input_dir for audio scanning if set
    output_dir: Path

    scratch_track_index: int = 0
    confidence_threshold: float = 0.3
    keep_original_audio_track: bool = True
    audio_channel_mode: AudioChannelMode = AudioChannelMode.DUAL_MONO
    source_priority: list[str] | None = None
    correlation_sample_rate: int = 16000
    skip_implausible_candidates: bool = False
    output_naming: str = "{stem}_synced{suffix}"
    run_summary_path: Path | None = None
    dry_run: bool = False

    @model_validator(mode="after")
    def _validate(self) -> "SyncWormConfig":
        if self.video_input_dir is None:
            self.video_input_dir = self.input_dir
        if self.audio_pool_dir is None:
            self.audio_pool_dir = self.input_dir
        if self.video_input_dir is None or self.audio_pool_dir is None:
            raise ValueError(
                "Provide input_dir (scanned for both video and audio by extension), or "
                "both video_input_dir and audio_pool_dir explicitly"
            )

        if self.scratch_track_index < 0:
            raise ValueError("scratch_track_index must be >= 0")
        if self.confidence_threshold < 0:
            raise ValueError("confidence_threshold must be >= 0")
        if self.correlation_sample_rate <= 0:
            raise ValueError("correlation_sample_rate must be > 0")
        if "{stem}" not in self.output_naming:
            raise ValueError("output_naming must include a '{stem}' placeholder")

        video_input = self.video_input_dir.resolve()
        audio_pool = self.audio_pool_dir.resolve()
        output = self.output_dir.resolve()

        for label, other in (("video_input_dir", video_input), ("audio_pool_dir", audio_pool)):
            if output == other or _is_within(output, other) or _is_within(other, output):
                raise ValueError(
                    f"output_dir must not equal, contain, or be contained within {label} "
                    f"({other}) — originals must never be at risk of being treated as output, "
                    f"or output files re-scanned as new inputs on a later run"
                )

        if self.run_summary_path is None:
            self.run_summary_path = self.output_dir / "syncworm_run_summary.json"

        return self

    @classmethod
    def load(cls, path: str | Path) -> "SyncWormConfig":
        data = json.loads(Path(path).read_text())
        return cls.model_validate(data)


def _is_within(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False
