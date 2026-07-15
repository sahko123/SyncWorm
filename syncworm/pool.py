"""Recursive scanner for the candidate audio pool directory."""

from __future__ import annotations

import logging
from pathlib import Path

from syncworm.extraction import ProbeError, probe_audio_file
from syncworm.models import AudioCandidate

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".wav", ".mp3", ".aac", ".flac", ".aif", ".aiff", ".m4a"}


def scan_audio_pool(audio_pool_dir: str | Path) -> list[AudioCandidate]:
    """Recursively scan audio_pool_dir for candidate audio files.

    Files that fail to probe (corrupt/unreadable) are skipped with a logged
    warning rather than aborting the whole scan.
    """
    audio_pool_dir = Path(audio_pool_dir)
    candidates: list[AudioCandidate] = []

    for path in sorted(audio_pool_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        try:
            info = probe_audio_file(path)
        except ProbeError as exc:
            logger.warning("Skipping unreadable pool audio file %s: %s", path, exc)
            continue
        candidates.append(
            AudioCandidate(
                name=path.stem,
                filepath=path,
                channels=info.channels,
                duration_seconds=info.duration_seconds,
            )
        )

    return candidates
