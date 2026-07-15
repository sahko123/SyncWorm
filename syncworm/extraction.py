"""ffmpeg/ffprobe wrappers: audio-stream probing and extraction from video.

This module only deals in raw, unmodified audio (original channel count and
sample rate preserved). Downmixing/resampling for correlation purposes lives
in correlator.py, not here.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ProbeError(RuntimeError):
    """Raised when ffprobe fails or returns unusable data."""


class ExtractionError(RuntimeError):
    """Raised when ffmpeg fails to extract an audio track."""


@dataclass(frozen=True)
class AudioStreamInfo:
    index: int  # 0-based index among this media file's audio streams (not container index)
    channels: int
    sample_rate: int
    duration_seconds: float


def _run_ffprobe(args: list[str]) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ProbeError(f"ffprobe failed on {args[-1]}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def probe_container_duration(media_path: str | Path) -> float:
    """Overall container duration in seconds (e.g. a video's play length)."""
    data = _run_ffprobe(["-show_entries", "format=duration", str(media_path)])
    duration = data.get("format", {}).get("duration")
    return float(duration) if duration is not None else 0.0


def probe_audio_streams(media_path: str | Path) -> list[AudioStreamInfo]:
    """Return info for every audio stream in a media file (video or audio-only file).

    Empty list means no audio track at all.
    """
    data = _run_ffprobe(
        [
            "-show_entries",
            "stream=channels,sample_rate,duration",
            "-select_streams",
            "a",
            str(media_path),
        ]
    )
    container_duration = None
    streams = []
    for i, stream in enumerate(data.get("streams", [])):
        duration = stream.get("duration")
        if duration is None:
            if container_duration is None:
                container_duration = probe_container_duration(media_path)
            duration = container_duration
        streams.append(
            AudioStreamInfo(
                index=i,
                channels=int(stream.get("channels", 0)),
                sample_rate=int(stream.get("sample_rate", 0)),
                duration_seconds=float(duration),
            )
        )
    return streams


def has_audio_track(video_path: str | Path) -> bool:
    return len(probe_audio_streams(video_path)) > 0


def probe_audio_file(audio_path: str | Path) -> AudioStreamInfo:
    """Probe a standalone (pool) audio file's first audio stream."""
    streams = probe_audio_streams(audio_path)
    if not streams:
        raise ProbeError(f"{audio_path} has no audio stream")
    return streams[0]


def resolve_scratch_track_index(
    streams: list[AudioStreamInfo], requested_index: int
) -> tuple[int, bool]:
    """Resolve which audio stream index to use as scratch.

    Returns (actual_index, fell_back). Falls back to 0 if requested_index
    doesn't exist among the given streams.
    """
    if any(s.index == requested_index for s in streams):
        return requested_index, False
    return 0, True


def extract_audio_track(
    video_path: str | Path,
    output_path: str | Path,
    stream_index: int = 0,
) -> Path:
    """Extract one audio stream from a video into a new PCM WAV file.

    Preserves the original channel count and sample rate. `output_path` must
    be a new file path — this never reads back into the source video.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-map",
            f"0:a:{stream_index}",
            "-vn",
            "-acodec",
            "pcm_s16le",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ExtractionError(
            f"ffmpeg failed extracting audio stream {stream_index} from {video_path}: "
            f"{result.stderr.strip()}"
        )
    return output_path
