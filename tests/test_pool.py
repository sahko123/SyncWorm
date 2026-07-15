from syncworm.pool import scan_audio_pool


def test_scan_finds_audio_files_recursively(make_audio_file, tmp_path):
    pool_dir = tmp_path / "pool"
    make_audio_file(name="pool/boom.wav", duration=1.0)
    make_audio_file(name="pool/subfolder/lav1.wav", duration=1.0)

    candidates = scan_audio_pool(pool_dir)

    names = {c.name for c in candidates}
    assert names == {"boom", "lav1"}
    for c in candidates:
        assert c.duration_seconds > 0
        assert c.channels >= 1


def test_scan_ignores_non_audio_extensions(make_audio_file, tmp_path):
    pool_dir = tmp_path / "pool"
    make_audio_file(name="pool/boom.wav", duration=1.0)
    (pool_dir / "notes.txt").write_text("not audio")

    candidates = scan_audio_pool(pool_dir)

    assert len(candidates) == 1
    assert candidates[0].name == "boom"


def test_scan_skips_corrupt_file_without_crashing(make_audio_file, tmp_path):
    pool_dir = tmp_path / "pool"
    make_audio_file(name="pool/good.wav", duration=1.0)
    bad = pool_dir / "corrupt.wav"
    bad.write_bytes(b"not a real wav file")

    candidates = scan_audio_pool(pool_dir)

    names = {c.name for c in candidates}
    assert names == {"good"}


def test_scan_empty_dir_returns_empty_list(tmp_path):
    pool_dir = tmp_path / "empty_pool"
    pool_dir.mkdir()
    assert scan_audio_pool(pool_dir) == []
