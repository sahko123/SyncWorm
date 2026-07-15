"""Audio slicing to fit a matched source into the video's existing duration.

This is the mandatory v1-scope trim only (Step 6 of the plan) — not a
user-facing trim feature. Original channel count and sample rate are
preserved; channel conversion for baking happens later in
channel_handler.py.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from syncworm.extraction import probe_audio_file


class TrimError(RuntimeError):
    """Raised when ffmpeg fails to decode audio for trimming."""


def _decode_native_pcm(path: str | Path, channels: int) -> np.ndarray:
    """Decode audio to int16 PCM at its own native sample rate/channel count (no downmix)."""
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-"],
        capture_output=True,
    )
    if result.returncode != 0:
        raise TrimError(
            f"ffmpeg failed decoding {path}: {result.stderr.decode(errors='replace').strip()}"
        )
    samples = np.frombuffer(result.stdout, dtype=np.int16)
    if channels > 1:
        usable_len = (len(samples) // channels) * channels
        samples = samples[:usable_len].reshape(-1, channels)
    return samples


def _silence(length: int, channels: int) -> np.ndarray:
    shape = (length, channels) if channels > 1 else (length,)
    return np.zeros(shape, dtype=np.int16)


def trim_to_video_duration(
    candidate_path: str | Path,
    output_path: str | Path,
    offset_seconds: float,
    video_duration_seconds: float,
) -> Path:
    """Slice/pad a matched audio source so it exactly spans the video's duration.

    offset_seconds is the point in candidate_path where the video's start
    aligns (as computed by correlator.correlate): positive means the
    candidate has that much lead-in to trim off the front; negative means
    the candidate started recording after the video, so that much silence
    is prepended instead. Output always covers exactly
    video_duration_seconds, padding with silence at the tail if the
    candidate runs out early.
    """
    info = probe_audio_file(candidate_path)
    sample_rate = info.sample_rate
    channels = info.channels

    samples = _decode_native_pcm(candidate_path, channels)
    target_len = int(round(video_duration_seconds * sample_rate))

    if offset_seconds >= 0:
        start_sample = int(round(offset_seconds * sample_rate))
        trimmed = samples[start_sample:]
    else:
        pad_len = int(round(-offset_seconds * sample_rate))
        trimmed = np.concatenate([_silence(pad_len, channels), samples], axis=0)

    if len(trimmed) < target_len:
        trimmed = np.concatenate([trimmed, _silence(target_len - len(trimmed), channels)], axis=0)
    else:
        trimmed = trimmed[:target_len]

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(str(output_path), sample_rate, trimmed)
    return output_path
