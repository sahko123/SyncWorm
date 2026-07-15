"""FFT cross-correlation core: downmix, resample, normalize, offset + confidence scoring.

This is the unit tested most rigorously in isolation (see tests/test_correlator.py),
per the plan's testing considerations.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import signal


class DecodeError(RuntimeError):
    """Raised when ffmpeg fails to decode an audio file for correlation."""


@dataclass(frozen=True)
class CorrelationOutcome:
    offset_seconds: float
    confidence_score: float


def load_mono_signal(path: str | Path, sample_rate: int) -> np.ndarray:
    """Decode any audio file to a mean-centered mono float64 array at sample_rate.

    Uses ffmpeg for decoding so any format ffmpeg supports (wav, mp3, aac,
    flac, ...) is handled uniformly. This downmix/resample is for correlation
    comparison only — it never touches the audio that eventually gets baked.
    """
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(path),
            "-ac", "1", "-ar", str(sample_rate),
            "-f", "s16le", "-",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise DecodeError(
            f"ffmpeg failed decoding {path}: {result.stderr.decode(errors='replace').strip()}"
        )

    samples = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float64)
    if samples.size == 0:
        raise DecodeError(f"{path} decoded to zero samples")
    samples -= samples.mean()
    return samples


def correlate(
    scratch_path: str | Path,
    candidate_path: str | Path,
    sample_rate: int = 16000,
) -> CorrelationOutcome:
    """Cross-correlate a candidate audio file against a video's scratch audio track.

    offset_seconds is the position within the candidate file where the video's
    start aligns — i.e. candidate[offset_seconds : offset_seconds + video_duration]
    is synced to the video. This is exactly what trimmer.py consumes. A
    positive offset means the candidate recording started before the video.
    """
    scratch = load_mono_signal(scratch_path, sample_rate)
    candidate = load_mono_signal(candidate_path, sample_rate)

    correlation = signal.correlate(candidate, scratch, mode="full", method="fft")
    lags = signal.correlation_lags(len(candidate), len(scratch), mode="full")

    peak_index = int(np.argmax(np.abs(correlation)))
    peak_lag = int(lags[peak_index])

    offset_seconds = peak_lag / sample_rate
    confidence_score = _normalized_confidence(scratch, candidate, peak_lag)

    return CorrelationOutcome(offset_seconds=offset_seconds, confidence_score=confidence_score)


def _normalized_confidence(scratch: np.ndarray, candidate: np.ndarray, peak_lag: int) -> float:
    """Normalized cross-correlation coefficient (bounded ~[0, 1]) at the winning lag.

    Computed only over the samples that actually overlap at peak_lag, rather
    than the whole raw correlation array's stddev — a stddev-based score is
    biased upward by how many lags get searched (extreme-value statistics
    mean even unrelated audio occasionally spikes high once you search
    enough lag positions), which this avoids since it only ever looks at one
    fixed-length aligned window.
    """
    scratch_start = max(0, -peak_lag)
    candidate_start = max(0, peak_lag)
    overlap = min(len(scratch) - scratch_start, len(candidate) - candidate_start)
    if overlap <= 0:
        return 0.0

    scratch_segment = scratch[scratch_start : scratch_start + overlap]
    candidate_segment = candidate[candidate_start : candidate_start + overlap]

    numerator = abs(float(np.dot(scratch_segment, candidate_segment)))
    denominator = float(np.linalg.norm(scratch_segment) * np.linalg.norm(candidate_segment))
    if denominator == 0:
        return 0.0
    return numerator / denominator
