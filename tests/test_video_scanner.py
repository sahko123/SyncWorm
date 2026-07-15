from syncworm.video_scanner import scan_video_inputs


def test_scan_finds_videos_recursively(make_video_with_audio, make_video_without_audio, tmp_path):
    video_dir = tmp_path / "videos"
    make_video_with_audio(name="videos/DayOne/CamA/clip001.mp4", duration=1.0)
    make_video_without_audio(name="videos/DayOne/CamB/clip002.mp4", duration=1.0)

    jobs = scan_video_inputs(video_dir)

    filepaths = {job.video_filepath.name for job in jobs}
    assert filepaths == {"clip001.mp4", "clip002.mp4"}
    for job in jobs:
        assert job.search_results == []
        assert job.matched_sources == []
        assert job.chosen_default_track is None


def test_scan_ignores_non_video_files(make_video_with_audio, tmp_path):
    video_dir = tmp_path / "videos"
    make_video_with_audio(name="videos/clip.mp4", duration=1.0)
    (video_dir / "readme.txt").write_text("not a video")

    jobs = scan_video_inputs(video_dir)

    assert len(jobs) == 1
    assert jobs[0].video_filepath.name == "clip.mp4"


def test_scan_empty_dir_returns_empty_list(tmp_path):
    video_dir = tmp_path / "empty_videos"
    video_dir.mkdir()
    assert scan_video_inputs(video_dir) == []
