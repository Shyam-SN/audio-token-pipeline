"""Typer CLI interface for Audio Token Pipeline."""

from __future__ import annotations

import logging
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
) -> None:
    """Stage 1: Ingest, resample to 24 kHz mono, loudness-normalise to -23 LUFS."""
    console.print("[yellow]Stage 1 (ingest) will run in Day 2[/yellow]")


@app.command()
def segment(
    config: Path = typer.Option(Path("configs/dev_mac.yaml"), "--config", "-c", help="Path to config"),
) -> None:
    """Stage 2: Voice Activity Detection (Silero VAD) segmentation."""
    console.print("[yellow]Stage 2 (segment) will run in Day 2[/yellow]")


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
    """Run end-to-end benchmark suite and write results JSON."""
    console.print("[yellow]Benchmark suite will run in Day 7-8[/yellow]")


@app.command()
def report(
    stage: str | None = typer.Option(None, "--stage", help="Stage name to report"),
) -> None:
    """Generate verification reports from catalog metrics."""
    console.print("[yellow]Report generator ready.[/yellow]")


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
