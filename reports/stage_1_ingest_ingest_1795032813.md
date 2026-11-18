# Stage Report: stage_1_ingest (ingest_1795032813)

## 1. Summary
This report documents verified performance for **stage_1_ingest** in the Audio Token Pipeline (`atp`). All values are dynamically queried from `catalog.duckdb`, `reports/coverage.json`, and git metadata.
- **Overall Stage Status:** **FAIL**
- **Sources Registered:** 18 files (354.070 s / 0.0984 h)
- **Ingested Metadata:** 18 sources (Normalized: 16, Loudness Undefined: 2)
- **Ingest Multi-Core Speedup (6w vs 1w):** 1.91x
- **Quarantined (`dead_letter`):** 1 file(s)
- **Total Project Test Coverage:** 86.34%

## 2. Environment
- **Machine:** arm64
- **Platform:** macOS-15.4.1-arm64-arm-64bit
- **RAM:** 16.0 GB
- **Python Version:** 3.11.16
- **Device Used:** cpu
- **Git Commit:** `f36ae1a909344b9b0dc80e238c80e5905b979dfe`
- **Config Hash:** `90d1fc24d6bd94fc`
- **Run ID:** `ingest_1795032813`
- **Start Time (UTC):** `2026-11-19T01:43:33Z`
- **End Time (UTC):** `2026-11-19T01:43:33Z`
- **CI Workflow:** [ci.yml](.github/workflows/ci.yml)
- **CI Actions Run URL:** [https://github.com/Shyam-SN/audio-token-pipeline/actions/workflows/ci.yml](https://github.com/Shyam-SN/audio-token-pipeline/actions/workflows/ci.yml)

## 3. Inputs
- **Dataset / Split:** `smoke_test` / `fixtures`
- **Total Evaluated Files:** 19
- **Total Decoded Hours:** 0.0984 h

## 4. Outputs
- **Ingested Sources (Metadata Only, Zero Audio On Disk):** 18
- **Loudness Normalized (-23 LUFS, capped +20dB, peak ≤ -1dBTP):** 16
- **Loudness Undefined (Silent or <400ms):** 2
- **Quarantined in Dead Letter:** 1

## 5. Metrics Table
| Metric | Value | Unit | Measurement Method | Target | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Stage 1 Ingest Throughput (6w) | 4556.78 | audio-h / wall-h | ProcessPoolExecutor (6 workers) | >= 100.0 | **PASS** |
| Stage 1 Ingest Throughput (4w) | 4845.87 | audio-h / wall-h | ProcessPoolExecutor (4 workers) | >= 80.0 | **PASS** |
| Stage 1 Ingest Throughput (2w) | 3621.7 | audio-h / wall-h | ProcessPoolExecutor (2 workers) | >= 50.0 | **PASS** |
| Stage 1 Ingest Throughput (1w) | 2385.21 | audio-h / wall-h | Baseline (1 worker) | >= 0.0 | **PASS** |
| Ingest Multi-Core Speedup (6w/1w) | 1.91 | ratio | Throughput ratio (6w / 1w) | >= 3.0 | **FAIL** |
| Loudness Normalized Sources | 16 | sources | DuckDB sources query | 18 | **FAIL** |
| Loudness Undefined Sources | 2 | sources | DuckDB sources query | 0 | **FAIL** |
| Ingest Quarantined (Dead Letter) | 1 | files | DuckDB dead_letter query | 0 | **FAIL** |
| Total Test Coverage | 86.34 | % | pytest-cov JSON report | >= 85.0 | **PASS** |

## 6. Performance & Multi-Core Scaling
- **1 Worker:** 2385.21 audio-h/h (Baseline)
- **2 Workers:** 3621.7 audio-h/h (1.52x speedup)
- **4 Workers:** 4845.87 audio-h/h (2.03x speedup)
- **6 Workers:** 4556.78 audio-h/h (1.91x speedup)
- **Optimization Applied:** Batched DuckDB writes via `con.executemany`, chunked IPC task submission, and lightweight worker process initialization.

## 7. Quality Evidence
### Sample Ingested Metadata (from DuckDB `sources`)
| Source ID | Duration (s) | Sample Rate | Orig LUFS | Orig Peak dB | Gain dB | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `smoke_test_fixtures_clean_formant_315f2288` | 40.0 | 24000 | -16.06 | -6.63 | -6.94 | `NORMALIZED` |
| `smoke_test_fixtures_clipped_7fc2d4db` | 30.0 | 24000 | -1.19 | 0.0 | -21.81 | `NORMALIZED` |
| `smoke_test_fixtures_dc_offset_b1bc3d85` | 30.0 | 24000 | -17.93 | -12.04 | -5.07 | `NORMALIZED` |
| `smoke_test_fixtures_extended_speech_8bda80f9` | 100.0 | 24000 | -14.69 | -8.63 | -8.31 | `NORMALIZED` |
| `smoke_test_fixtures_format_speech_4fe90a02` | 5.0 | 48000 | -14.28 | -6.01 | -8.72 | `NORMALIZED` |

## 8. Exact Commands to Reproduce
```bash
uv run atp ingest --workers 6
uv run atp report stage_1_ingest
```
