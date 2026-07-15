# SyncWorm — Audio Sync & Bake Tool: Implementation Plan

## Overview

SyncWorm is a Python tool that searches a pool of external audio recordings (mono or stereo, from field recorders / mics) to find which ones sync to a given video via FFT cross-correlation, then bakes the matched, synced audio onto that video as new track(s) — non-destructively, with the original camera scratch audio preserved. It supports multiple mic sources matching a single video.

**Original files (both video and audio pool files) are never modified or overwritten.** Every operation reads from the originals and writes new output files; nothing in the pipeline touches source data in place.

This is **Stage 1 scope only**: pool search against a video's scratch track, generalized to N matched audio sources per video, with a config-driven bake step. No trimming, multi-file library sorting, crossover detection, or drift correction — those are v2+ (see Future Goals below).

## Goals

1. Take one or more videos, each with camera scratch audio — the video is the anchor / search key.
2. Take a **pool** of candidate external audio files (mono or stereo — e.g. boom, lav1, lav2, recorder backup), not pre-assigned to any specific video.
3. For each video, search the audio pool: correlate the video's scratch track against every candidate audio file to find which ones actually match, with time offset + confidence per candidate.
4. Any candidate that passes the confidence threshold is treated as a valid synced source for that video — this naturally handles multiple mics matching one video without the user manually pairing them.
5. Trim each matched audio source to the video's duration at the correct offset (required for baking — not a user-facing trim feature, just fitting audio to the existing video length).
6. Bake all matched, synced sources onto the video as additional tracks, alongside the preserved original scratch track — written to a **new output file**, never overwriting or modifying the original video or any pool audio file.
7. Track and report which videos had no matching audio (no candidate passed threshold), and which pool audio files were never matched to any video — both are first-class outcomes, not just discarded search noise. The full `RunSummary` (matches, unmatched videos, unmatched audio, no-audio-track videos) is saved to a **JSON file** at the end of each run, not just printed to console.
8. Detect videos that have **no embedded audio track at all** (as distinct from having a scratch track that just failed to match anything) before attempting any search, flag them, and skip straight past — no extraction, no correlation attempted, since there's nothing to correlate against.
9. Support a `--dry-run` mode: run the full pool search and validation, produce the `RunSummary`/JSON report, but skip trimming and baking entirely — no output media files written. Lets you sanity-check matches and tune `confidence_threshold` before committing to a full write run.
10. All of the above driven by a config object/file — no hardcoded behavior.

## Non-Goals (v1)

- Automatically matching unknown audio files to unknown videos across a whole library (Stage 2/3 — future work).
- Crossover/gap detection across multiple takes.
- Clock-drift correction over long takes.
- **Any user-facing trimming (video-to-audio or audio-to-video extents)** — v1 only performs the minimal audio slicing required to fit a matched source into the video's existing duration for baking; no video file is ever shortened in v1. Full trim toggle deferred to v2.
- Any GUI (CLI/library first; DITz-style Qt UI can come later, matching the existing DITz pattern).

## Pipeline Stages

### 1. Input

- A **video input directory**, scanned **recursively** for video files — no need to pass individual video paths; drop a folder (with subfolders, e.g. per-day or per-scene structure) and every video found anywhere beneath it is queued as a job.
- A **pool** of candidate external audio files (mono or stereo), also given as a directory and scanned recursively — e.g. a folder containing boom, lav1, lav2, recorder backup takes from the session, potentially organized into subfolders. These are not pre-paired to any video; the pool can be shared across many videos from the same shoot/session.
- Each video is processed independently. For each video, every file found in the audio pool (at any depth) is treated as a candidate and searched/correlated (see Step 4) — the tool determines which candidates actually belong to that video, rather than the user specifying it upfront.

### 2. Pre-Check: Audio Track Presence

- Before any extraction or correlation is attempted, probe the video for the presence of at least one audio stream (e.g. via `ffprobe`).
- If the video has **no audio track at all**, it's a distinct outcome from "no match found" — flag it immediately (e.g. into a `videos_with_no_audio_track` list) and skip it entirely: no extraction, no pool search, no correlation calls made for that file. This is a cheap early exit, not a failed search.
- If the video has **more than one audio stream** (e.g. internal mic + external XLR input), which one is treated as the scratch track for correlation is configurable per run via `scratch_track_index` — not auto-detected in v1. If the configured index doesn't exist on a given video (e.g. index 1 requested but only one stream present), fall back to index 0 and note the fallback in that video's log entry rather than failing the job.
- Only videos that pass this check proceed to Step 3 (extraction).

