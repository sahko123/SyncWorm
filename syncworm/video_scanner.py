"""Recursive scanner for the video input directory."""

from __future__ import annotations

from pathlib import Path

from syncworm.models import VideoJob

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mxf", ".avi", ".mkv"}


def scan_video_inputs(video_input_dir: str | Path) -> list[VideoJob]:
    """Recursively scan video_input_dir for video files, one VideoJob per file."""
    video_input_dir = Path(video_input_dir)
    return [
        VideoJob(video_filepath=path)
        for path in sorted(video_input_dir.rglob("*"))
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    ]
