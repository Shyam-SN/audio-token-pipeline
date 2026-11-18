"""Benchmarking script for Stage 1 Ingest and Stage 2 Segmentation throughput across worker counts."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from audio_token_pipeline.catalog import Catalog
from audio_token_pipeline.config import AppConfig
from audio_token_pipeline.stages.ingest import run_ingest
from audio_token_pipeline.stages.segment import run_segment

logger = logging.getLogger(__name__)


def run_benchmark_1_and_6_workers(
    config_path: Path | str = "configs/librispeech_dev_clean.yaml",
    results_dir: Path | str = "bench/results",
) -> dict[str, Any]:
    """
    Benchmark Stage 1 (Ingest) and Stage 2 (Segmentation) with 1 worker vs 6 workers.
    Returns comparison metrics and writes to bench/results/stage1_stage2_benchmarks.json.
    """
    res_dir = Path(results_dir)
    res_dir.mkdir(parents=True, exist_ok=True)
    cfg = AppConfig.from_yaml(config_path)

    results: dict[str, Any] = {
        "dataset": cfg.dataset.name,
        "split": cfg.dataset.split,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stage_1_ingest": {},
        "stage_2_segment": {},
    }

    # --- Benchmark Stage 1 (Ingest) with 1 worker ---
    print("\n=== Benchmarking Stage 1 Ingest (1 worker) ===")
    cat = Catalog(cfg.catalog_path)
    with cat.connection() as con:
        con.execute("UPDATE sources SET status = 'PENDING'")
    res_ingest_1 = run_ingest(cfg, num_workers=1)
    results["stage_1_ingest"]["1_worker"] = res_ingest_1

    # Reset sources status to re-run with 6 workers for exact comparison
    cat = Catalog(cfg.catalog_path)
    with cat.connection() as con:
        con.execute("UPDATE sources SET status = 'PENDING' WHERE status = 'INGESTED'")

    # --- Benchmark Stage 1 (Ingest) with 6 workers ---
    print("\n=== Benchmarking Stage 1 Ingest (6 workers) ===")
    res_ingest_6 = run_ingest(cfg, num_workers=6)
    results["stage_1_ingest"]["6_workers"] = res_ingest_6

    # Speedup calculation
    th_1 = res_ingest_1.get("throughput_audio_hours_per_wall_hour", 1e-4)
    th_6 = res_ingest_6.get("throughput_audio_hours_per_wall_hour", 1e-4)
    speedup_ingest = round(th_6 / max(th_1, 1e-4), 2)
    results["stage_1_ingest"]["speedup_6w_vs_1w"] = speedup_ingest
    print(f"Stage 1 Ingest Speedup: {speedup_ingest}x ({th_1} -> {th_6} audio-h/wall-h)")

    # --- Benchmark Stage 2 (Segmentation) with 1 worker ---
    print("\n=== Benchmarking Stage 2 Segmentation (1 worker) ===")
    res_seg_1 = run_segment(cfg, num_workers=1)
    results["stage_2_segment"]["1_worker"] = res_seg_1

    # Clear segments to re-run cleanly with 6 workers
    with cat.connection() as con:
        con.execute("DELETE FROM segments")

    # --- Benchmark Stage 2 (Segmentation) with 6 workers ---
    print("\n=== Benchmarking Stage 2 Segmentation (6 workers) ===")
    res_seg_6 = run_segment(cfg, num_workers=6)
    results["stage_2_segment"]["6_workers"] = res_seg_6

    seg_sec_1 = res_seg_1.get("speed_segments_per_second", 1e-4)
    seg_sec_6 = res_seg_6.get("speed_segments_per_second", 1e-4)
    speedup_seg = round(seg_sec_6 / max(seg_sec_1, 1e-4), 2)
    results["stage_2_segment"]["speedup_6w_vs_1w"] = speedup_seg
    print(f"Stage 2 Segment Speedup: {speedup_seg}x ({seg_sec_1} -> {seg_sec_6} seg/s)")

    # Save to JSON
    out_file = res_dir / "stage1_stage2_benchmarks.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved benchmark results to {out_file}")

    return results


if __name__ == "__main__":
    import sys
    cfg_file = sys.argv[1] if len(sys.argv) > 1 else "configs/librispeech_dev_clean.yaml"
    run_benchmark_1_and_6_workers(config_path=cfg_file)
