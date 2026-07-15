"""Synthetic video+matched-audio-pair helpers shared across pipeline/cli tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from audio_fixtures import broadband_signal, write_wav

SAMPLE_RATE = 16000


def make_synced_pair(
    video_path: Path,
    candidate_path: Path,
    video_duration: float,
    lead_in: float,
    seed: int,
    sample_rate: int = SAMPLE_RATE,
) -> None:
    """A video with embedded scratch audio, and a pool candidate wav that syncs to
    it with a known offset == lead_in (candidate has lead_in extra seconds up front).
    """
    base = broadband_signal(video_duration + lead_in, seed, sample_rate)
    lead_in_samples = int(round(lead_in * sample_rate))
    scratch = base[lead_in_samples:]

    video_path.parent.mkdir(parents=True, exist_ok=True)
    scratch_wav = video_path.parent / f"_scratch_src_{seed}.wav"
    write_wav(scratch_wav, scratch, sample_rate)

    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=blue:s=64x64:d={video_duration}",
            "-i", str(scratch_wav),
            "-shortest", "-c:v", "libx264", "-c:a", "aac",
            str(video_path),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    write_wav(candidate_path, base, sample_rate)
