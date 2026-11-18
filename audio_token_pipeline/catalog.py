"""Single source of truth: DuckDB catalogue for audio files, segments, tokens, runs, and errors."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)


class Catalog:
    """Manages the DuckDB catalog schema, transactions, queries, and dead-letter queue."""

    def __init__(self, db_path: Path | str = "catalog.duckdb"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        """Create a new DuckDB connection."""
        return duckdb.connect(str(self.db_path))

    @contextmanager
    def connection(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """Context manager for connections."""
        con = self.get_connection()
        try:
            yield con
        finally:
            con.close()

    def _init_schema(self) -> None:
        """Initialize catalog tables with idempotent IF NOT EXISTS clauses."""
        with self.connection() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS sources (
                    source_id VARCHAR PRIMARY KEY,
                    filepath VARCHAR NOT NULL,
                    dataset VARCHAR NOT NULL,
                    split VARCHAR NOT NULL,
                    duration_s DOUBLE,
                    sample_rate INTEGER,
                    channels INTEGER,
                    sha256 VARCHAR NOT NULL,
                    orig_lufs DOUBLE,
                    orig_peak_db DOUBLE,
                    gain_db DOUBLE,
                    loudness_status VARCHAR DEFAULT 'PENDING',
                    status VARCHAR DEFAULT 'PENDING',
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );
                ALTER TABLE sources ADD COLUMN IF NOT EXISTS orig_lufs DOUBLE;
                ALTER TABLE sources ADD COLUMN IF NOT EXISTS orig_peak_db DOUBLE;
                ALTER TABLE sources ADD COLUMN IF NOT EXISTS gain_db DOUBLE;
                ALTER TABLE sources ADD COLUMN IF NOT EXISTS loudness_status VARCHAR DEFAULT 'PENDING';

                CREATE TABLE IF NOT EXISTS dead_letter (
                    item_id VARCHAR PRIMARY KEY,
                    stage VARCHAR NOT NULL,
                    reason_code VARCHAR NOT NULL,
                    error_message VARCHAR,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id VARCHAR PRIMARY KEY,
                    stage VARCHAR NOT NULL,
                    config_hash VARCHAR NOT NULL,
                    git_commit VARCHAR DEFAULT '',
                    start_time TIMESTAMPTZ,
                    end_time TIMESTAMPTZ,
                    items_in INTEGER DEFAULT 0,
                    items_out INTEGER DEFAULT 0,
                    status VARCHAR,
                    error VARCHAR
                );
                ALTER TABLE runs ADD COLUMN IF NOT EXISTS git_commit VARCHAR DEFAULT '';

                CREATE TABLE IF NOT EXISTS segments (
                    segment_id VARCHAR PRIMARY KEY,
                    source_id VARCHAR NOT NULL,
                    start_ms INTEGER NOT NULL,
                    end_ms INTEGER NOT NULL,
                    duration_s DOUBLE NOT NULL,
                    speech_prob DOUBLE,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS filter_results (
                    segment_id VARCHAR PRIMARY KEY,
                    passed BOOLEAN NOT NULL,
                    silence_ratio DOUBLE,
                    clip_fraction DOUBLE,
                    snr_db DOUBLE,
                    dc_offset DOUBLE,
                    speech_prob DOUBLE,
                    reason_codes VARCHAR,
                    exact_hash VARCHAR,
                    near_duplicate_hash VARCHAR,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );
                ALTER TABLE filter_results ADD COLUMN IF NOT EXISTS exact_hash VARCHAR;
                ALTER TABLE filter_results ADD COLUMN IF NOT EXISTS near_duplicate_hash VARCHAR;

                CREATE TABLE IF NOT EXISTS transcripts (
                    segment_id VARCHAR PRIMARY KEY,
                    text VARCHAR NOT NULL,
                    language VARCHAR,
                    avg_logprob DOUBLE,
                    no_speech_prob DOUBLE,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS tokens (
                    segment_id VARCHAR PRIMARY KEY,
                    codec VARCHAR NOT NULL,
                    num_codebooks INTEGER NOT NULL,
                    num_frames INTEGER NOT NULL,
                    storage_path VARCHAR,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS shards (
                    shard_id VARCHAR PRIMARY KEY,
                    shard_path VARCHAR NOT NULL,
                    split VARCHAR NOT NULL,
                    num_samples INTEGER NOT NULL,
                    total_duration_s DOUBLE NOT NULL,
                    total_tokens BIGINT NOT NULL,
                    sha256 VARCHAR NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );
            """)

    def register_source(
        self,
        source_id: str,
        filepath: str,
        dataset: str,
        split: str,
        duration_s: float | None,
        sample_rate: int | None,
        channels: int | None,
        sha256: str,
        status: str = "PENDING",
    ) -> None:
        """Register or update a source audio file in the catalog."""
        with self.connection() as con:
            con.execute(
                """
                INSERT INTO sources (source_id, filepath, dataset, split, duration_s, sample_rate, channels, sha256, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (source_id) DO UPDATE SET
                    filepath = EXCLUDED.filepath,
                    duration_s = EXCLUDED.duration_s,
                    sample_rate = EXCLUDED.sample_rate,
                    channels = EXCLUDED.channels,
                    sha256 = EXCLUDED.sha256,
                    status = EXCLUDED.status;
                """,
                [
                    source_id,
                    filepath,
                    dataset,
                    split,
                    duration_s,
                    sample_rate,
                    channels,
                    sha256,
                    status,
                ],
            )

    def update_source_ingest_metadata(
        self,
        source_id: str,
        orig_lufs: float | None,
        orig_peak_db: float | None,
        gain_db: float,
        loudness_status: str,
        status: str = "INGESTED",
    ) -> None:
        """Update source loudness, true peak, and normalisation gain metadata without saving resampled audio."""
        self.update_sources_ingest_batch(
            [
                {
                    "source_id": source_id,
                    "orig_lufs": orig_lufs,
                    "orig_peak_db": orig_peak_db,
                    "gain_db": gain_db,
                    "loudness_status": loudness_status,
                    "status": status,
                }
            ]
        )

    def update_sources_ingest_batch(self, records: list[dict[str, Any]]) -> None:
        """Batch update source loudness, true peak, and normalisation gain metadata atomically."""
        if not records:
            return
        tuples = [
            (
                r.get("orig_lufs"),
                r.get("orig_peak_db"),
                r.get("gain_db", 0.0),
                r.get("loudness_status", "NORMALIZED"),
                r.get("status", "INGESTED"),
                r["source_id"],
            )
            for r in records
        ]
        with self.connection() as con:
            con.executemany(
                """
                UPDATE sources
                SET orig_lufs = ?,
                    orig_peak_db = ?,
                    gain_db = ?,
                    loudness_status = ?,
                    status = ?
                WHERE source_id = ?;
                """,
                tuples,
            )

    def record_dead_letters_batch(self, records: list[dict[str, Any]]) -> None:
        """Batch insert quarantined dead letter items atomically."""
        if not records:
            return
        tuples = [
            (
                r["item_id"],
                r["stage"],
                r["reason_code"],
                r.get("error_message", ""),
                datetime.now(UTC),
            )
            for r in records
        ]
        with self.connection() as con:
            con.executemany(
                """
                INSERT INTO dead_letter (item_id, stage, reason_code, error_message, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (item_id) DO UPDATE SET
                    stage = EXCLUDED.stage,
                    reason_code = EXCLUDED.reason_code,
                    error_message = EXCLUDED.error_message,
                    created_at = EXCLUDED.created_at;
                """,
                tuples,
            )

    def record_segments_batch(self, segments: list[dict[str, Any]]) -> None:
        """Atomically insert detected speech segment coordinates into DuckDB."""
        if not segments:
            return
        records = [
            (
                s["segment_id"],
                s["source_id"],
                int(s["start_ms"]),
                int(s["end_ms"]),
                float(s["duration_s"]),
                float(s.get("speech_prob", 1.0)),
                datetime.now(UTC),
            )
            for s in segments
        ]
        with self.connection() as con:
            con.executemany(
                """
                INSERT INTO segments (segment_id, source_id, start_ms, end_ms, duration_s, speech_prob, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (segment_id) DO UPDATE SET
                    start_ms = EXCLUDED.start_ms,
                    end_ms = EXCLUDED.end_ms,
                    duration_s = EXCLUDED.duration_s,
                    speech_prob = EXCLUDED.speech_prob;
                """,
                records,
            )

    def record_filter_results_batch(self, results: list[dict[str, Any]]) -> None:
        """Atomically insert or update quality filtering results into DuckDB."""
        if not results:
            return
        records = [
            (
                r["segment_id"],
                bool(r["passed"]),
                float(r["silence_ratio"]) if r.get("silence_ratio") is not None else None,
                float(r["clip_fraction"]) if r.get("clip_fraction") is not None else None,
                float(r["snr_db"]) if r.get("snr_db") is not None else None,
                float(r["dc_offset"]) if r.get("dc_offset") is not None else None,
                float(r["speech_prob"]) if r.get("speech_prob") is not None else None,
                str(r.get("reason_codes", "")),
                str(r.get("exact_hash", "")),
                str(r.get("near_duplicate_hash", "")),
                datetime.now(UTC),
            )
            for r in results
        ]
        with self.connection() as con:
            con.executemany(
                """
                INSERT INTO filter_results (
                    segment_id, passed, silence_ratio, clip_fraction, snr_db,
                    dc_offset, speech_prob, reason_codes, exact_hash, near_duplicate_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (segment_id) DO UPDATE SET
                    passed = EXCLUDED.passed,
                    silence_ratio = EXCLUDED.silence_ratio,
                    clip_fraction = EXCLUDED.clip_fraction,
                    snr_db = EXCLUDED.snr_db,
                    dc_offset = EXCLUDED.dc_offset,
                    speech_prob = EXCLUDED.speech_prob,
                    reason_codes = EXCLUDED.reason_codes,
                    exact_hash = EXCLUDED.exact_hash,
                    near_duplicate_hash = EXCLUDED.near_duplicate_hash,
                    created_at = EXCLUDED.created_at;
                """,
                records,
            )

    def record_dead_letter(
        self,
        item_id: str,
        stage: str,
        reason_code: str,
        error_message: str | None = None,
    ) -> None:
        """Quarantine a failing item into the dead-letter queue."""
        with self.connection() as con:
            con.execute(
                """
                INSERT INTO dead_letter (item_id, stage, reason_code, error_message, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (item_id) DO UPDATE SET
                    stage = EXCLUDED.stage,
                    reason_code = EXCLUDED.reason_code,
                    error_message = EXCLUDED.error_message,
                    created_at = EXCLUDED.created_at;
                """,
                [item_id, stage, reason_code, error_message or "", datetime.now(UTC)],
            )

    def start_run(self, run_id: str, stage: str, config_hash: str, git_commit: str = "") -> None:
        """Audit log the beginning of a pipeline run."""
        with self.connection() as con:
            con.execute(
                """
                INSERT INTO runs (run_id, stage, config_hash, git_commit, start_time, status)
                VALUES (?, ?, ?, ?, ?, 'RUNNING');
                """,
                [run_id, stage, config_hash, git_commit, datetime.now(UTC)],
            )

    def finish_run(
        self,
        run_id: str,
        status: str,
        items_in: int = 0,
        items_out: int = 0,
        error: str | None = None,
    ) -> None:
        """Audit log the completion or failure of a pipeline run."""
        with self.connection() as con:
            con.execute(
                """
                UPDATE runs
                SET end_time = ?,
                    status = ?,
                    items_in = ?,
                    items_out = ?,
                    error = ?
                WHERE run_id = ?;
                """,
                [datetime.now(UTC), status, items_in, items_out, error, run_id],
            )

    def get_stage_status_summary(self) -> dict[str, Any]:
        """Query count of items across all pipeline stages and dead letter queue."""
        with self.connection() as con:
            sources_count = con.execute("SELECT count(*) FROM sources;").fetchone()[0]  # type: ignore[index]
            sources_done = con.execute(
                "SELECT count(*) FROM sources WHERE status = 'DONE';"
            ).fetchone()[0]  # type: ignore[index]
            segments_count = con.execute("SELECT count(*) FROM segments;").fetchone()[0]  # type: ignore[index]
            filtered_passed = con.execute(
                "SELECT count(*) FROM filter_results WHERE passed = true;"
            ).fetchone()[0]  # type: ignore[index]
            filtered_rejected = con.execute(
                "SELECT count(*) FROM filter_results WHERE passed = false;"
            ).fetchone()[0]  # type: ignore[index]
            transcripts_count = con.execute("SELECT count(*) FROM transcripts;").fetchone()[0]  # type: ignore[index]
            tokens_count = con.execute("SELECT count(*) FROM tokens;").fetchone()[0]  # type: ignore[index]
            shards_count = con.execute("SELECT count(*) FROM shards;").fetchone()[0]  # type: ignore[index]
            dead_letter_count = con.execute("SELECT count(*) FROM dead_letter;").fetchone()[0]  # type: ignore[index]

            return {
                "sources_total": sources_count,
                "sources_done": sources_done,
                "segments": segments_count,
                "filter_passed": filtered_passed,
                "filter_rejected": filtered_rejected,
                "transcripts": transcripts_count,
                "tokens": tokens_count,
                "shards": shards_count,
                "dead_letter": dead_letter_count,
            }

    def get_dead_letters(self) -> list[dict[str, Any]]:
        """Fetch all dead-letter records."""
        with self.connection() as con:
            rows = con.execute(
                "SELECT item_id, stage, reason_code, error_message, created_at FROM dead_letter;"
            ).fetchall()
            return [
                {
                    "item_id": r[0],
                    "stage": r[1],
                    "reason_code": r[2],
                    "error_message": r[3],
                    "created_at": r[4],
                }
                for r in rows
            ]
