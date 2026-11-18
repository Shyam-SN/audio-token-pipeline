"""Unit tests for downloader, checksum verification, and manifest generation."""

from pathlib import Path

import pyarrow.parquet as pq

from audio_token_pipeline.catalog import Catalog
from audio_token_pipeline.io.download import (
    build_manifest_parquet,
    compute_file_sha256,
    scan_audio_metadata,
)

FIXTURES_DIR = Path("tests/fixtures")


def test_compute_file_sha256(tmp_path: Path) -> None:
    test_file = tmp_path / "hello.txt"
    test_file.write_text("audio-token-pipeline test string", encoding="utf-8")

    sha = compute_file_sha256(test_file)
    assert len(sha) == 64
    # Deterministic check
    assert sha == compute_file_sha256(test_file)


def test_scan_audio_metadata() -> None:
    clean_fixture = FIXTURES_DIR / "clean_formant.wav"
    assert clean_fixture.exists(), "Clean fixture should exist"

    meta = scan_audio_metadata(clean_fixture)
    assert meta["sample_rate"] == 24000
    assert meta["channels"] == 1
    assert meta["duration_s"] is not None
    assert abs(float(meta["duration_s"]) - 40.0) < 0.1


def test_build_manifest_parquet(tmp_path: Path) -> None:
    manifest_out = tmp_path / "manifest.parquet"
    db_path = tmp_path / "cat.duckdb"
    catalog = Catalog(db_path)

    build_manifest_parquet(
        audio_dir=FIXTURES_DIR,
        manifest_path=manifest_out,
        dataset_name="smoke_test",
        split_name="fixtures",
        license_str="MIT",
        max_hours=1.0,
        catalog=catalog,
    )

    assert manifest_out.exists()
    table = pq.read_table(str(manifest_out))
    records = table.to_pylist()
    assert len(records) >= 7  # All generated fixture files
    assert "source_id" in table.column_names
    assert "sha256" in table.column_names
    assert "duration_s" in table.column_names

    # Verify DuckDB was populated
    summary = catalog.get_stage_status_summary()
    assert summary["sources_total"] == len(records)
