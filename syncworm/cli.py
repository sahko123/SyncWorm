"""CLI entry point for SyncWorm."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from pydantic import ValidationError

from syncworm.config import AudioChannelMode, SyncWormConfig
from syncworm.models import RunSummary
from syncworm.pipeline import run_pipeline, run_summary_to_dict


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="syncworm",
        description=(
            "Search a pool of external audio against video scratch tracks via FFT "
            "cross-correlation, then bake matches onto new video files."
        ),
    )
    parser.add_argument(
        "--config", type=Path, help="Path to a JSON config file (see docs/SyncWorm_Plan.md)."
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        nargs="?",
        default=None,
        help=(
            "Folder scanned recursively for both video and audio files, split by "
            "extension (the default way to run). Use --video-input-dir/--audio-pool-dir "
            "instead if video and audio live in separate trees."
        ),
    )
    parser.add_argument(
        "--video-input-dir", type=Path, help="Overrides input_dir for video scanning."
    )
    parser.add_argument(
        "--audio-pool-dir", type=Path, help="Overrides input_dir for audio scanning."
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--scratch-track-index", type=int, default=None)
    parser.add_argument("--confidence-threshold", type=float, default=None)
    parser.add_argument(
        "--audio-channel-mode", choices=[m.value for m in AudioChannelMode], default=None
    )
    parser.add_argument("--correlation-sample-rate", type=int, default=None)
    parser.add_argument("--run-summary-path", type=Path, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run search/validation and produce the report, but skip trimming/baking.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return parser


def build_config(args: argparse.Namespace) -> SyncWormConfig:
    base = json.loads(args.config.read_text()) if args.config else {}

    overrides = {
        "input_dir": args.input_dir,
        "video_input_dir": args.video_input_dir,
        "audio_pool_dir": args.audio_pool_dir,
        "output_dir": args.output_dir,
        "scratch_track_index": args.scratch_track_index,
        "confidence_threshold": args.confidence_threshold,
        "audio_channel_mode": args.audio_channel_mode,
        "correlation_sample_rate": args.correlation_sample_rate,
        "run_summary_path": args.run_summary_path,
    }
    base.update({k: v for k, v in overrides.items() if v is not None})

    if args.dry_run:
        base["dry_run"] = True

    if "output_dir" not in base:
        raise SystemExit("Missing required config field: output_dir (pass --config or --output-dir)")

    has_input_dir = "input_dir" in base
    has_split_dirs = "video_input_dir" in base and "audio_pool_dir" in base
    if not has_input_dir and not has_split_dirs:
        raise SystemExit(
            "Missing input location: pass an input_dir (positional, --config, or "
            "otherwise), or both --video-input-dir and --audio-pool-dir"
        )

    try:
        return SyncWormConfig.model_validate(base)
    except ValidationError as exc:
        raise SystemExit(f"Invalid config: {exc}") from exc


def print_report(summary: RunSummary) -> None:
    print("\n=== Per-video search results ===")
    for job in summary.video_jobs:
        print(f"\n{job.video_filepath}")
        if not job.search_results:
            print("  (no audio track / no candidates searched)")
            continue
        for result in sorted(job.search_results, key=lambda r: r.confidence_score, reverse=True):
            flag = "MATCH" if result.matched else "     "
            print(
                f"  [{flag}] {result.candidate_name:<20} "
                f"offset={result.offset_seconds:+.3f}s confidence={result.confidence_score:.3f}"
            )
        if job.chosen_default_track:
            print(f"  default track: {job.chosen_default_track}")
        timing_parts = []
        if job.extraction_seconds is not None:
            timing_parts.append(f"extraction={job.extraction_seconds:.1f}s")
        if job.search_seconds is not None:
            timing_parts.append(f"search={job.search_seconds:.1f}s")
        if job.trim_and_bake_seconds is not None:
            timing_parts.append(f"trim+bake={job.trim_and_bake_seconds:.1f}s")
        if timing_parts:
            print(f"  timing: {', '.join(timing_parts)}")

    print("\n=== Summary ===")
    print(f"Videos processed: {len(summary.video_jobs)}")

    print(f"Videos with no audio track: {len(summary.videos_with_no_audio_track)}")
    for path in summary.videos_with_no_audio_track:
        print(f"  - {path}")

    print(f"Unmatched videos (no candidate passed threshold): {len(summary.unmatched_videos)}")
    for path in summary.unmatched_videos:
        print(f"  - {path}")

    print(f"Unmatched pool audio files (matched no video): {len(summary.unmatched_audio_files)}")
    for path in summary.unmatched_audio_files:
        print(f"  - {path}")


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    config = build_config(args)
    summary = run_pipeline(config)

    print_report(summary)

    config.run_summary_path.parent.mkdir(parents=True, exist_ok=True)
    config.run_summary_path.write_text(json.dumps(run_summary_to_dict(summary), indent=2))
    print(f"\nRun summary written to {config.run_summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
