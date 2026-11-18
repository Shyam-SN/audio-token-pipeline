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
                    status VARCHAR DEFAULT 'PENDING',
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );

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
                    start_time TIMESTAMPTZ,
                    end_time TIMESTAMPTZ,
                    items_in INTEGER DEFAULT 0,
                    items_out INTEGER DEFAULT 0,
                    status VARCHAR,
                    error VARCHAR
                );

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
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );

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
                [source_id, filepath, dataset, split, duration_s, sample_rate, channels, sha256, status],
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

    def start_run(self, run_id: str, stage: str, config_hash: str) -> None:
        """Audit log the beginning of a pipeline run."""
        with self.connection() as con:
            con.execute(
                """
                INSERT INTO runs (run_id, stage, config_hash, start_time, status)
                VALUES (?, ?, ?, ?, 'RUNNING');
                """,
                [run_id, stage, config_hash, datetime.now(UTC)],
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
            sources_done = con.execute("SELECT count(*) FROM sources WHERE status = 'DONE';").fetchone()[0]  # type: ignore[index]
            segments_count = con.execute("SELECT count(*) FROM segments;").fetchone()[0]  # type: ignore[index]
            filtered_passed = con.execute("SELECT count(*) FROM filter_results WHERE passed = true;").fetchone()[0]  # type: ignore[index]
            filtered_rejected = con.execute("SELECT count(*) FROM filter_results WHERE passed = false;").fetchone()[0]  # type: ignore[index]
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
            rows = con.execute("SELECT item_id, stage, reason_code, error_message, created_at FROM dead_letter;").fetchall()
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