### 3. Audio Extraction & Normalization (for correlation only)

- Extract the scratch audio track (per `scratch_track_index`) from video via ffmpeg.
- Downmix any stereo signal (scratch or external source) to mono for correlation purposes only — this never touches the final baked audio, only the comparison signal.
- Downsample both signals to a common low rate (e.g. 8–16kHz) to keep FFT cost low.
- Mean-center / normalize amplitude on both signals before correlating.

### 4. Search / Correlation Against the Pool

- For the given video's scratch track, iterate over **every** file currently in the audio pool as a candidate — this is the "search" step, since the tool doesn't know in advance which pool files belong to this video.
- For each (video, candidate) pair: run FFT-based cross-correlation (`scipy.signal.correlate`, method='fft') of the candidate audio against the video scratch audio — unbounded, full-range search, no window assumption.
- Find peak lag → convert to time offset in seconds.
- Compute confidence score (e.g. peak magnitude relative to correlation stddev, or peak vs. second-highest peak).
- Every candidate gets its own independent offset + confidence score — no shared/collapsed offset across candidates, since matched sources may have slightly different offsets (different physical mic position, different recorder clock), and non-matching candidates should simply score low rather than distort a shared result.
- **A pool audio file that already matched one video remains eligible to match other videos in the same run — this is default v1 behavior, not gated behind any "already used" flag.** This is what makes multi-cam / shared-source setups (one continuous recorder file covering several cameras or a camera + screen recording) work without extra configuration. The tradeoff is a false-positive shared match wouldn't be specially flagged in v1 — if that becomes an issue in practice, add a review flag in v2 rather than restricting sharing now.
- Candidates whose scratch-track overlap can be cheaply ruled out early (e.g. wildly different duration with no plausible overlap window) can optionally be skipped before running the full correlation, as a performance optimization once the basic search works — not required for v1 correctness.

### 5. Validation

- Compare each candidate's confidence score against `confidence_threshold`.
- Candidates below threshold are treated as **non-matches** for that video and discarded (this is the expected outcome for most of the pool — only a handful of files should match any given video).
- Candidates above threshold become that video's matched sources, carried forward into trimming/bake.
- Log/report full search results per video (every candidate + score, not just the winners) so you can sanity-check near-miss cases or a threshold that's too strict/loose.
- **Across the whole run**, track two outcome lists in addition to per-video results:
  - Videos with zero matched sources (no candidate in the pool passed threshold) — these still get reported, just skip trimming/bake.
  - Pool audio files that never matched *any* video across the entire batch — surfaces recordings that may be misnamed, corrupted, from an unrelated session, or simply have no corresponding video (e.g. a room-tone or ambient take).
- These two lists are a required part of the run's final report, not just debug logging — the point is you can look at one summary and immediately see what still needs manual attention.

### 6. Trim Audio to Match Video

- For each validated (audio source, video) pair, slice the audio source starting at its computed offset, running for the video's duration.
- This produces one "synced audio segment" per source, per video.

### 7. Channel Handling (bake-time only)

Applied per config, independent of correlation logic:

- `mono` — bake as extracted/original channel count (no forced conversion).
- `dual_mono` — duplicate mono signal to L/R.
- `passthrough` — preserve source's original channel layout unmodified.

### 8. Bake (Remux)

**Output is always a new file.** Originals — the source video and every pool audio file, matched or not — are opened read-only throughout the pipeline and are never overwritten, renamed, or modified in place.

**Output directory structure mirrors the input.** If a video is found at `video_input_dir/DayOne/CamA/clip001.mp4`, its baked output lands at `output_dir/DayOne/CamA/clip001<suffix>.mp4` (or similar) — same relative subfolder path, just rooted under `output_dir` instead of `video_input_dir`. This keeps a large recursive shoot structure navigable after processing rather than dumping everything into one flat folder.

Track layout (generalized to N sources):

- Track 0: original video stream, untouched.
- Track 1: original camera scratch audio, kept, flagged disabled/secondary by default (never destroyed).
- Track 2..N: each validated synced audio source, trimmed, labeled by source name (e.g. "Synced — Boom", "Synced — Lav1").
- Default/active audio track chosen by: highest confidence score, or a configured priority order list (e.g. `["lav1", "boom", "recorder"]`) with fallback to next-available if a preferred source failed validation.
- Container-level remux only — no video re-encode.
- Track labels/names baked into container metadata for clarity in NLEs.

