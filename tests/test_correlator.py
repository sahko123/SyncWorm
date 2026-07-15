import numpy as np
import pytest
from scipy.io import wavfile

from syncworm.correlator import correlate, load_mono_signal

SAMPLE_RATE = 16000


def _broadband_signal(duration_seconds: float, seed: int) -> np.ndarray:
    """A noise-like signal with enough structure to correlate sharply, deterministic per seed."""
    rng = np.random.default_rng(seed)
    n = int(duration_seconds * SAMPLE_RATE)
    return rng.normal(0, 1, n)


def _write_wav(path, samples: np.ndarray, sample_rate: int = SAMPLE_RATE, channels: int = 1):
    data = np.clip(samples, -1.0, 1.0) * 32767
    data = data.astype(np.int16)
    if channels == 2:
        data = np.column_stack([data, data])
    wavfile.write(str(path), sample_rate, data)


def test_correlate_recovers_known_positive_offset(tmp_path):
    base = _broadband_signal(6.0, seed=1)
    shift_seconds = 1.5
    shift_samples = int(shift_seconds * SAMPLE_RATE)

    scratch = base[shift_samples:]  # video's scratch track: the "later" portion
    candidate = base  # candidate has shift_samples of extra lead-in before matching scratch

    scratch_path = tmp_path / "scratch.wav"
    candidate_path = tmp_path / "candidate.wav"
    _write_wav(scratch_path, scratch)
    _write_wav(candidate_path, candidate)

    outcome = correlate(scratch_path, candidate_path, sample_rate=SAMPLE_RATE)

    assert outcome.offset_seconds == pytest.approx(shift_seconds, abs=0.01)
    assert outcome.confidence_score > 10


def test_correlate_recovers_known_negative_offset(tmp_path):
    base = _broadband_signal(6.0, seed=2)
    shift_seconds = 1.0
    shift_samples = int(shift_seconds * SAMPLE_RATE)

    # candidate is the "later" portion — it started recording *after* the video
    candidate = base[shift_samples:]
    scratch = base

    scratch_path = tmp_path / "scratch.wav"
    candidate_path = tmp_path / "candidate.wav"
    _write_wav(scratch_path, scratch)
    _write_wav(candidate_path, candidate)

    outcome = correlate(scratch_path, candidate_path, sample_rate=SAMPLE_RATE)

    assert outcome.offset_seconds == pytest.approx(-shift_seconds, abs=0.01)


def test_confidence_low_for_unrelated_audio(tmp_path):
    matched_base = _broadband_signal(6.0, seed=3)
    shift_samples = int(1.0 * SAMPLE_RATE)
    matched_scratch = matched_base[shift_samples:]
    matched_candidate = matched_base

    unrelated_scratch = _broadband_signal(6.0, seed=10)
    unrelated_candidate = _broadband_signal(6.0, seed=20)

    matched_scratch_path = tmp_path / "m_scratch.wav"
    matched_candidate_path = tmp_path / "m_candidate.wav"
    unrelated_scratch_path = tmp_path / "u_scratch.wav"
    unrelated_candidate_path = tmp_path / "u_candidate.wav"
    _write_wav(matched_scratch_path, matched_scratch)
    _write_wav(matched_candidate_path, matched_candidate)
    _write_wav(unrelated_scratch_path, unrelated_scratch)
    _write_wav(unrelated_candidate_path, unrelated_candidate)

    matched = correlate(matched_scratch_path, matched_candidate_path, sample_rate=SAMPLE_RATE)
    unrelated = correlate(unrelated_scratch_path, unrelated_candidate_path, sample_rate=SAMPLE_RATE)

    assert matched.confidence_score > unrelated.confidence_score * 3


def test_stereo_candidate_downmix_does_not_affect_offset_accuracy(tmp_path):
    base = _broadband_signal(6.0, seed=4)
    shift_seconds = 0.75
    shift_samples = int(shift_seconds * SAMPLE_RATE)

    scratch = base[shift_samples:]
    candidate = base

    scratch_path = tmp_path / "scratch.wav"
    candidate_mono_path = tmp_path / "candidate_mono.wav"
    candidate_stereo_path = tmp_path / "candidate_stereo.wav"
    _write_wav(scratch_path, scratch, channels=1)
    _write_wav(candidate_mono_path, candidate, channels=1)
    _write_wav(candidate_stereo_path, candidate, channels=2)

    mono_outcome = correlate(scratch_path, candidate_mono_path, sample_rate=SAMPLE_RATE)
    stereo_outcome = correlate(scratch_path, candidate_stereo_path, sample_rate=SAMPLE_RATE)

    assert stereo_outcome.offset_seconds == pytest.approx(mono_outcome.offset_seconds, abs=0.01)
    assert stereo_outcome.offset_seconds == pytest.approx(shift_seconds, abs=0.01)


def test_load_mono_signal_is_mean_centered(tmp_path):
    base = _broadband_signal(2.0, seed=5) + 0.5  # DC offset
    path = tmp_path / "offset.wav"
    _write_wav(path, np.clip(base, -1, 1))

    loaded = load_mono_signal(path, SAMPLE_RATE)

    assert loaded.mean() == pytest.approx(0.0, abs=1.0)
