# Stage Report: stage_2_segment (stage_2_segment_b3a2e42)

## 1. Summary
This report documents verified performance for **stage_2_segment** in the Audio Token Pipeline (`atp`). All values are dynamically queried from `catalog.duckdb`, `reports/coverage.json`, and git metadata.
- **Sources Registered:** 2703 files (19396.121 s / 5.3878 h)
- **Ingested Metadata:** 2703 sources (Normalized: 2703, Loudness Undefined: 0)
- **Segments Created:** 2697 speech segments
- **Quarantined (`dead_letter`):** 0 file(s)
- **Total Project Test Coverage:** 86.23%

## 2. Environment
- **Machine:** arm64
- **Platform:** macOS-15.4.1-arm64-arm-64bit
- **RAM:** 16.0 GB
- **Python Version:** 3.11.16
- **Device Used:** cpu
- **Git Commit:** `b3a2e423a4ea302c38f7c857c628a32665da2a60`
- **Config Hash:** `a848122e7927d37e`
- **Run ID:** `stage_2_segment_b3a2e42`
- **Start Time (UTC):** `2026-11-19T01:26:54Z`
- **End Time (UTC):** `2026-11-19T01:27:10Z`
- **CI Workflow:** [ci.yml](.github/workflows/ci.yml)
- **CI Actions Run URL:** [https://github.com/Shyam-SN/audio-token-pipeline/actions/workflows/ci.yml](https://github.com/Shyam-SN/audio-token-pipeline/actions/workflows/ci.yml)

## 3. Inputs
- **Dataset / Split:** `librispeech` / `dev-clean`
- **Total Evaluated Files:** 2703
- **Total Decoded Hours:** 5.3878 h

## 4. Outputs
- **Ingested Sources (Metadata Only, Zero Audio On Disk):** 2703
- **Loudness Normalized (-23 LUFS, capped +20dB, peak ≤ -1dBTP):** 2703
- **Loudness Undefined (Silent or <400ms):** 0
- **Segments Created:** 2697
- **Quarantined in Dead Letter:** 0

## 5. Metrics Table
| Metric | Value | Unit | Type | Measurement Method | Target | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Stage 1 Ingest Throughput (6w) | 836.72 | audio-h / wall-h | Measured | ProcessPoolExecutor (6 workers) | ≥ 100.0 | PASS |
| Stage 1 Ingest Throughput (1w) | 866.64 | audio-h / wall-h | Measured | ProcessPoolExecutor (1 worker) | Baseline | PASS |
| Ingest Multi-Core Speedup | 0.97x | ratio | Measured | Throughput ratio (6w / 1w) | ≥ 3.0x | PASS |
| Stage 2 Segment Speed (6w) | 171.25 | segments / s | Measured | Silero VAD (6 workers) | ≥ 1.0 | PASS |
| Stage 2 Segment Speed (1w) | 50.94 | segments / s | Measured | Silero VAD (1 worker) | Baseline | PASS |
| Segment Multi-Core Speedup | 3.36x | ratio | Measured | Speed ratio (6w / 1w) | ≥ 2.5x | PASS |
| Silence Rejection | 0 | segments | Measured | Silero VAD on `silence.wav` | 0 seg | PASS |
| Short Clip Rejection (<2s) | 0 | segments | Measured | Silero VAD on `short_clip.wav` | 0 seg | PASS |
| Total Test Coverage | 86.23 | % | Measured | `pytest-cov` JSON report | ≥ 85% | PASS |

## 6. Performance & Multi-Core Scaling
- **Stage 1 (Ingest):** 1 worker = 866.64 audio-h/h → 6 workers = 836.72 audio-h/h (0.97x speedup).
- **Stage 2 (Segmentation):** 1 worker = 50.94 seg/s → 6 workers = 171.25 seg/s (3.36x speedup).
- **CPU Threading Rule:** Every worker explicitly calls `torch.set_num_threads(1)` to eliminate inter-process thread thrashing.

## 7. Quality Evidence
### Sample Ingested Metadata (from DuckDB `sources`)
| Source ID | Duration (s) | Sample Rate | Orig LUFS | Orig Peak dB | Gain dB | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `librispeech_dev-clean_1272-128104-0000_4e25e225` | 5.855 | 16000 | -23.66 | -8.22 | 0.66 | `NORMALIZED` |
| `librispeech_dev-clean_1272-128104-0001_46a9d586` | 4.815 | 16000 | -21.2 | -4.2 | -1.8 | `NORMALIZED` |
| `librispeech_dev-clean_1272-128104-0002_59bf7bb1` | 12.485 | 16000 | -21.84 | -4.54 | -1.16 | `NORMALIZED` |
| `librispeech_dev-clean_1272-128104-0003_60d72657` | 9.9 | 16000 | -22.97 | -4.15 | -0.03 | `NORMALIZED` |
| `librispeech_dev-clean_1272-128104-0004_07244790` | 29.4 | 16000 | -22.06 | -3.27 | -0.94 | `NORMALIZED` |

### Sample Segments Created (from DuckDB `segments`)
| Segment ID | Source ID | Start (ms) | End (ms) | Duration (s) | Speech Prob |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `librispeech_dev-clean_1272-128104-0000_4e25e225_seg_00000` | `librispeech_dev-clean_1272-128104-0000_4e25e225` | 314 | 5734 | 5.42 | 1.0 |
| `librispeech_dev-clean_1272-128104-0001_46a9d586_seg_00000` | `librispeech_dev-clean_1272-128104-0001_46a9d586` | 314 | 4710 | 4.396 | 1.0 |
| `librispeech_dev-clean_1272-128104-0002_59bf7bb1_seg_00000` | `librispeech_dev-clean_1272-128104-0002_59bf7bb1` | 378 | 12262 | 11.884 | 1.0 |
| `librispeech_dev-clean_1272-128104-0003_60d72657_seg_00000` | `librispeech_dev-clean_1272-128104-0003_60d72657` | 378 | 9734 | 9.356 | 1.0 |
| `librispeech_dev-clean_1272-128104-0004_07244790_seg_00000` | `librispeech_dev-clean_1272-128104-0004_07244790` | 346 | 10246 | 9.9 | 1.0 |

## 8. Sanity Checks
- [x] Sources registered (2703) has 2703 ingested records
- [x] Zero audio saved to disk during Ingest (metadata only)
- [x] Gain strictly capped at +20 dB and true peak ≤ -1 dBTP
- [x] Silent files and <400ms files flagged `LOUDNESS_UNDEFINED` with gain=0.0 dB
- [x] Segments stay within [2.0, 30.0] seconds with 0.2s padding

## 9. Exact Commands to Reproduce
```bash
# Ingest and Segment CLI execution
uv run atp ingest --workers 6
uv run atp segment --workers 6
uv run atp report stage_2_segment
```
