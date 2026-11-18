"""Typer CLI interface for Audio Token Pipeline."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from audio_token_pipeline import __version__
from audio_token_pipeline.catalog import Catalog
from audio_token_pipeline.config import AppConfig
from audio_token_pipeline.device import get_device_info, resolve_device

app = typer.Typer(
    name="atp",
    help="Audio Token Pipeline (atp) - High-throughput speech tokenization CLI",
    add_completion=False,
)
console = Console()
logger = logging.getLogger("atp")


@app.command()
def version() -> None:
    """Print pipeline version."""
    console.print(f"[bold green]Audio Token Pipeline (atp)[/bold green] version {__version__}")


@app.command()
def info() -> None:
    """Display machine hardware, platform detection, and acceleration status."""
    info_data = get_device_info()
    table = Table(title="Hardware & Environment Diagnostics")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="magenta")

    for k, v in info_data.items():
        table.add_row(str(k), str(v))

    console.print(table)


@app.command()
def status(
    config: Path = typer.Option(Path("configs/dev_mac.yaml"), "--config", "-c", help="Path to YAML config"),
) -> None:
    """Display current item counts across all stages in the DuckDB catalog."""
    cfg = AppConfig.from_yaml(config) if config.exists() else AppConfig()
    cat = Catalog(cfg.catalog_path)
    summary = cat.get_stage_status_summary()

    table = Table(title=f"Catalog Status Summary ({cfg.catalog_path})")
    table.add_column("Stage / Item", style="cyan")
    table.add_column("Count", justify="right", style="green")

    table.add_row("Sources Total", str(summary["sources_total"]))
    table.add_row("Sources Completed", str(summary["sources_done"]))
    table.add_row("Segments Created", str(summary["segments"]))
    table.add_row("Filter Passed", str(summary["filter_passed"]))
    table.add_row("Filter Rejected", str(summary["filter_rejected"]))
    table.add_row("Transcripts Generated", str(summary["transcripts"]))
    table.add_row("Tokens Generated", str(summary["tokens"]))
    table.add_row("WebDataset Shards", str(summary["shards"]))
    table.add_row("Dead Letter (Quarantine)", f"[red]{summary['dead_letter']}[/red]" if summary['dead_letter'] > 0 else "0")

    console.print(table)


@app.command()
def download(
    config: Path = typer.Option(Path("configs/dev_mac.yaml"), "--config", "-c", help="Path to config"),
    max_hours: float | None = typer.Option(None, "--max-hours", help="Override max audio hours to scan"),
) -> None:
    """Download or index dataset, verify checksums, and generate manifest."""
    cfg = AppConfig.from_yaml(config) if config.exists() else AppConfig()
    from audio_token_pipeline.io.download import build_manifest_parquet

    catalog = Catalog(cfg.catalog_path)
    console.print(f"[bold blue]Indexing dataset[/bold blue]: {cfg.dataset.name} ({cfg.dataset.split})")

    # If directory has audio, build manifest
    if cfg.dataset.download_dir.exists():
        manifest_file = build_manifest_parquet(
            audio_dir=cfg.dataset.download_dir,
            manifest_path=cfg.dataset.manifest_path,
            dataset_name=cfg.dataset.name,
            split_name=cfg.dataset.split,
            license_str=cfg.dataset.license,
            max_hours=max_hours or cfg.dataset.max_hours,
            catalog=catalog,
        )
        console.print(f"[green]Manifest generated at:[/green] {manifest_file}")
    else:
        console.print(f"[yellow]Download directory does not exist: {cfg.dataset.download_dir}[/yellow]")


@app.command()
def ingest(
    config: Path = typer.Option(Path("configs/dev_mac.yaml"), "--config", "-c", help="Path to config"),
    workers: int | None = typer.Option(None, "--workers", "-w", help="Number of worker processes"),
    max_hours: float | None = typer.Option(None, "--max-hours", help="Max hours to ingest"),
) -> None:
    """Stage 1: Streaming ingest and EBU R128 loudness normalisation metadata (metadata only)."""
    from audio_token_pipeline.stages.ingest import run_ingest

    cfg = AppConfig.from_yaml(config) if config.exists() else AppConfig()
    cat = Catalog(cfg.catalog_path)
    run_id = f"ingest_{int(time.time())}"
    cat.start_run(run_id=run_id, stage="ingest", config_hash=cfg.compute_hash("ingest"))

    console.print("[bold blue]Starting Stage 1 (Ingest)...[/bold blue]")
    metrics = run_ingest(cfg, num_workers=workers, max_hours=max_hours)
    cat.finish_run(run_id=run_id, status="SUCCESS", items_in=metrics["items_in"], items_out=metrics["items_out"])

    console.print(f"[bold green]Stage 1 Complete:[/bold green] {metrics['items_out']}/{metrics['items_in']} sources ingested.")
    console.print(f"Throughput: [bold cyan]{metrics['throughput_audio_hours_per_wall_hour']} audio-h / wall-clock-h[/bold cyan] ({metrics['workers']} workers)")


@app.command()
def segment(
    config: Path = typer.Option(Path("configs/dev_mac.yaml"), "--config", "-c", help="Path to config"),
    workers: int | None = typer.Option(None, "--workers", "-w", help="Number of worker processes"),
    max_hours: float | None = typer.Option(None, "--max-hours", help="Max hours to segment"),
) -> None:
    """Stage 2: Voice Activity Detection (Silero VAD) on on-the-fly 16 kHz stream."""
    from audio_token_pipeline.stages.segment import run_segment

    cfg = AppConfig.from_yaml(config) if config.exists() else AppConfig()
    cat = Catalog(cfg.catalog_path)
    run_id = f"segment_{int(time.time())}"
    cat.start_run(run_id=run_id, stage="segment", config_hash=cfg.compute_hash("segment"))

    console.print("[bold blue]Starting Stage 2 (Segmentation)...[/bold blue]")
    metrics = run_segment(cfg, num_workers=workers, max_hours=max_hours)
    cat.finish_run(run_id=run_id, status="SUCCESS", items_in=metrics["items_in"], items_out=metrics["segments_out"])

    console.print(f"[bold green]Stage 2 Complete:[/bold green] {metrics['segments_out']} segments generated across {metrics['items_in']} sources.")
    console.print(f"Speed: [bold cyan]{metrics['speed_segments_per_second']} segments/s[/bold cyan], avg speech ratio: {metrics['avg_speech_ratio']}")


@app.command()
def filter(
    config: Path = typer.Option(Path("configs/dev_mac.yaml"), "--config", "-c", help="Path to config"),
) -> None:
    """Stage 3: Multi-metric quality filtering."""
    console.print("[yellow]Stage 3 (filter) will run in Day 3[/yellow]")


@app.command()
def transcribe(
    config: Path = typer.Option(Path("configs/dev_mac.yaml"), "--config", "-c", help="Path to config"),
) -> None:
    """Stage 4: Whisper transcription with length-bucketed batching."""
    console.print("[yellow]Stage 4 (transcribe) will run in Day 4[/yellow]")


@app.command()
def tokenize(
    config: Path = typer.Option(Path("configs/dev_mac.yaml"), "--config", "-c", help="Path to config"),
) -> None:
    """Stage 5: Mimi & EnCodec audio codec tokenisation."""
    console.print("[yellow]Stage 5 (tokenize) will run in Day 5[/yellow]")


@app.command()
def shard(
    config: Path = typer.Option(Path("configs/dev_mac.yaml"), "--config", "-c", help="Path to config"),
) -> None:
    """Stage 6: WebDataset sharding and manifest creation."""
    console.print("[yellow]Stage 6 (shard) will run in Day 6[/yellow]")


@app.command()
def feed_bench(
    config: Path = typer.Option(Path("configs/dev_mac.yaml"), "--config", "-c", help="Path to config"),
) -> None:
    """Stage 7: Streaming training feed and probe dataloader stall benchmark."""
    console.print("[yellow]Stage 7 (feed-bench) will run in Day 6[/yellow]")


@app.command()
def bench(
    config: Path = typer.Option(Path("configs/dev_mac.yaml"), "--config", "-c", help="Path to config"),
) -> None:
    """Benchmark Stage 1 (Ingest) and Stage 2 (Segmentation) across 1 vs 6 workers."""
    from audio_token_pipeline.bench.benchmark_dev_clean import run_benchmark_1_and_6_workers

    console.print("[bold blue]Starting Throughput Benchmarks (1 worker vs 6 workers)...[/bold blue]")
    run_benchmark_1_and_6_workers(config_path=config)
    console.print("[bold green]Benchmarks complete.[/bold green]")


@app.command()
def report(
    stage: str = typer.Argument("stage_0_foundation", help="Stage name to report (e.g. stage_0_foundation)"),
    config: Path = typer.Option(Path("configs/dev_mac.yaml"), "--config", "-c", help="Path to config"),
) -> None:
    """Generate verification reports strictly from captured catalogue and coverage data."""
    from audio_token_pipeline.bench.report import generate_stage_report

    md_path, json_path = generate_stage_report(stage_name=stage, config_path=config)
    console.print("[bold green]Report generated successfully:[/bold green]")
    console.print(f"  Markdown: [cyan]{md_path}[/cyan]")
    console.print(f"  JSON:     [cyan]{json_path}[/cyan]")


@app.command()
def run(
    config: Path = typer.Option(Path("configs/dev_mac.yaml"), "--config", "-c", help="Path to config"),
    max_hours: float | None = typer.Option(None, "--max-hours", help="Override max hours"),
    device: str | None = typer.Option(None, "--device", help="Device override (cpu, mps, cuda)"),
) -> None:
    """Run all stages in end-to-end pipeline with resumption."""
    resolved = resolve_device(device)
    console.print(f"[bold green]Starting ATP Pipeline on device: {resolved}[/bold green]")


if __name__ == "__main__":
    app()
