"""Unit tests for the Typer CLI commands."""

from typer.testing import CliRunner

from audio_token_pipeline.cli import app

runner = CliRunner()


def test_cli_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "Audio Token Pipeline" in result.stdout
    assert "0.1.0" in result.stdout


def test_cli_info() -> None:
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "Hardware & Environment Diagnostics" in result.stdout
    assert "optimal_device" in result.stdout


def test_cli_status() -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Catalog Status Summary" in result.stdout
    assert "Sources Total" in result.stdout


def test_cli_run_stub() -> None:
    result = runner.invoke(app, ["run", "--device", "cpu"])
    assert result.exit_code == 0
    assert "Starting ATP Pipeline" in result.stdout


def test_cli_report() -> None:
    result = runner.invoke(app, ["report", "stage_0_foundation"])
    assert result.exit_code == 0
    assert "Report generated successfully" in result.stdout


def test_cli_stage_stubs() -> None:
    for cmd in ["ingest", "segment", "filter", "transcribe", "tokenize", "shard", "feed-bench", "bench"]:
        res = runner.invoke(app, [cmd])
        assert res.exit_code == 0
