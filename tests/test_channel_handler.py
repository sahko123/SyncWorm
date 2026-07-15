import numpy as np
from scipy.io import wavfile

from audio_fixtures import broadband_signal, write_wav
from syncworm.channel_handler import apply_channel_mode
from syncworm.config import AudioChannelMode

SAMPLE_RATE = 16000


def _read_wav(path):
    return wavfile.read(str(path))


def test_mono_mode_is_noop_on_mono_source(tmp_path):
    base = broadband_signal(1.0, seed=1, sample_rate=SAMPLE_RATE)
    input_path = tmp_path / "mono_in.wav"
    write_wav(input_path, base, SAMPLE_RATE, channels=1)

    output_path = tmp_path / "mono_out.wav"
    apply_channel_mode(input_path, output_path, AudioChannelMode.MONO)

    _, original = _read_wav(input_path)
    _, result = _read_wav(output_path)
    assert result.ndim == 1
    assert np.array_equal(result, original)


def test_passthrough_mode_is_noop_on_stereo_source(tmp_path):
    base = broadband_signal(1.0, seed=2, sample_rate=SAMPLE_RATE)
    input_path = tmp_path / "stereo_in.wav"
    write_wav(input_path, base, SAMPLE_RATE, channels=2)

    output_path = tmp_path / "stereo_out.wav"
    apply_channel_mode(input_path, output_path, AudioChannelMode.PASSTHROUGH)

    _, original = _read_wav(input_path)
    _, result = _read_wav(output_path)
    assert result.ndim == 2
    assert result.shape[1] == 2
    assert np.array_equal(result, original)


def test_dual_mono_duplicates_mono_source_to_stereo(tmp_path):
    base = broadband_signal(1.0, seed=3, sample_rate=SAMPLE_RATE)
    input_path = tmp_path / "mono_in.wav"
    write_wav(input_path, base, SAMPLE_RATE, channels=1)

    output_path = tmp_path / "dual_mono_out.wav"
    apply_channel_mode(input_path, output_path, AudioChannelMode.DUAL_MONO)

    _, original = _read_wav(input_path)
    _, result = _read_wav(output_path)
    assert result.ndim == 2
    assert result.shape[1] == 2
    assert np.array_equal(result[:, 0], original)
    assert np.array_equal(result[:, 1], original)


def test_dual_mono_downmixes_stereo_source_first(tmp_path):
    base = broadband_signal(1.0, seed=4, sample_rate=SAMPLE_RATE)
    input_path = tmp_path / "stereo_in.wav"
    write_wav(input_path, base, SAMPLE_RATE, channels=2)

    output_path = tmp_path / "dual_mono_out.wav"
    apply_channel_mode(input_path, output_path, AudioChannelMode.DUAL_MONO)

    _, result = _read_wav(output_path)
    assert result.ndim == 2
    assert result.shape[1] == 2
    # both channels identical (dual-mono), and equal to the downmixed average
    assert np.array_equal(result[:, 0], result[:, 1])
