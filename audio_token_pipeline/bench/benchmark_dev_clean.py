"""Benchmarking script for Stage 1 Ingest and Stage 2 Segmentation throughput across worker counts [1, 2, 4, 6]."""

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


def run_benchmark_1_to_6_workers(
    config_path: Path | str = "configs/librispeech_dev_clean.yaml",
    results_dir: Path | str = "bench/results",
    worker_counts: list[int] | None = None,
    repeat_count: int = 10,
    min_runtime_s: float = 60.0,
    stages: list[str] | None = None,
) -> dict[str, Any]:
    """
    Benchmark Stage 1 (Ingest) and Stage 2 (Segmentation) across 1, 2, 4, and 6 workers.
    Repeats on dataset 10x (>= 60s runs) for stable, noise-free measurements.
    """
    if worker_counts is None:
        worker_counts = [1, 2, 4, 6]
    if stages is None:
        stages = ["ingest", "segment"]

    res_dir = Path(results_dir)
    res_dir.mkdir(parents=True, exist_ok=True)
    cfg = AppConfig.from_yaml(config_path)
    cat = Catalog(cfg.catalog_path)

    out_file = res_dir / "stage1_stage2_benchmarks.json"
    existing_results: dict[str, Any] = {}
    if out_file.is_file():
        try:
            with open(out_file, encoding="utf-8") as f:
                existing_results = json.load(f)
        except Exception:
            pass

    results: dict[str, Any] = {
        "dataset": cfg.dataset.name,
        "split": cfg.dataset.split,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stage_1_ingest": existing_results.get("stage_1_ingest", {}),
        "stage_2_segment": existing_results.get("stage_2_segment", {}),
    }

    # ==========================================
    # --- Benchmark Stage 1 (Ingest) ---
    # ==========================================
    if "ingest" in stages:
        baseline_ingest_th = 0.0
        for w in worker_counts:
            print(f"\n=== Benchmarking Stage 1 Ingest ({w} worker{'s' if w > 1 else ''}) [repeated >= {min_runtime_s}s] ===")
            total_audio_s = 0.0
            passes = 0
            last_res: dict[str, Any] = {}
            t_start = time.perf_counter()

            while passes < repeat_count or (time.perf_counter() - t_start) < min_runtime_s:
                with cat.connection() as con:
                    con.execute("UPDATE sources SET status = 'PENDING'")
                res = run_ingest(cfg, num_workers=w)
                total_audio_s += res.get("total_audio_seconds", 0.0)
                last_res = res
                passes += 1

            elapsed_total = max(time.perf_counter() - t_start, 1e-4)
            th = round((total_audio_s / 3600.0) / (elapsed_total / 3600.0), 2)
            res_summary = dict(last_res)
            res_summary["throughput_audio_hours_per_wall_hour"] = th
            res_summary["total_audio_seconds"] = round(total_audio_s, 3)
            res_summary["elapsed_seconds"] = round(elapsed_total, 3)
            res_summary["passes"] = passes

            if w == 1:
                baseline_ingest_th = th
                speedup = 1.0
            else:
                speedup = round(th / max(baseline_ingest_th, 1e-4), 2)

            res_summary["speedup_vs_1w"] = speedup
            results["stage_1_ingest"][f"{w}_worker{'s' if w > 1 else ''}"] = res_summary
            print(f"Stage 1 ({w}w): {th} audio-h/h ({passes} passes in {elapsed_total:.1f}s, Speedup: {speedup}x)")

        results["stage_1_ingest"]["speedup_6w_vs_1w"] = results["stage_1_ingest"].get("6_workers", {}).get("speedup_vs_1w", 1.0)

    # ==========================================
    # --- Benchmark Stage 2 (Segmentation) ---
    # ==========================================
    if "segment" in stages:
        baseline_seg_th = 0.0
        for w in worker_counts:
            print(f"\n=== Benchmarking Stage 2 Segmentation ({w} worker{'s' if w > 1 else ''}) [repeated >= {min_runtime_s}s] ===")
            total_audio_s = 0.0
            total_segs = 0
            passes = 0
            last_res = {}
            t_start = time.perf_counter()

            while passes < max(1, repeat_count // 3) or (time.perf_counter() - t_start) < min_runtime_s:
                with cat.connection() as con:
                    con.execute("DELETE FROM segments")
                res = run_segment(cfg, num_workers=w)
                total_audio_s += res.get("total_audio_seconds", 0.0)
                total_segs += res.get("segments_out", 0)
                last_res = res
                passes += 1

            elapsed_total = max(time.perf_counter() - t_start, 1e-4)
            th = round((total_audio_s / 3600.0) / (elapsed_total / 3600.0), 2)
            spd = round(total_segs / elapsed_total, 2)
            res_summary = dict(last_res)
            res_summary["throughput_audio_hours_per_wall_hour"] = th
            res_summary["speed_segments_per_second"] = spd
            res_summary["total_audio_seconds"] = round(total_audio_s, 3)
            res_summary["elapsed_seconds"] = round(elapsed_total, 3)
            res_summary["passes"] = passes

            if w == 1:
                baseline_seg_th = th
                speedup = 1.0
            else:
                speedup = round(th / max(baseline_seg_th, 1e-4), 2)

            res_summary["speedup_vs_1w"] = speedup
            results["stage_2_segment"][f"{w}_worker{'s' if w > 1 else ''}"] = res_summary
            print(f"Stage 2 ({w}w): {th} audio-h/h, {spd} seg/s ({passes} passes in {elapsed_total:.1f}s, Speedup: {speedup}x)")

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
    import argparse
    parser = argparse.ArgumentParser(description="Benchmark Dev-Clean Stages")
    parser.add_argument("config", nargs="?", default="configs/librispeech_dev_clean.yaml")
    parser.add_argument("--stage", choices=["all", "ingest", "segment"], default="all")
    parser.add_argument("--workers", nargs="+", type=int, default=[1, 2, 4, 6])
    args = parser.parse_args()

    target_stages = ["ingest", "segment"] if args.stage == "all" else [args.stage]
    run_benchmark_1_to_6_workers(config_path=args.config, worker_counts=args.workers, stages=target_stages)
