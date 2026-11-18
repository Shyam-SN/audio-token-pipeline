"""Profile Stage 1 Ingest using cProfile to isolate bottlenecks."""

from __future__ import annotations

import cProfile
import pstats
from pathlib import Path

from audio_token_pipeline.catalog import Catalog
from audio_token_pipeline.config import AppConfig
from audio_token_pipeline.stages.ingest import run_ingest


def profile_ingest(config_path: str = "configs/librispeech_dev_clean.yaml", num_workers: int = 6) -> None:
    cfg = AppConfig.from_yaml(config_path)
    out_dir = Path("docs/profiles")
    out_dir.mkdir(parents=True, exist_ok=True)
    prof_file = out_dir / "ingest.prof"
    txt_file = out_dir / "ingest_profile.txt"

    cat = Catalog(cfg.catalog_path)
    with cat.connection() as con:
        con.execute("UPDATE sources SET status = 'PENDING'")

    profiler = cProfile.Profile()
    profiler.enable()
    run_ingest(cfg, num_workers=num_workers)
    profiler.disable()

    profiler.dump_stats(str(prof_file))
    with open(txt_file, "w", encoding="utf-8") as f:
        stats = pstats.Stats(profiler, stream=f).sort_stats("cumulative")
        stats.print_stats(30)
    print(f"Profile saved to {prof_file} and {txt_file}")


if __name__ == "__main__":
    profile_ingest()

