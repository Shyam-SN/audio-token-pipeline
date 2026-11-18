"""Unit tests for DuckDB catalog and dead-letter quarantine."""

from pathlib import Path

from audio_token_pipeline.catalog import Catalog


def test_catalog_initialization(tmp_path: Path) -> None:
    db_path = tmp_path / "test_catalog.duckdb"
    cat = Catalog(db_path)
    summary = cat.get_stage_status_summary()
    assert summary["sources_total"] == 0
    assert summary["dead_letter"] == 0


def test_register_source_and_update(tmp_path: Path) -> None:
    db_path = tmp_path / "test_catalog.duckdb"
    cat = Catalog(db_path)

    cat.register_source(
        source_id="src_001",
        filepath="/tmp/audio.wav",
        dataset="test_ds",
        split="train",
        duration_s=10.5,
        sample_rate=24000,
        channels=1,
        sha256="abc123sha",
        status="PENDING",
    )

    summary = cat.get_stage_status_summary()
    assert summary["sources_total"] == 1
    assert summary["sources_done"] == 0

    # Mark as DONE
    cat.register_source(
        source_id="src_001",
        filepath="/tmp/audio.wav",
        dataset="test_ds",
        split="train",
        duration_s=10.5,
        sample_rate=24000,
        channels=1,
        sha256="abc123sha",
        status="DONE",
    )
    summary = cat.get_stage_status_summary()
    assert summary["sources_total"] == 1
    assert summary["sources_done"] == 1


def test_dead_letter_quarantine(tmp_path: Path) -> None:
    db_path = tmp_path / "test_catalog.duckdb"
    cat = Catalog(db_path)

    cat.record_dead_letter(
        item_id="corrupt_001",
        stage="ingest",
        reason_code="DECODE_FAIL",
        error_message="Invalid audio header",
    )

    summary = cat.get_stage_status_summary()
    assert summary["dead_letter"] == 1

    records = cat.get_dead_letters()
    assert len(records) == 1
    assert records[0]["reason_code"] == "DECODE_FAIL"
    assert records[0]["stage"] == "ingest"


def test_run_audit_lifecycle(tmp_path: Path) -> None:
    db_path = tmp_path / "test_catalog.duckdb"
    cat = Catalog(db_path)

    run_id = "run_20261119_001"
    cat.start_run(run_id=run_id, stage="ingest", config_hash="1234abcd")
    cat.finish_run(run_id=run_id, status="SUCCESS", items_in=10, items_out=9)

    with cat.connection() as con:
        row = con.execute("SELECT status, items_in, items_out FROM runs WHERE run_id = ?", [run_id]).fetchone()
        assert row is not None
        assert row[0] == "SUCCESS"
        assert row[1] == 10
        assert row[2] == 9
