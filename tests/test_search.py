from pathlib import Path

from audio_fixtures import broadband_signal, write_wav
from syncworm.models import AudioCandidate
from syncworm.search import matched_sources, search_pool

SAMPLE_RATE = 16000
CONFIDENCE_THRESHOLD = 0.3


def _candidate(name: str, path: Path, samples, sample_rate: int = SAMPLE_RATE) -> AudioCandidate:
    write_wav(path, samples, sample_rate)
    return AudioCandidate(
        name=name,
        filepath=path,
        channels=1,
        duration_seconds=len(samples) / sample_rate,
    )


def test_search_pool_flags_real_matches_and_rejects_unrelated(tmp_path):
    video_path = Path("video.mp4")  # search_pool only carries this through, doesn't read it

    base_a = broadband_signal(6.0, seed=100, sample_rate=SAMPLE_RATE)
    scratch = base_a[int(1.0 * SAMPLE_RATE):]
    scratch_path = tmp_path / "scratch.wav"
    write_wav(scratch_path, scratch, SAMPLE_RATE)

    candidates = [
        _candidate("boom", tmp_path / "boom.wav", base_a),  # real match, offset ~1.0s
        _candidate(
            "lav1", tmp_path / "lav1.wav", base_a[int(0.5 * SAMPLE_RATE):]
        ),  # still matches, offset ~0.5s
        _candidate("unrelated1", tmp_path / "unrelated1.wav", broadband_signal(6.0, seed=300, sample_rate=SAMPLE_RATE)),
        _candidate("unrelated2", tmp_path / "unrelated2.wav", broadband_signal(6.0, seed=400, sample_rate=SAMPLE_RATE)),
    ]

    results = search_pool(video_path, scratch_path, candidates, CONFIDENCE_THRESHOLD, sample_rate=SAMPLE_RATE)

    assert len(results) == 4  # every candidate gets a result, winners and near-misses alike
    by_name = {r.candidate_name: r for r in results}

    assert by_name["boom"].matched is True
    assert by_name["lav1"].matched is True
    assert by_name["unrelated1"].matched is False
    assert by_name["unrelated2"].matched is False

    matches = matched_sources(results)
    assert {m.candidate_name for m in matches} == {"boom", "lav1"}

    for result in results:
        assert result.video_filepath == video_path


def test_search_pool_empty_candidates_returns_empty(tmp_path):
    scratch_path = tmp_path / "scratch.wav"
    write_wav(scratch_path, broadband_signal(2.0, seed=1, sample_rate=SAMPLE_RATE), SAMPLE_RATE)

    results = search_pool(Path("video.mp4"), scratch_path, [], CONFIDENCE_THRESHOLD)

    assert results == []
