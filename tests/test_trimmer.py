import numpy as np
from scipy.io import wavfile

from audio_fixtures import broadband_signal, write_wav
from syncworm.trimmer import trim_to_video_duration

SAMPLE_RATE = 16000


def _read_wav(path):
    sample_rate, data = wavfile.read(str(path))
    return sample_rate, data


def test_positive_offset_trims_lead_in(tmp_path):
    base = broadband_signal(6.0, seed=1, sample_rate=SAMPLE_RATE)
    candidate_path = tmp_path / "candidate.wav"
    write_wav(candidate_path, base, SAMPLE_RATE)

    offset_seconds = 1.0
    video_duration = 3.0
    output_path = tmp_path / "trimmed.wav"

    trim_to_video_duration(candidate_path, output_path, offset_seconds, video_duration)

    sample_rate, data = _read_wav(output_path)
    assert sample_rate == SAMPLE_RATE
    assert len(data) == int(round(video_duration * SAMPLE_RATE))

    start_sample = int(round(offset_seconds * SAMPLE_RATE))
    expected = (np.clip(base, -1, 1) * 32767).astype(np.int16)[start_sample : start_sample + len(data)]
    assert np.array_equal(data, expected)


def test_positive_offset_pads_silence_when_candidate_runs_out(tmp_path):
    base = broadband_signal(2.0, seed=2, sample_rate=SAMPLE_RATE)
    candidate_path = tmp_path / "candidate.wav"
    write_wav(candidate_path, base, SAMPLE_RATE)

    offset_seconds = 1.5  # only 0.5s of real audio remains after trimming lead-in
    video_duration = 3.0
    output_path = tmp_path / "trimmed.wav"

    trim_to_video_duration(candidate_path, output_path, offset_seconds, video_duration)

    sample_rate, data = _read_wav(output_path)
    target_len = int(round(video_duration * SAMPLE_RATE))
    assert len(data) == target_len

    real_audio_len = len(base) - int(round(offset_seconds * SAMPLE_RATE))
    tail_silence = data[real_audio_len:]
    assert np.all(tail_silence == 0)


def test_negative_offset_prepends_silence(tmp_path):
    base = broadband_signal(2.0, seed=3, sample_rate=SAMPLE_RATE)
    candidate_path = tmp_path / "candidate.wav"
    write_wav(candidate_path, base, SAMPLE_RATE)

    offset_seconds = -0.5  # candidate started 0.5s after the video
    video_duration = 2.5
    output_path = tmp_path / "trimmed.wav"

    trim_to_video_duration(candidate_path, output_path, offset_seconds, video_duration)

    sample_rate, data = _read_wav(output_path)
    target_len = int(round(video_duration * SAMPLE_RATE))
    assert len(data) == target_len

    pad_len = int(round(0.5 * SAMPLE_RATE))
    lead_silence = data[:pad_len]
    assert np.all(lead_silence == 0)

    expected_audio = (np.clip(base, -1, 1) * 32767).astype(np.int16)
    assert np.array_equal(data[pad_len : pad_len + len(expected_audio)], expected_audio)


def test_stereo_candidate_preserves_channel_count(tmp_path):
    base = broadband_signal(3.0, seed=4, sample_rate=SAMPLE_RATE)
    candidate_path = tmp_path / "candidate_stereo.wav"
    write_wav(candidate_path, base, SAMPLE_RATE, channels=2)

    output_path = tmp_path / "trimmed_stereo.wav"
    trim_to_video_duration(candidate_path, output_path, 0.0, 2.0)

    sample_rate, data = _read_wav(output_path)
    assert data.ndim == 2
    assert data.shape[1] == 2
    assert data.shape[0] == int(round(2.0 * SAMPLE_RATE))
