"""Unit tests for Stage 1 Ingest and EBU R128 loudness metadata computation."""

from pathlib import Path

import numpy as np
import soundfile as sf

from audio_token_pipeline.stages.ingest import compute_audio_loudness_metadata

FIXTURES_DIR = Path("tests/fixtures")


def test_ingest_silent_file_loudness_undefined() -> None:
    res = compute_audio_loudness_metadata("silence_01", str(FIXTURES_DIR / "silence.wav"))
    assert res.status == "INGESTED"
    assert res.loudness_status == "LOUDNESS_UNDEFINED"
    assert res.orig_lufs is None
    assert res.gain_db == 0.0


def test_ingest_short_clip_loudness_undefined() -> None:
    res = compute_audio_loudness_metadata("short_01", str(FIXTURES_DIR / "short_clip.wav"))
    assert res.status == "INGESTED"
    assert res.loudness_status == "LOUDNESS_UNDEFINED"
    assert res.gain_db == 0.0


def test_ingest_gain_cap_at_20db(tmp_path: Path) -> None:
    # Very quiet signal (-50 LUFS equivalent)
    sr = 24000
    t = np.linspace(0, 5, sr * 5, endpoint=False, dtype=np.float32)
    quiet_audio = 1e-3 * np.sin(2 * np.pi * 440 * t)
    quiet_file = tmp_path / "quiet.wav"
    sf.write(str(quiet_file), quiet_audio, sr)

    res = compute_audio_loudness_metadata("quiet_01", str(quiet_file))
    assert res.status == "INGESTED"
    assert res.loudness_status == "NORMALIZED"
    assert res.gain_db <= 20.0  # Capped at +20 dB


def test_ingest_true_peak_limiting_to_minus_1_dbtp(tmp_path: Path) -> None:
    # High amplitude audio near 0 dBFS
    sr = 24000
    t = np.linspace(0, 5, sr * 5, endpoint=False, dtype=np.float32)
    loud_audio = 0.95 * np.sin(2 * np.pi * 440 * t)  # ~ -0.45 dB peak
    loud_file = tmp_path / "loud.wav"
    sf.write(str(loud_file), loud_audio, sr)

    res = compute_audio_loudness_metadata("loud_01", str(loud_file))
    assert res.status == "INGESTED"
    assert res.orig_peak_db is not None
    post_gain_peak = res.orig_peak_db + res.gain_db
    # Post-gain true peak must never exceed -1.0 dBTP
    assert post_gain_peak <= -0.99


def test_run_ingest_pipeline(tmp_path: Path) -> None:
    from audio_token_pipeline.catalog import Catalog
    from audio_token_pipeline.config import AppConfig
    from audio_token_pipeline.stages.ingest import run_ingest

    db_path = tmp_path / "test_ingest.duckdb"
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
    )
    res = run_ingest(cfg, num_workers=1)
    assert res["items_in"] == 1
    assert res["items_out"] == 1

