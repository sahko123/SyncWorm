# SyncWorm Benchmarks

A running log of dry-run timings against a real multi-day shoot dataset, kept so
future performance work (e.g. the v2 timestamp-based pool narrowing described in
`docs/SyncWorm_Plan.md`) has a before/after baseline instead of a vague "it feels
faster" impression.

## How to reproduce

Each `VideoJob` records `extraction_seconds` and `search_seconds` automatically
(see `syncworm/pipeline.py`), logged at INFO level and included in the
`RunSummary` JSON. To reproduce a run:

```
python -m syncworm <input_dir> --output-dir <dir> --dry-run -v
```

`--dry-run` is enough — extraction and search (the two costly stages) run
regardless of `dry_run`; only trim/bake are skipped. Sum `extraction_seconds`
and `search_seconds` across `video_jobs` in the output JSON (or grep the `-v`
log for `extraction took` / `search took`) to get run totals.

## Dataset used

10 real-world 4K camera clips + 22 DJI wireless mic recordings from a multi-day
shoot (2026-06-07 through 2026-06-10). The mic auto-splits into sequential
files on a size/time limit, so several videos have multiple candidate chunks
from the same continuous recording session in the pool. Total input: ~307GB
video, ~4.5GB audio. Config used default `correlation_sample_rate` (16000) and
`confidence_threshold` (0.3).

## Environment

- CPU: AMD Ryzen 7 3700X (8-core)
- RAM: 32GB
- OS: Windows 11
- Python 3.13.14, ffmpeg 2026-07-13 build

## Results log

### 2026-07-16 — commit `ad9924d` (baseline, full unbounded pool search)

Totals across 10 videos × 22 candidates each (220 correlation pairs):

| Stage | Total | Share |
|---|---|---|
| Extraction | 104.1s | 3% |
| Search (correlation) | 3239.7s | 97% |
| **Run total** | **3343.8s (~55.7 min)** | |

**Headline finding: correlation dominates, not extraction.** Extraction time
tracks roughly with file I/O (demux only, no video decode), while search time
tracks with scratch-track *duration* (resampled-to-16kHz signal length), not
file size — e.g. the 107.6GB/151min video and the 3.1GB/156min video took
comparable search time (556.8s vs 546.6s) despite a 30x difference in file
size. This is the expected cost center for v1's full-pool, no-narrowing
design, and is exactly what v2's timestamp-based pool narrowing (plan
"Future Goals") is meant to cut down.

Per-video breakdown:

| Video | Duration | Size | Extraction | Search (22 candidates) |
|---|---:|---:|---:|---:|
| `2026_06_07/2026-06-07 19-43-58_..._205932.mkv` | 75.5 min | 1.0 GB | 5.0s | 392.9s |
| `2026_06_07/C0001_..._210119.mkv` | 75.7 min | 40.7 GB | 40.8s | 478.2s |
| `2026_06_07/C0002_..._170710.mkv` | 11.4 min | 6.1 GB | 6.4s | 114.8s |
| `2026_06_07/C0002_..._235140.MP4` | 105.0 min | 74.3 GB | 11.7s | 418.3s |
| `2026_06_08/2026-06-07 22-05-01_..._004117.mkv` | 156.3 min | 3.1 GB | 8.5s | 546.6s |
| `2026_06_08/C0001_..._020521.MP4` | 1.1 min | 0.8 GB | 0.2s | 64.4s |
| `2026_06_08/C0001_..._164411.MP4` | 151.2 min | 107.6 GB | 17.3s | 556.8s |
| `2026_06_08/C0002_..._222747.MP4` | 28.2 min | 19.9 GB | 3.0s | 160.9s |
| `2026_06_09/C0001_..._000654.MP4` | 96.6 min | 68.3 GB | 10.9s | 420.5s |
| `2026_06_10/C0001_..._022934.MP4` | 1.7 min | 1.2 GB | 0.3s | 86.3s |

Match outcome: 3/10 videos matched (7 unmatched), 4/22 audio files matched
(18 unmatched) — expected, since the mic pool spans far more continuous
recording time than these particular clips cover.

<!--
Add new entries above this line, newest first, in the same format:
### YYYY-MM-DD — commit `<hash>` (<one-line description of what changed>)
-->
