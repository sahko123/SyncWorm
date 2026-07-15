"""mono / dual_mono / passthrough channel conversion — applied at bake time only.

Independent of correlation logic: this runs on the already-trimmed audio
segment, never on the signal used for correlation.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.io import wavfile

from syncworm.config import AudioChannelMode


def apply_channel_mode(
    input_path: str | Path,
    output_path: str | Path,
    mode: AudioChannelMode,
) -> Path:
    """Apply the configured channel-handling mode to a (trimmed) audio file.

    - mono / passthrough: no forced conversion — output exactly as extracted,
      original channel layout preserved unmodified.
    - dual_mono: duplicate a mono signal to L/R stereo. A non-mono source is
      downmixed to mono first, so the output is always exactly 2 identical
      channels.
    """
    sample_rate, data = wavfile.read(str(input_path))

    if mode == AudioChannelMode.DUAL_MONO:
        if data.ndim == 1:
            mono = data
        else:
            mono = np.clip(np.round(data.mean(axis=1)), -32768, 32767).astype(data.dtype)
        data = np.column_stack([mono, mono])

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(str(output_path), sample_rate, data)
    return output_path
