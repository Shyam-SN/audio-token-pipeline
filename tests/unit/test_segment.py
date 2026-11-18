"""Unit tests for Stage 2 Silero VAD segmentation and per-fixture behavior."""

from pathlib import Path

from audio_token_pipeline.stages.segment import segment_audio_file

FIXTURES_DIR = Path("tests/fixtures")


def test_segment_silence_produces_zero_segments() -> None:
    res = segment_audio_file("silence", str(FIXTURES_DIR / "silence.wav"))
    assert len(res.segments) == 0, f"Expected 0 segments for silence, got {len(res.segments)}"
    assert res.speech_ratio == 0.0


def test_segment_short_clip_produces_zero_segments() -> None:
    # 0.5s audio is under the min_speech_duration_s (2.0s) threshold
    res = segment_audio_file("short_clip", str(FIXTURES_DIR / "short_clip.wav"), min_speech_duration_s=2.0)
    assert len(res.segments) == 0, f"Expected 0 segments for 0.5s short clip, got {len(res.segments)}"


def test_segment_librispeech_speech_ratio() -> None:
    # Official LibriSpeech clean speech clips should yield >= 85% speech ratio
    libri_files = sorted(FIXTURES_DIR.glob("librispeech_2277-149896-*.flac"))
    assert len(libri_files) >= 3, "Missing official LibriSpeech fixtures"

    for l_file in libri_files:
        res = segment_audio_file(l_file.stem, str(l_file))
        assert len(res.segments) >= 1, f"Expected at least 1 speech segment for {l_file.name}"
        assert res.speech_ratio >= 0.85, f"Expected speech ratio >= 0.85 for {l_file.name}, got {res.speech_ratio}"


def test_segment_multirate_and_stereo_consistency() -> None:
    # rate_16k, rate_44k, rate_48k have identical tone synthesis at different sample rates
    res_16 = segment_audio_file("rate_16k", str(FIXTURES_DIR / "rate_16k.wav"))
    res_44 = segment_audio_file("rate_44k", str(FIXTURES_DIR / "rate_44k.wav"))
    res_48 = segment_audio_file("rate_48k", str(FIXTURES_DIR / "rate_48k.wav"))

    assert len(res_16.segments) == len(res_44.segments) == len(res_48.segments)
    if res_16.segments:
        # Check start and end boundaries match within 50 ms
        for s16, s48 in zip(res_16.segments, res_48.segments, strict=False):
            assert abs(s16["start_ms"] - s48["start_ms"]) <= 50
            assert abs(s16["end_ms"] - s48["end_ms"]) <= 50

    # Stereo audio averaged to mono gives consistent behavior
    res_stereo = segment_audio_file("stereo", str(FIXTURES_DIR / "stereo.wav"))
    assert res_stereo.error is None


def test_segment_music_chord_log_result() -> None:
    # Log VAD classification on synthetic polyphonic music chord
    music_file = FIXTURES_DIR / "music_chord.wav"
    if music_file.exists():
        res = segment_audio_file("music_chord", str(music_file))
        print(f"\n[VAD Music Evaluation] segments={len(res.segments)}, speech_ratio={res.speech_ratio}")
        assert res.error is None


def test_run_segment_pipeline(tmp_path: Path) -> None:
    from audio_token_pipeline.catalog import Catalog
    from audio_token_pipeline.config import AppConfig
    from audio_token_pipeline.stages.segment import run_segment

    db_path = tmp_path / "test_segment.duckdb"
    cfg = AppConfig(catalog_path=db_path)
    cat = Catalog(db_path)
    cat.register_source(
        source_id="libri_test",
        filepath=str(FIXTURES_DIR / "librispeech_2277-149896-0000.flac"),
        dataset="test",
        split="fixtures",
        duration_s=14.0,
        sample_rate=16000,
        channels=1,
        sha256="abc",
        status="INGESTED",
    )
    res = run_segment(cfg, num_workers=1)
    assert res["items_in"] == 1
    assert res["segments_out"] >= 1