## Config Schema (v1)

```
video_input_dir: str                 # folder scanned recursively for video files to process as jobs
audio_pool_dir: str                  # folder of candidate audio files, scanned recursively, searched per video
scratch_track_index: int             # default 0 — which embedded audio stream to use as scratch when a video has more than one; falls back to 0 with a logged note if the index doesn't exist on a given video
confidence_threshold: float          # e.g. 0.3 — below this, candidate is treated as non-match
keep_original_audio_track: bool      # default true
audio_channel_mode: enum             # "mono" | "dual_mono" | "passthrough"
source_priority: list[str] | null    # optional ordered list of source names for default-track selection
correlation_sample_rate: int         # default e.g. 16000
skip_implausible_candidates: bool    # default false — cheap pre-filter before full correlation (perf optimization)
output_naming: str/template          # naming convention for new files — must never resolve to the original filepath (open item, TBD)
output_dir: str                      # root output directory; output files mirror video_input_dir's subfolder structure beneath it
run_summary_path: str                # path to write the RunSummary JSON report (e.g. defaults to output_dir/syncworm_run_summary.json)
dry_run: bool                        # default false — if true, run full search/validation and produce the RunSummary/report, but skip trimming and baking entirely (no output media files written)
```

## Data Structures (suggested)

```
AudioCandidate:
  name: str
  filepath: str
  channels: int (detected)
  duration_seconds: float (detected)

CorrelationResult:
  candidate_name: str
  video_filepath: str
  offset_seconds: float
  confidence_score: float
  matched: bool               # true if confidence_score >= threshold

VideoJob:
  video_filepath: str
  search_results: list[CorrelationResult]   # every candidate tried, for full visibility
  matched_sources: list[CorrelationResult]  # subset where matched == true
  chosen_default_track: str | null

RunSummary:
  video_jobs: list[VideoJob]
  unmatched_videos: list[str]           # video filepaths with zero matched_sources (search ran, nothing passed threshold)
  unmatched_audio_files: list[str]      # pool filepaths never matched to any video in this run
  videos_with_no_audio_track: list[str] # video filepaths skipped before any search — no audio stream present at all
```

## Module Breakdown (suggested for Claude Code implementation)

1. `extraction.py` — ffmpeg/ffprobe wrappers: probe for audio-stream presence (used for the no-audio-track pre-check before anything else runs), pull audio track from video, probe channel count/duration/sample rate.
2. `pool.py` — recursively scans `audio_pool_dir` for candidate audio files by extension, builds the list of `AudioCandidate` objects, handles the optional cheap pre-filter (`skip_implausible_candidates`).
3. `video_scanner.py` — recursively scans `video_input_dir` for video files by extension, builds the list of video jobs to process.
4. `correlator.py` — core FFT cross-correlation logic, mono downmix, resampling, offset + confidence scoring. This is the unit to test most rigorously in isolation (known offset test fixtures).
5. `search.py` — for a given video, runs the correlator against every pool candidate, collects all `CorrelationResult`s, applies threshold to produce `matched_sources`. This is the new "search" orchestration layer sitting between the raw correlator and the rest of the pipeline.
6. `trimmer.py` — audio slicing to fit video duration given offset (v1 scope only). Video trimming and reverse audio-to-video trimming are v2 features (see Future Goals) and should not be implemented here yet.
7. `channel_handler.py` — mono / dual_mono / passthrough conversion at bake time only.
8. `bake.py` — ffmpeg remux logic: track assembly, labeling, default-track flag, disabled/secondary flag for scratch track.
9. `config.py` — config schema, loading/validation (e.g. via dataclass or pydantic), sensible defaults.
10. `pipeline.py` — orchestrates the above per `VideoJob`: pre-check → extract scratch → search pool → (if not `dry_run`: trim matches → bake). Aggregates results across multiple videos into a `RunSummary`, computing `unmatched_videos`, `unmatched_audio_files`, and `videos_with_no_audio_track` once all jobs are processed, regardless of `dry_run`.
11. `cli.py` — entry point: accept `video_input_dir` + `audio_pool_dir` (both scanned recursively) + config + `--dry-run` flag, run pipeline, report full search results (matches and near-misses) per video, and write the `RunSummary` (unmatched videos, unmatched audio, no-audio-track videos) to a JSON file at `run_summary_path` at the end of the run, in addition to console output.

