"""Synthetic audio signal helpers shared across correlator/search tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.io import wavfile


def broadband_signal(duration_seconds: float, seed: int, sample_rate: int) -> np.ndarray:
    """A noise-like signal with enough structure to correlate sharply, deterministic per seed."""
    rng = np.random.default_rng(seed)
    n = int(duration_seconds * sample_rate)
    return rng.normal(0, 1, n)


def write_wav(path: Path, samples: np.ndarray, sample_rate: int, channels: int = 1) -> None:
    data = np.clip(samples, -1.0, 1.0) * 32767
    data = data.astype(np.int16)
    if channels == 2:
        data = np.column_stack([data, data])
    wavfile.write(str(path), sample_rate, data)
