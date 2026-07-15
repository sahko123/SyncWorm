# SyncWorm

SyncWorm is a Python tool that searches a pool of external audio recordings (mono or
stereo, from field recorders / mics) to find which ones sync to a given video via FFT
cross-correlation, then bakes the matched, synced audio onto that video as new track(s)
— non-destructively, with the original camera scratch audio preserved. It supports
multiple mic sources matching a single video.

This is a spinout from DITz, following the same Python/library-first-then-Qt-UI pattern.

## Core v1 principles

- **Video is the search key.** Each video's scratch audio is correlated against every
  file in an audio pool to find which ones match — audio files are not pre-paired to
  videos.
- **Originals are never modified.** Every input (video or pool audio) is opened
  read-only; all output goes to new files under a separate output directory.
- **No trimming in v1.** The only length adjustment is the mandatory slicing needed to
  fit a matched audio source into the video's existing duration for baking. Full
  trim toggles (video-to-audio, audio-to-video) are deferred to v2.
- **Shared sources allowed.** A single audio file can legitimately match more than one
  video in the same run (e.g. a continuous recorder take covering multiple cameras) —
  this is default behavior, not a special case.
- **Unmatched tracking is first-class.** Videos with no matching audio, and pool audio
  files that never matched any video, are both reported in the `RunSummary`, not just
  silently dropped.
- **`--dry-run`.** Run the full pool search and validation, produce the `RunSummary`
  JSON report, but skip trimming/baking — no output media files written.

## Project layout

```
syncworm/       core library — extraction, pool/video scanning, correlation, search,
                trimming, channel handling, baking, config, pipeline orchestration, CLI
tests/          unit + integration tests
docs/           SyncWorm_Plan.md — full implementation plan and design rationale
```

See [`docs/SyncWorm_Plan.md`](docs/SyncWorm_Plan.md) for the complete pipeline design,
config schema, data structures, and testing plan.

## Setup

Requires Python 3.11+ and `ffmpeg`/`ffprobe` on `PATH`.

```
python -m venv .venv
.venv/Scripts/activate        # .venv/bin/activate on macOS/Linux
pip install -r requirements-dev.txt
pytest
```

## Usage

```
python -m syncworm --video-input-dir <dir> --audio-pool-dir <dir> --output-dir <dir>
```

Or via a JSON config file matching the schema in
[`docs/SyncWorm_Plan.md`](docs/SyncWorm_Plan.md#config-schema-v1):

```
python -m syncworm --config config.json
```

CLI flags override values from `--config` when both are given. Add `--dry-run` to
run search/validation and produce the report without writing any output media.

## Status

Under active development — v1 (pool search + trim + bake) scope, per the plan above.
