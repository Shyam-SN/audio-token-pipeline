"""Stage 1: Streaming ingest and EBU R128 loudness metadata computation (zero audio on disk)."""

from __future__ import annotations

import logging
import math
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
import torch

from audio_token_pipeline.catalog import Catalog
from audio_token_pipeline.config import AppConfig

logger = logging.getLogger(__name__)


def worker_init() -> None:
    """Initialize worker process with single-threaded PyTorch to prevent CPU thread oversubscription."""
    try:
        torch.set_num_threads(1)
    except Exception:
        pass


@dataclass
class IngestResult:
    source_id: str
    duration_s: float
    sample_rate: int
    channels: int
    orig_lufs: float | None
    orig_peak_db: float | None
    gain_db: float
    loudness_status: str
    status: str
    error: str | None = None


def compute_audio_loudness_metadata(
    source_id: str,
    filepath: str,
    target_lufs: float = -23.0,
    max_gain_db: float = 20.0,
    true_peak_limit_db: float = -1.0,
) -> IngestResult:
    """
    Stream/read audio file to compute EBU R128 integrated loudness, true peak, and required gain.
    Does not save any resampled audio to disk.
    """
    fpath = Path(filepath)
    if not fpath.is_file():
        return IngestResult(
            source_id=source_id,
            duration_s=0.0,
            sample_rate=0,
            channels=0,
            orig_lufs=None,
            orig_peak_db=None,
            gain_db=0.0,
            loudness_status="ERROR",
            status="FAILED",
            error=f"File not found: {filepath}",
        )

    try:
        info = sf.info(str(fpath))
        sr = int(info.samplerate)
        channels = int(info.channels)
        audio, sr = sf.read(str(fpath), dtype="float32", always_2d=True)
    except Exception as e:
        return IngestResult(
            source_id=source_id,
            duration_s=0.0,
            sample_rate=0,
            channels=0,
            orig_lufs=None,
            orig_peak_db=None,
            gain_db=0.0,
            loudness_status="DECODE_FAIL",
            status="FAILED",
            error=f"DECODE_FAIL: {e}",
        )

    duration_s = float(len(audio)) / float(sr)
    peak_val = float(np.max(np.abs(audio))) if len(audio) > 0 else 0.0
    orig_peak_db = 20.0 * math.log10(max(peak_val, 1e-9))

    # Condition: Silent files (peak < 1e-4) or files under 400ms (< 0.4s)
    # Skip gain and flag LOUDNESS_UNDEFINED instead of quarantining
    if duration_s < 0.4 or peak_val < 1e-4:
        return IngestResult(
            source_id=source_id,
            duration_s=round(duration_s, 4),
            sample_rate=sr,
            channels=channels,
            orig_lufs=None,
            orig_peak_db=round(orig_peak_db, 2),
            gain_db=0.0,
            loudness_status="LOUDNESS_UNDEFINED",
            status="INGESTED",
        )

    # Compute integrated loudness via pyloudnorm
    try:
        meter = pyln.Meter(sr)  # BS.1770 compliant meter
        orig_lufs = float(meter.integrated_loudness(audio))
    except Exception:
        orig_lufs = float("-inf")

    if math.isinf(orig_lufs) or math.isnan(orig_lufs) or orig_lufs < -70.0:
        return IngestResult(
            source_id=source_id,
            duration_s=round(duration_s, 4),
            sample_rate=sr,
            channels=channels,
            orig_lufs=None,
            orig_peak_db=round(orig_peak_db, 2),
            gain_db=0.0,
            loudness_status="LOUDNESS_UNDEFINED",
            status="INGESTED",
        )

    # Nominal loudness gain: target - orig
    nominal_gain = target_lufs - orig_lufs

    # Rule: Cap gain at +20 dB
    gain_db = min(nominal_gain, max_gain_db)

    # Rule: Limit true peak to -1 dBTP
    # Post-gain peak: orig_peak_db + gain_db <= true_peak_limit_db
    post_gain_peak = orig_peak_db + gain_db
    if post_gain_peak > true_peak_limit_db:
        gain_db = min(gain_db, true_peak_limit_db - orig_peak_db)

    return IngestResult(
        source_id=source_id,
        duration_s=round(duration_s, 4),
        sample_rate=sr,
        channels=channels,
        orig_lufs=round(orig_lufs, 2),
        orig_peak_db=round(orig_peak_db, 2),
        gain_db=round(gain_db, 2),
        loudness_status="NORMALIZED",
        status="INGESTED",
    )


def run_ingest(
    config: AppConfig,
    num_workers: int | None = None,
    max_hours: float | None = None,
) -> dict[str, Any]:
    """
    Run Stage 1 Ingest in parallel with ProcessPoolExecutor.
    Main process performs all DuckDB catalogue writes (single-writer rule).
    """
    cat = Catalog(config.catalog_path)
    workers = num_workers or config.device.num_workers or 6

    # Fetch pending sources from catalog
    with cat.connection() as con:
        rows = con.execute(
            "SELECT source_id, filepath, duration_s, sample_rate, channels, sha256 FROM sources WHERE status != 'INGESTED' ORDER BY source_id"
        ).fetchall()

    if not rows:
        logger.info("No sources pending ingestion.")
        return {
            "items_in": 0,
            "items_out": 0,
            "throughput_audio_hours_per_wall_hour": 0.0,
            "total_audio_seconds": 0.0,
            "elapsed_seconds": 0.0,
            "workers": workers,
        }

    total_seconds = 0.0
    max_sec = (max_hours * 3600.0) if max_hours else float("inf")
    pending_tasks = []
    for r in rows:
        if total_seconds >= max_sec:
            break
        pending_tasks.append((r[0], r[1]))
        total_seconds += float(r[2]) if r[2] else 0.0

    logger.info(f"Ingesting {len(pending_tasks)} sources using {workers} workers (ProcessPoolExecutor)...")
    run_id = f"ingest_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    cat.start_run(run_id, "ingest", config.compute_hash())
    start_time = time.perf_counter()
    processed_count = 0
    total_audio_sec = 0.0

    with ProcessPoolExecutor(max_workers=workers, initializer=worker_init) as executor:
        future_map = {
            executor.submit(compute_audio_loudness_metadata, source_id, fpath): source_id
            for source_id, fpath in pending_tasks
        }

        for fut in as_completed(future_map):
            res: IngestResult = fut.result()
            if res.status == "FAILED":
                cat.record_dead_letter(
                    item_id=res.source_id,
                    stage="ingest",
                    reason_code=res.loudness_status,
                    error_message=res.error or "Ingest failed",
                )
            else:
                cat.update_source_ingest_metadata(
                    source_id=res.source_id,
                    orig_lufs=res.orig_lufs,
                    orig_peak_db=res.orig_peak_db,
                    gain_db=res.gain_db,
                    loudness_status=res.loudness_status,
                    status="INGESTED",
                )
                total_audio_sec += res.duration_s
                processed_count += 1

    elapsed_s = max(time.perf_counter() - start_time, 1e-4)
    audio_hours = total_audio_sec / 3600.0
    wall_hours = elapsed_s / 3600.0
    throughput = audio_hours / wall_hours if wall_hours > 0 else 0.0

    cat.finish_run(run_id, "COMPLETED", items_in=len(pending_tasks), items_out=processed_count)

    return {
        "items_in": len(pending_tasks),
        "items_out": processed_count,
        "total_audio_seconds": round(total_audio_sec, 3),
        "elapsed_seconds": round(elapsed_s, 3),
        "throughput_audio_hours_per_wall_hour": round(throughput, 2),
        "workers": workers,
    }
