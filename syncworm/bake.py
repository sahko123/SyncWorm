"""ffmpeg remux: track assembly, labeling, default-track flag, output dir mirroring.

Container-level remux only — the video stream is always copied, never
re-encoded. Output always goes to a new path; the original video and every
pool audio file are opened read-only.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from syncworm.models import BakeSource


class BakeError(RuntimeError):
    """Raised when ffmpeg fails to remux the output video, or an output path is unsafe."""


def mirrored_output_path(
    video_path: str | Path,
    video_input_dir: str | Path,
    output_dir: str | Path,
    output_naming: str,
) -> Path:
    """Compute a video's output path, mirroring its subfolder path under output_dir.

    e.g. video_input_dir/DayOne/CamA/clip001.mp4 -> output_dir/DayOne/CamA/<naming>.
    Refuses to resolve to the original input path.
    """
    video_path = Path(video_path)
    video_input_dir = Path(video_input_dir)
    output_dir = Path(output_dir)

    try:
        relative = video_path.resolve().relative_to(video_input_dir.resolve())
    except ValueError as exc:
        raise BakeError(f"{video_path} is not inside video_input_dir {video_input_dir}") from exc

    new_name = output_naming.format(stem=video_path.stem, suffix=video_path.suffix)
    output_path = output_dir / relative.parent / new_name

    if output_path.resolve() == video_path.resolve():
        raise BakeError(
            f"Refusing to bake: resolved output path {output_path.resolve()} matches the "
            f"original input video path"
        )
    return output_path


def choose_default_source(
    sources: list[BakeSource], source_priority: list[str] | None
) -> BakeSource | None:
    """Pick the default/active audio track: priority list first, else highest confidence.

    Falls back to next-available in the priority list if a preferred source
    isn't among the validated sources (e.g. it failed to match).
    """
    if not sources:
        return None
    if source_priority:
        by_name = {s.name: s for s in sources}
        for name in source_priority:
            if name in by_name:
                return by_name[name]
    return max(sources, key=lambda s: s.confidence_score)


def bake(
    video_path: str | Path,
    output_path: str | Path,
    scratch_track_index: int,
    matched_sources: list[BakeSource],
    keep_original_audio_track: bool = True,
    source_priority: list[str] | None = None,
) -> Path:
    """Remux video + scratch (optional) + matched synced sources into a new output file.

    Track layout: video, then (if kept) original scratch audio flagged
    non-default, then each matched source labeled by name, with the chosen
    default source flagged default.
    """
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    default_source = choose_default_source(matched_sources, source_priority)

    cmd = ["ffmpeg", "-y", "-i", str(video_path)]
    for source in matched_sources:
        cmd += ["-i", str(source.filepath)]

    cmd += ["-map", "0:v:0"]
    if keep_original_audio_track:
        cmd += ["-map", f"0:a:{scratch_track_index}"]
    for i in range(len(matched_sources)):
        cmd += ["-map", f"{i + 1}:a:0"]

    cmd += ["-c:v", "copy"]

    audio_stream_index = 0
    if keep_original_audio_track:
        cmd += [
            f"-c:a:{audio_stream_index}", "copy",
            f"-disposition:a:{audio_stream_index}", "0",
            f"-metadata:s:a:{audio_stream_index}", "title=Scratch (Camera Original)",
        ]
        audio_stream_index += 1

    for source in matched_sources:
        is_default = source == default_source
        cmd += [
            f"-c:a:{audio_stream_index}", "aac",
            f"-disposition:a:{audio_stream_index}", "default" if is_default else "0",
            f"-metadata:s:a:{audio_stream_index}", f"title=Synced - {source.name}",
        ]
        audio_stream_index += 1

    cmd += [str(output_path)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise BakeError(f"ffmpeg failed baking {output_path}: {result.stderr.strip()}")

    return output_path
