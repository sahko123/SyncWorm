"""Per-video pool search: correlate a video's scratch audio against every candidate."""

from __future__ import annotations

from pathlib import Path

from syncworm.correlator import correlate
from syncworm.models import AudioCandidate, CorrelationResult


def search_pool(
    video_filepath: str | Path,
    scratch_audio_path: str | Path,
    candidates: list[AudioCandidate],
    confidence_threshold: float,
    sample_rate: int = 16000,
) -> list[CorrelationResult]:
    """Correlate every pool candidate against one video's scratch audio.

    Returns one CorrelationResult per candidate — full visibility for
    sanity-checking near-misses, not just the winners — each flagged
    matched=True/False against confidence_threshold. Each candidate gets
    its own independently computed offset and score.
    """
    video_filepath = Path(video_filepath)
    results = []
    for candidate in candidates:
        outcome = correlate(scratch_audio_path, candidate.filepath, sample_rate=sample_rate)
        results.append(
            CorrelationResult(
                candidate_name=candidate.name,
                candidate_filepath=candidate.filepath,
                video_filepath=video_filepath,
                offset_seconds=outcome.offset_seconds,
                confidence_score=outcome.confidence_score,
                matched=outcome.confidence_score >= confidence_threshold,
            )
        )
    return results


def matched_sources(results: list[CorrelationResult]) -> list[CorrelationResult]:
    return [r for r in results if r.matched]
