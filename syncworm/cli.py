"""CLI entry point for SyncWorm."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

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
    parser.add_argument("--video-input-dir", type=Path)
    parser.add_argument("--audio-pool-dir", type=Path)
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

    missing = [f for f in ("video_input_dir", "audio_pool_dir", "output_dir") if f not in base]
    if missing:
        raise SystemExit(
            f"Missing required config field(s): {', '.join(missing)} "
            f"(pass --config, or --video-input-dir/--audio-pool-dir/--output-dir)"
        )

    return SyncWormConfig.model_validate(base)


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
