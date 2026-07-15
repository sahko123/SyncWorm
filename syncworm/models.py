"""Shared data structures used across scanning, search, and pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AudioCandidate:
    name: str
    filepath: Path
    channels: int
    duration_seconds: float


@dataclass
class CorrelationResult:
    candidate_name: str
    candidate_filepath: Path
    video_filepath: Path
    offset_seconds: float
    confidence_score: float
    matched: bool  # True if confidence_score >= threshold


@dataclass
class VideoJob:
    video_filepath: Path
    search_results: list[CorrelationResult] = field(default_factory=list)
    matched_sources: list[CorrelationResult] = field(default_factory=list)
    chosen_default_track: str | None = None
    scratch_track_index_used: int | None = None
    scratch_track_fallback: bool = False


@dataclass(frozen=True)
class BakeSource:
    """A matched source ready to mux in — trimmed and channel-handled."""

    name: str
    filepath: Path
    confidence_score: float


@dataclass
class RunSummary:
    video_jobs: list[VideoJob]
    unmatched_videos: list[Path]  # zero matched_sources; search ran, nothing passed threshold
    unmatched_audio_files: list[Path]  # pool filepaths never matched to any video in this run
    videos_with_no_audio_track: list[Path]  # skipped before any search
