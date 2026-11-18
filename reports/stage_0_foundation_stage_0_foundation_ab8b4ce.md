# Stage Report: stage_0_foundation (stage_0_foundation_ab8b4ce)

## 1. Summary
This report documents verified performance for **stage_0_foundation** in the Audio Token Pipeline (`atp`). All values are dynamically queried from `catalog.duckdb`, `reports/coverage.json`, and git metadata.
- **Sources Registered:** 18 files (354.070 s / 0.0984 h)
- **Ingested Metadata:** 18 sources (Normalized: 16, Loudness Undefined: 2)
- **Segments Created:** 3 speech segments
- **Quarantined (`dead_letter`):** 1 file(s)
- **Total Project Test Coverage:** 86.23%

## 2. Environment
- **Machine:** arm64
- **Platform:** macOS-15.4.1-arm64-arm-64bit
- **RAM:** 16.0 GB
- **Python Version:** 3.11.16
- **Device Used:** cpu
- **Git Commit:** `ab8b4cee06f32afd5e20d9c152220975c7a2e388`
- **Config Hash:** `29265ee9e189fa8c`
- **Run ID:** `stage_0_foundation_ab8b4ce`
- **Start Time (UTC):** `2026-11-18T19:59:32Z`
- **End Time (UTC):** `2026-11-18T19:59:32Z`
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
- **Segments Created:** 3
- **Quarantined in Dead Letter:** 1

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
| `smoke_test_fixtures_clean_formant_315f2288` | 40.0 | 24000 | -16.06 | -6.63 | -6.94 | `NORMALIZED` |
| `smoke_test_fixtures_clipped_7fc2d4db` | 30.0 | 24000 | -1.19 | 0.0 | -21.81 | `NORMALIZED` |
| `smoke_test_fixtures_dc_offset_b1bc3d85` | 30.0 | 24000 | -17.93 | -12.04 | -5.07 | `NORMALIZED` |
| `smoke_test_fixtures_extended_speech_8bda80f9` | 100.0 | 24000 | -14.69 | -8.63 | -8.31 | `NORMALIZED` |
| `smoke_test_fixtures_format_speech_4fe90a02` | 5.0 | 48000 | -14.28 | -6.01 | -8.72 | `NORMALIZED` |

### Sample Segments Created (from DuckDB `segments`)
| Segment ID | Source ID | Start (ms) | End (ms) | Duration (s) | Speech Prob |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `smoke_test_fixtures_librispeech_2277-149896-0000_fead3e0c_seg_00000` | `smoke_test_fixtures_librispeech_2277-149896-0000_fead3e0c` | 90 | 6470 | 6.38 | 1.0 |
| `smoke_test_fixtures_librispeech_2277-149896-0001_f9c3371b_seg_00000` | `smoke_test_fixtures_librispeech_2277-149896-0001_f9c3371b` | 154 | 7110 | 6.956 | 1.0 |
| `smoke_test_fixtures_librispeech_2277-149896-0002_ade2caad_seg_00000` | `smoke_test_fixtures_librispeech_2277-149896-0002_ade2caad` | 346 | 4774 | 4.428 | 1.0 |

## 8. Sanity Checks
- [x] Sources registered (18) has 18 ingested records
- [x] Zero audio saved to disk during Ingest (metadata only)
- [x] Gain strictly capped at +20 dB and true peak ≤ -1 dBTP
- [x] Silent files and <400ms files flagged `LOUDNESS_UNDEFINED` with gain=0.0 dB
- [x] Segments stay within [2.0, 30.0] seconds with 0.2s padding

## 9. Exact Commands to Reproduce
```bash
# Ingest and Segment CLI execution
uv run atp ingest --workers 6
uv run atp segment --workers 6
uv run atp report stage_0_foundation
```
