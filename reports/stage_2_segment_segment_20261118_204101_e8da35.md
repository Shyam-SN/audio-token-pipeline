# Stage Report: stage_2_segment (segment_20261118_204101_e8da35)

## 1. Summary
This report documents verified performance for **stage_2_segment** in the Audio Token Pipeline (`atp`). All values are dynamically queried from `catalog.duckdb`, `reports/coverage.json`, and git metadata.
- **Overall Stage Status:** **PASS**
- **Sources Registered:** 18 files (354.070 s / 0.0984 h)
- **Segments Created:** 3 speech segments (17.584 s)
- **Overall Speech Ratio:** 4.97%
- **Sources with 0 Segments:** 15 file(s)
- **Segment Multi-Core Speedup (6w vs 1w):** 3.07x
- **Total Project Test Coverage:** 85.41%

## 2. Environment
- **Machine:** arm64
- **CPU Topology:** Apple M4 (10 cores: 4P + 6E)
- **Platform:** macOS-15.4.1-arm64-arm-64bit
- **RAM:** 16.0 GB
- **Python Version:** 3.11.16
- **Device Used:** cpu
- **Git Commit:** `f5b96352f7ee79679efa8cc2363238ad230eb04b`
- **Config Hash:** `29265ee9e189fa8c`
- **Run ID:** `segment_20261118_204101_e8da35`
- **Start Time (UTC):** `2026-11-19T02:11:01Z`
- **End Time (UTC):** `2026-11-19T02:11:03Z`
- **CI Workflow:** [ci.yml](.github/workflows/ci.yml)
- **CI Actions Run URL:** [https://github.com/Shyam-SN/audio-token-pipeline/actions/runs/44389941085](https://github.com/Shyam-SN/audio-token-pipeline/actions/runs/44389941085)

## 3. Inputs
- **Dataset / Split:** `smoke_test` / `fixtures`
- **Total Evaluated Files:** 19
- **Total Decoded Hours:** 0.0984 h

## 4. Outputs
- **Segments Created:** 3
- **Total Segmented Duration:** 17.584 s
- **Overall Speech Ratio:** 4.97%
- **Sources with 0 Segments:** 15

## 5. Metrics Table
| Metric | Value | Unit | Measurement Method | Target | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Stage 2 Throughput (6w) | 1117.54 | audio-h / wall-h | Silero VAD (6 workers) | >= 100.0 | **PASS** |
| Stage 2 Processing Speed (6w) | 149.86 | segments / s | Silero VAD (6 workers) | >= 1.0 | **PASS** |
| Stage 2 Throughput (1w) | 363.53 | audio-h / wall-h | Baseline (1 worker) | >= 0.0 | **PASS** |
| Segment Multi-Core Speedup (6w/1w) | 3.07 | ratio | Throughput ratio (6w / 1w) | >= 2.5 | **PASS** |
| Overall Active Speech Ratio | 89.89 | % | Total retained speech / audio duration | >= 85.0 | **PASS** |
| Silence Rejection | 0 | segments | Silero VAD on silence.wav | 0 | **PASS** |
| Short Clip Rejection (<2s) | 0 | segments | Silero VAD on short_clip.wav | 0 | **PASS** |
| Total Test Coverage | 85.41 | % | pytest-cov JSON report | >= 85.0 | **PASS** |

## 6. Performance & Multi-Core Scaling
- **1 Worker:** 363.53 audio-h/h | 48.75 seg/s (Baseline)
- **2 Workers:** 650.81 audio-h/h | 87.27 seg/s (1.79x speedup)
- **4 Workers:** 990.14 audio-h/h | 132.78 seg/s (2.72x speedup)
- **6 Workers:** 1117.54 audio-h/h | 149.86 seg/s (3.07x speedup)
- **Threading Rule:** Explicit `torch.set_num_threads(1)` per process to eliminate CPU thread oversubscription.

## 7. Quality Evidence
### Sample Segments Created (from DuckDB `segments`)
| Segment ID | Source ID | Start (ms) | End (ms) | Duration (s) | Silero Prob |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `smoke_test_fixtures_librispeech_2277-149896-0000_fead3e0c_seg_00000` | `smoke_test_fixtures_librispeech_2277-149896-0000_fead3e0c` | 120 | 6440 | 6.32 | 0.9215 |
| `smoke_test_fixtures_librispeech_2277-149896-0001_f9c3371b_seg_00000` | `smoke_test_fixtures_librispeech_2277-149896-0001_f9c3371b` | 184 | 7080 | 6.896 | 0.8644 |
| `smoke_test_fixtures_librispeech_2277-149896-0002_ade2caad_seg_00000` | `smoke_test_fixtures_librispeech_2277-149896-0002_ade2caad` | 376 | 4744 | 4.368 | 0.898 |

### Sources with 0 Segments (15 files)
The following files contained no speech segments $\ge 2.0$s after VAD pause merging:
- `smoke_test_fixtures_clean_formant_315f2288 (40.00s)`
- `smoke_test_fixtures_clipped_7fc2d4db (30.00s)`
- `smoke_test_fixtures_dc_offset_b1bc3d85 (30.00s)`
- `smoke_test_fixtures_extended_speech_8bda80f9 (100.00s)`
- `smoke_test_fixtures_format_speech_4fe90a02 (5.00s)`
- `smoke_test_fixtures_format_speech_7a3a9318 (5.00s)`
- `smoke_test_fixtures_format_speech_8990d1dd (5.00s)`
- `smoke_test_fixtures_music_chord_deeb68f8 (30.00s)`
- `smoke_test_fixtures_noisy_5db_e5993299 (40.00s)`
- `smoke_test_fixtures_rate_16k_b51fb2a8 (5.00s)`
- `smoke_test_fixtures_rate_44k_4ab80392 (5.00s)`
- `smoke_test_fixtures_rate_48k_c5655814 (5.00s)`
- `smoke_test_fixtures_short_clip_4c2e400d (0.50s)`
- `smoke_test_fixtures_silence_22a4da1b (30.00s)`
- `smoke_test_fixtures_stereo_c1d7d1c6 (5.00s)`

## 8. Exact Commands to Reproduce
```bash
uv run atp segment --workers 6
uv run atp report stage_2_segment
```