## Testing Considerations

- Synthetic test fixtures: generate a known audio signal, offset a copy by a known amount, verify correlator recovers that offset within tolerance.
- Test confidence scoring against a clearly unrelated audio pair (expect low score / reject).
- Test mono/stereo mixed-input correlation (stereo scratch + mono external source) to confirm downmix path doesn't affect offset accuracy.
- Test multi-source-per-video case: one source passes threshold, one fails — confirm video still bakes with only the passing source, no crash.
- Test pool search with a pool containing several clearly unrelated audio files plus 1-2 real matches — confirm only the real matches pass threshold and unrelated files are correctly discarded, not weakly matched.
- Test unmatched tracking: run a batch where one video has no valid match and one pool file matches nothing — confirm both show up correctly in `RunSummary.unmatched_videos` / `unmatched_audio_files`, and that the unmatched video is skipped (no crash) while the rest of the batch completes.
- Test no-audio-track handling: include a silent/audio-less video in a batch — confirm it lands in `videos_with_no_audio_track` (not `unmatched_videos`), that no extraction or correlation calls are made for it (verify via logging/mocking, not just the end result), and the rest of the batch proceeds normally.
- Test shared-source matching: run two videos against a pool where one audio file legitimately matches both (e.g. simulate a multi-cam/screen-recording scenario) — confirm both videos independently list it in `matched_sources` with their own correctly computed offsets, and neither is blocked from matching by the other's prior match.
- Test `scratch_track_index` fallback: configure an index that doesn't exist on a given video's audio streams — confirm it falls back to index 0 and logs the fallback rather than failing the job.
- Test `dry_run`: run a batch with `dry_run: true` — confirm the `RunSummary`/JSON report is produced with correct matches, but no output media files are written anywhere under `output_dir`.
- Test bake output in at least one NLE (track labels visible, scratch track present but disabled, correct default track playing).

## Open Items / Decisions Still Needed

- `output_naming` convention — new files vs. overwrite vs. suffix pattern. **Hard constraint: whatever convention is chosen must never write to the original video or original pool audio filepath** — e.g. a dedicated output directory, or a suffix like `_synced`, with a safety check that refuses to proceed if the resolved output path matches any input path.
- Which file extensions count as "video" and "audio" during recursive scanning of `video_input_dir` and `audio_pool_dir` (e.g. video: `.mp4`, `.mov`, `.mxf`; audio: `.wav`, `.mp3`) — needs a concrete allowlist so the scanners don't choke on non-media files sitting in the same folder structure.
- Whether correlation should run in parallel across (candidate, video) pairs for larger batches (not a bottleneck per earlier discussion, but worth deciding as a config/CLI flag: `--parallel`).
- Since the same audio pool is searched against every video in a batch, whether to cache extracted/normalized/resampled candidate audio in memory (or on disk) across the whole run rather than re-processing each pool file once per video — likely worth doing once there's more than a handful of videos, since it's a straightforward win with no correctness tradeoff.

## Future Goals (v2 — after basic search/sync/bake is working)

These are explicitly deferred until v1 (pool search + trim + bake) is solid and tested. Listed here so the v1 architecture doesn't accidentally foreclose them.

### Timestamp-based pool narrowing

- All source files (video and audio) are dated/timestamped. Once the pool grows large, searching every candidate against every video is wasteful — narrow the search order using timestamps instead of scanning the whole pool blind.
- **Search order:** for a given video's timestamp, sort pool candidates by absolute time distance from that timestamp (nearest first, direction doesn't matter — a candidate slightly before or slightly after is equally valid).
- **Search strategy:** try the nearest candidate first. If it matches (passes `confidence_threshold`), stop expanding outward for that source slot — but keep in mind multiple candidates may still match the same video (see "shared sources" below), so this stops the *search radius*, not necessarily the whole search.
- If the nearest doesn't match, try the next-nearest, and keep expanding outward until either a match is found or a reasonable search radius/candidate-count limit is exhausted.
- **No-match outcome:** if no candidate within the search radius matches, stop searching for that video, flag it clearly in output/report as "no syncable audio found," and move on to the next video rather than blocking the batch.
- This narrowing is a performance/scaling optimization layered on top of the v1 search logic, not a replacement for it — the underlying correlator and threshold logic stay the same, only the order and quantity of candidates tried per video changes.
- Config additions to consider: `use_timestamp_narrowing: bool`, `initial_search_radius` (e.g. number of nearest candidates to try before giving up or before falling back to a full pool scan), `require_timestamp_metadata: bool` (behavior if a file lacks a reliable timestamp).

