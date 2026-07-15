"""Orchestrates the full run: scan -> precheck -> search -> (trim -> bake) -> RunSummary.

Public functions here are plain Python calls returning structured results
(VideoJob/RunSummary), not print statements or CLI-specific I/O, so a future
GUI can call into the same pipeline without any refactor.
"""

from __future__ import annotations

import dataclasses
import logging
import tempfile
import time
from pathlib import Path

from syncworm import bake as bake_module
from syncworm import channel_handler, extraction, pool, search as search_module, trimmer, video_scanner
from syncworm.config import SyncWormConfig
from syncworm.models import BakeSource, RunSummary, VideoJob

logger = logging.getLogger(__name__)


def _process_video(
    job: VideoJob,
    candidates: list,
    config: SyncWormConfig,
    work_dir: Path,
) -> None:
    streams = extraction.probe_audio_streams(job.video_filepath)
    if not streams:
        return  # caller checks probe result and routes to videos_with_no_audio_track

    scratch_index, fell_back = extraction.resolve_scratch_track_index(
        streams, config.scratch_track_index
    )
    job.scratch_track_index_used = scratch_index
    job.scratch_track_fallback = fell_back
    if fell_back:
        logger.warning(
            "%s: scratch_track_index %d not present, falling back to 0",
            job.video_filepath, config.scratch_track_index,
        )

    scratch_wav = work_dir / f"{job.video_filepath.stem}_scratch.wav"
    extraction_start = time.perf_counter()
    extraction.extract_audio_track(job.video_filepath, scratch_wav, stream_index=scratch_index)
    job.extraction_seconds = time.perf_counter() - extraction_start
    logger.info("%s: extraction took %.1fs", job.video_filepath, job.extraction_seconds)

    search_start = time.perf_counter()
    job.search_results = search_module.search_pool(
        job.video_filepath,
        scratch_wav,
        candidates,
        config.confidence_threshold,
        sample_rate=config.correlation_sample_rate,
    )
    job.search_seconds = time.perf_counter() - search_start
    logger.info(
        "%s: search took %.1fs across %d candidates", job.video_filepath, job.search_seconds, len(candidates)
    )
    job.matched_sources = search_module.matched_sources(job.search_results)

    if config.dry_run or not job.matched_sources:
        return

    bake_start = time.perf_counter()
    video_duration = extraction.probe_container_duration(job.video_filepath)
    bake_sources = []
    for i, result in enumerate(job.matched_sources):
        trimmed_path = work_dir / f"{job.video_filepath.stem}_{i}_{result.candidate_name}_trimmed.wav"
        trimmer.trim_to_video_duration(
            result.candidate_filepath, trimmed_path, result.offset_seconds, video_duration
        )

        processed_path = work_dir / f"{job.video_filepath.stem}_{i}_{result.candidate_name}_final.wav"
        channel_handler.apply_channel_mode(trimmed_path, processed_path, config.audio_channel_mode)

        bake_sources.append(
            BakeSource(
                name=result.candidate_name,
                filepath=processed_path,
                confidence_score=result.confidence_score,
            )
        )

    default_source = bake_module.choose_default_source(bake_sources, config.source_priority)
    job.chosen_default_track = default_source.name if default_source else None

    output_path = bake_module.mirrored_output_path(
        job.video_filepath, config.video_input_dir, config.output_dir, config.output_naming
    )
    bake_module.bake(
        job.video_filepath,
        output_path,
        scratch_index,
        bake_sources,
        keep_original_audio_track=config.keep_original_audio_track,
        source_priority=config.source_priority,
    )
    job.trim_and_bake_seconds = time.perf_counter() - bake_start
    logger.info("%s: trim+bake took %.1fs", job.video_filepath, job.trim_and_bake_seconds)


def run_pipeline(config: SyncWormConfig) -> RunSummary:
    video_jobs = video_scanner.scan_video_inputs(config.video_input_dir)
    candidates = pool.scan_audio_pool(config.audio_pool_dir)

    videos_with_no_audio_track: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="syncworm_") as tmp:
        work_dir = Path(tmp)
        for job in video_jobs:
            if not extraction.has_audio_track(job.video_filepath):
                videos_with_no_audio_track.append(job.video_filepath)
                logger.info("%s: no audio track, skipping", job.video_filepath)
                continue
            _process_video(job, candidates, config, work_dir)

    processed_jobs = [j for j in video_jobs if j.video_filepath not in videos_with_no_audio_track]
    unmatched_videos = [j.video_filepath for j in processed_jobs if not j.matched_sources]

    matched_candidate_names = {
        result.candidate_name
        for job in processed_jobs
        for result in job.matched_sources
    }
    unmatched_audio_files = [
        candidate.filepath for candidate in candidates if candidate.name not in matched_candidate_names
    ]

    return RunSummary(
        video_jobs=video_jobs,
        unmatched_videos=unmatched_videos,
        unmatched_audio_files=unmatched_audio_files,
        videos_with_no_audio_track=videos_with_no_audio_track,
    )


def run_summary_to_dict(summary: RunSummary) -> dict:
    """JSON-serializable representation of a RunSummary (Path -> str)."""
    return _stringify_paths(dataclasses.asdict(summary))


def _stringify_paths(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {k: _stringify_paths(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_stringify_paths(v) for v in value]
    return value
