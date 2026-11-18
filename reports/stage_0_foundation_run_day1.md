# Stage Report: Day 1 – Foundation, Config, Catalog, Downloader & CI

## 1. Summary
Day 1 sets up the core architecture of the Audio Token Pipeline (`atp`). It delivers a unified device abstraction (`device.py`) cleanly handling Apple Silicon M4 / CUDA / CPU fallbacks, a Pydantic v2 configuration engine (`config.py`) with deterministic SHA-256 config hashing, an embedded DuckDB single-source-of-truth catalogue with a dead-letter quarantine mechanism (`catalog.py`), a content-addressed disk cache (`cache.py`), a streaming metadata scanner and Parquet manifest generator (`io/download.py`), a 5-minute multi-condition synthetic audio test fixture suite (`tests/fixtures/`), a Typer CLI (`cli.py`), and GitHub Actions CI matrix. All targets PASSED with 100% test success across 21 unit tests.
Key headline numbers:
- **Unit test pass rate:** 100% (21/21 passed in 1.41s)
- **Catalog & Cache coverage:** 100% catalog coverage, 93% cache coverage
- **Smoke test fixture duration:** 300.5s (~5.01 mins) across 8 test acoustic conditions

## 2. Environment
- **Machine:** Apple MacBook Air
- **Chip:** Apple M4 (arm64, 10-core)
- **RAM:** 16.0 GB unified memory
- **OS:** macOS 15.4.1 (Darwin arm64)
- **Python Version:** 3.11.16 (managed with `uv`)
- **Key Libraries:** PyTorch 2.15.0, DuckDB 2.0.0, PyArrow 18.1.0, SoundFile 0.14.0, PyAV 18.1.0, Pydantic 2.14.3
- **Device Used:** `cpu` (safe fallback on macOS sandboxed process)
- **Git Commit:** `e24fe2f`
- **Config Hash:** `62bf143a537fbdcb`
- **Run ID:** `day1_foundation_e24fe2f`
- **Start / End Time:** 2026-11-19T00:29:00Z to 2026-11-19T00:36:00Z

## 3. Inputs
- **Dataset / Split:** Synthetic smoke-test audio fixtures (`tests/fixtures/`)
- **Number of Files:** 8 audio clips covering clean speech harmonic formants, pure silence, hard clipping, DC bias offset, low SNR noise (5 dB), musical chord harmonics, short clip (<1s), and extended conversational speech
- **Total Audio Duration:** 300.5 seconds (0.0835 audio hours)

## 4. Outputs
- **Items In / Out:** 8 in, 8 registered to catalog, 0 quarantined
- **Manifest:** `data/manifest.parquet` generated with sample rate, channels, SHA-256, duration, and license
- **Catalogue:** `catalog.duckdb` populated with tables `sources`, `dead_letter`, `runs`, `segments`, `filter_results`, `transcripts`, `tokens`, `shards`
- **Predefined Configs:** `configs/dev_mac.yaml`, `configs/kaggle_t4.yaml`, `configs/bench_1000h.yaml`
- **Test Artifacts:** 21 automated unit tests

## 5. Metrics Table

| Metric | Value | Unit | Type | Measurement Method | Target | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Test suite pass rate | 100.0 | % | Measured | `uv run pytest` (21 passed) | 100% | PASS |
| Catalog module coverage | 100.0 | % | Measured | `pytest-cov` on `catalog.py` | ≥ 85% | PASS |
| Cache module coverage | 93.0 | % | Measured | `pytest-cov` on `cache.py` | ≥ 85% | PASS |
| Config module coverage | 98.0 | % | Measured | `pytest-cov` on `config.py` | ≥ 85% | PASS |
| Fixture duration | 300.5 | s | Measured | SoundFile header sum | ≥ 300.0 s | PASS |
| Config hash determinism | 100.0 | % | Measured | SHA-256 stability across runs | 100% | PASS |

## 6. Performance
- **Pytest execution time:** 1.41 s for full suite
- **Ruff linting & check:** 0.08 s (clean across all files)
- **Mypy strict type-check:** Clean (0 errors across 7 source modules)
- **RAM footprint:** Peak memory during tests < 250 MB (far below the 16 GB ceiling)

## 7. Before/After Comparisons
- **Dependency compatibility:**
  - *Baseline:* Default `pyarrow 26` required NumPy 2+, causing collection conflict with PyTorch and SoundFile built on NumPy 1.26.4.
  - *Optimization / Fix:* Pinned `pyarrow>=15.0.0,<19.0.0` (installed `pyarrow 18.1.0`), achieving full binary interoperability and zero import overhead without sacrificing Parquet speed.

## 8. Quality Evidence
- **Config Hashing:** Changing `target_sample_rate` in `ingest` strictly alters `cfg.compute_hash("ingest")` while leaving `cfg.compute_hash("segment")` unchanged, validating stage-level cache isolation.
- **Dead-Letter Isolation:** Injection of bad header test item into `record_dead_letter` quarantined entry under code `DECODE_FAIL` without interrupting catalog state.
- **5 Spot-Check Samples:**
  1. `clean_formant.wav`: duration=40.0s, sr=24000, channels=1
  2. `silence.wav`: duration=30.0s, sr=24000, channels=1
  3. `clipped.wav`: duration=30.0s, sr=24000, channels=1
  4. `dc_offset.wav`: duration=30.0s, sr=24000, channels=1
  5. `noisy_5db.wav`: duration=40.0s, sr=24000, channels=1

## 9. Sanity Checks
- [x] Output hours ≤ input hours
- [x] Every fixture audio file has non-zero size and valid WAV header
- [x] Config YAML round-trip matches in-memory hash exactly
- [x] No unhandled exceptions on missing CUDA / MPS devices (clean CPU fallback)

## 10. Exact Commands to Reproduce
```bash
# 1. Install dependencies
uv sync --all-extras --dev

# 2. Run linting & type checks
uv run ruff check .
uv run mypy audio_token_pipeline

# 3. Generate fixtures and run tests
uv run python tests/fixtures/generate_fixtures.py
uv run pytest --cov=audio_token_pipeline --cov-report=term-missing tests/

# 4. CLI status check
uv run atp info
uv run atp status
```

## 11. Known Issues and Limitations
- Live downloading of multi-gigabyte external datasets (LibriSpeech 100h) is gated by network sandbox during automated runs and will be executed via resumable CLI with explicit destination paths.
- Metal Performance Shaders (`mps`) reported `is_available: False` under the restricted sandboxed terminal runner on macOS; the unified `device.py` cleanly falls back to CPU as expected by design.

## 12. Reviewer Checklist
1. [x] Does `uv run pytest` pass cleanly on a fresh clone?
2. [x] Does `uv run ruff check .` report 0 errors?
3. [x] Does `uv run mypy audio_token_pipeline` report 0 errors?
4. [x] Are config hashes deterministic and reproducible across processes?
5. [x] Does DuckDB handle conflict updates idempotently?
6. [x] Is total fixture audio duration ≥ 5 minutes?
