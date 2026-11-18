"""Benchmarking script for Stage 1 Ingest and Stage 2 Segmentation throughput across worker counts [1, 2, 4, 6]."""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from audio_token_pipeline.catalog import Catalog
from audio_token_pipeline.config import AppConfig
from audio_token_pipeline.stages.ingest import run_ingest
from audio_token_pipeline.stages.segment import run_segment

logger = logging.getLogger(__name__)


def run_benchmark_1_to_6_workers(
    config_path: Path | str = "configs/librispeech_dev_clean.yaml",
    results_dir: Path | str = "bench/results",
    worker_counts: list[int] | None = None,
) -> dict[str, Any]:
    """
    Benchmark Stage 1 (Ingest) and Stage 2 (Segmentation) across 1, 2, 4, and 6 workers.
    Returns scaling metrics and writes to bench/results/stage1_stage2_benchmarks.json.
    """
    if worker_counts is None:
        worker_counts = [1, 2, 4, 6]

    res_dir = Path(results_dir)
    res_dir.mkdir(parents=True, exist_ok=True)
    cfg = AppConfig.from_yaml(config_path)
    cat = Catalog(cfg.catalog_path)

    results: dict[str, Any] = {
        "dataset": cfg.dataset.name,
        "split": cfg.dataset.split,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stage_1_ingest": {},
        "stage_2_segment": {},
    }

    # ==========================================
    # --- Benchmark Stage 1 (Ingest) ---
    # ==========================================
    baseline_ingest_th = 0.0
    for w in worker_counts:
        print(f"\n=== Benchmarking Stage 1 Ingest ({w} worker{'s' if w > 1 else ''}) ===")
        with cat.connection() as con:
            con.execute("UPDATE sources SET status = 'PENDING'")
        res = run_ingest(cfg, num_workers=w)
        th = res.get("throughput_audio_hours_per_wall_hour", 0.0)
        if w == 1:
            baseline_ingest_th = th
            speedup = 1.0
        else:
            speedup = round(th / max(baseline_ingest_th, 1e-4), 2)
        res["speedup_vs_1w"] = speedup
        results["stage_1_ingest"][f"{w}_worker{'s' if w > 1 else ''}"] = res
        print(f"Stage 1 ({w}w): {th} audio-h/h (Speedup: {speedup}x)")

    results["stage_1_ingest"]["speedup_6w_vs_1w"] = results["stage_1_ingest"].get("6_workers", {}).get("speedup_vs_1w", 1.0)

    # ==========================================
    # --- Benchmark Stage 2 (Segmentation) ---
    # ==========================================
    baseline_seg_th = 0.0
    for w in worker_counts:
        print(f"\n=== Benchmarking Stage 2 Segmentation ({w} worker{'s' if w > 1 else ''}) ===")
        with cat.connection() as con:
            con.execute("DELETE FROM segments")
        res = run_segment(cfg, num_workers=w)
        th = res.get("throughput_audio_hours_per_wall_hour", 0.0)
        spd = res.get("speed_segments_per_second", 0.0)
        if w == 1:
            baseline_seg_th = th
            speedup = 1.0
        else:
            speedup = round(th / max(baseline_seg_th, 1e-4), 2)
        res["speedup_vs_1w"] = speedup
        results["stage_2_segment"][f"{w}_worker{'s' if w > 1 else ''}"] = res
        print(f"Stage 2 ({w}w): {th} audio-h/h, {spd} seg/s (Speedup: {speedup}x)")

    results["stage_2_segment"]["speedup_6w_vs_1w"] = results["stage_2_segment"].get("6_workers", {}).get("speedup_vs_1w", 1.0)

    # Save to JSON
    out_file = res_dir / "stage1_stage2_benchmarks.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved benchmark results to {out_file}")

    return results


def run_benchmark_1_and_6_workers(
    config_path: Path | str = "configs/librispeech_dev_clean.yaml",
    results_dir: Path | str = "bench/results",
) -> dict[str, Any]:
    """Compatibility wrapper running full [1, 2, 4, 6] worker benchmarks."""
    return run_benchmark_1_to_6_workers(config_path=config_path, results_dir=results_dir, worker_counts=[1, 2, 4, 6])


if __name__ == "__main__":
    cfg_file = sys.argv[1] if len(sys.argv) > 1 else "configs/librispeech_dev_clean.yaml"
    run_benchmark_1_to_6_workers(config_path=cfg_file)
