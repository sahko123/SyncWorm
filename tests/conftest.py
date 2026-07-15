"""Shared test fixtures for building synthetic media files via ffmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg fixture generation failed: {result.stderr}")


@pytest.fixture
def make_video_with_audio(tmp_path):
    def _make(name: str = "video.mp4", duration: float = 2.0, frequency: int = 440) -> Path:
        out = tmp_path / name
        out.parent.mkdir(parents=True, exist_ok=True)
        _run_ffmpeg(
            [
                "-f", "lavfi", "-i", f"color=c=blue:s=64x64:d={duration}",
                "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={duration}",
                "-shortest", "-c:v", "libx264", "-c:a", "aac",
                str(out),
            ]
        )
        return out

    return _make


@pytest.fixture
def make_video_without_audio(tmp_path):
    def _make(name: str = "silent_video.mp4", duration: float = 2.0) -> Path:
        out = tmp_path / name
        out.parent.mkdir(parents=True, exist_ok=True)
        _run_ffmpeg(
            [
                "-f", "lavfi", "-i", f"color=c=red:s=64x64:d={duration}",
                "-an", "-c:v", "libx264",
                str(out),
            ]
        )
        return out

    return _make


@pytest.fixture
def make_audio_file(tmp_path):
    def _make(
        name: str = "audio.wav",
        duration: float = 2.0,
        frequency: int = 440,
        channels: int = 1,
    ) -> Path:
        out = tmp_path / name
        out.parent.mkdir(parents=True, exist_ok=True)
        _run_ffmpeg(
            [
                "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={duration}",
                "-ac", str(channels),
                str(out),
            ]
        )
        return out

    return _make