### Shared audio sources across multiple videos — confirmed v1 behavior

- A single audio file may legitimately match more than one video — e.g. one continuous recorder take covering both a camera and a simultaneous screen recording, or multiple cameras in a multi-cam setup all capturing the same audio.
- **This is already supported in v1** (see Step 4/Search) — sharing is allowed by default, not deferred. Left here as a note rather than removed, since v2's timestamp-narrowing feature needs to be aware that stopping the search radius early for one video must not prevent that same candidate from being found by another video's independent search.

### Trimming (new in v2 — none exists in v1)

- v1 deliberately ships with **no trimming feature at all** — the only length adjustment in v1 is the mandatory audio slicing needed to fit a matched source into the video's existing duration for baking (Step 6), which is not user-facing or toggleable.
- v2 introduces an actual opt-in trim toggle, directional and configurable:
  - **Trim video to audio extents** — cut the video down to the coverage window where matched audio exists.
  - **Trim audio to video extents** — trim a matched audio source down to exactly the video's start/end rather than leaving excess overhang (distinct from Step 6's mandatory slicing, since this is user-opted rather than baseline behavior).
- Suggested config shape: `trim_mode: enum` — `"none" | "video_to_audio" | "audio_to_video" | "both"`, defaulting to `"none"` to match v1 behavior when this ships.

### CLI + GUI architecture

- The CLI is the core, canonical tool — all pipeline logic (pool scanning, search, correlation, trimming, bake) lives in the library/CLI layer with no GUI dependency.
- The GUI is a thin skin on top of that same core library — it should call into the same `pipeline.py` orchestration rather than duplicating any logic, mirroring the existing DITz pattern (Python/Qt) so the two tools can eventually share infrastructure or at least conventions.
- Practical implication for v1: keep `pipeline.py`'s public functions GUI-agnostic (plain Python calls returning structured results like `VideoJob`/`CorrelationResult`, not print statements or CLI-specific I/O), so wiring a Qt frontend later is just calling those same functions and rendering the results — no refactor of core logic needed at that point.

## Notes for Claude Code

- Python + numpy/scipy for correlation math (compiled C/Fortran under the hood — not the bottleneck).
- ffmpeg via subprocess or `ffmpeg-python` for extraction/remuxing — no video re-encode needed at any stage.
- **Never write to, overwrite, or modify an original input file (video or pool audio) at any pipeline stage.** All ffmpeg calls that produce output should target a new path in an output directory; treat any input path also being a computed output path as a bug to fail loudly on, not silently proceed.
- Keep this as a standalone library/CLI first (consistent with SyncWorm being a spinout from DITz); a Qt UI can wrap it later the same way DITz already does.

## Repository Setup

Claude Code should handle this as part of implementation, not just the code itself:

- Initialize a git repository named **SyncWorm** with the project structure described above (`syncworm/` module package, `tests/`, `docs/` containing this plan file).
- Default branch: `main`.
- Include a `.gitignore` covering standard Python artifacts (`__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `*.egg-info/`, `.pytest_cache/`, `.DS_Store`) plus run-time output paths (`/output/`, `syncworm_run_summary.json`) so generated media/reports never get committed.
- Include a `README.md` summarizing the tool (purpose, core v1 principles — video-as-search-key, non-destructive originals, no trimming in v1, shared sources allowed, unmatched tracking, `--dry-run`) and the project layout, linking to `docs/SyncWorm_Plan.md` for full detail.
- Include `requirements.txt` (numpy, scipy, ffmpeg-python, pydantic or equivalent for config validation).
- Commit the initial scaffold with a clear message before starting on actual pipeline logic, so the empty/stub structure is its own reviewable checkpoint.
- **Create a GitHub remote named `SyncWorm` and push `main` to it.** If Claude Code has GitHub access configured (e.g. `gh` CLI authenticated, or a connected GitHub integration), create the repository and push directly. If no GitHub credentials/access are available in the environment, stop and clearly tell the user what's needed (auth method, or the exact `git remote add` / `git push` commands to run manually) rather than silently skipping this step.
