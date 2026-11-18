# Stage Report: stage_2_segment (segment_20261118_202430_30ef4e)

## 1. Summary
This report documents verified performance for **stage_2_segment** in the Audio Token Pipeline (`atp`). All values are dynamically queried from `catalog.duckdb`, `reports/coverage.json`, and git metadata.
- **Overall Stage Status:** **PASS**
- **Sources Registered:** 2703 files (19396.121 s / 5.3878 h)
- **Segments Created:** 2676 speech segments (18374.625 s)
- **Overall Speech Ratio:** 94.73%
- **Sources with 0 Segments:** 37 file(s)
- **Segment Multi-Core Speedup (6w vs 1w):** 3.07x
- **Total Project Test Coverage:** 85.44%

## 2. Environment
- **Machine:** arm64
- **CPU Topology:** Apple M4 (10 cores: 4P + 6E)
- **Platform:** macOS-15.4.1-arm64-arm-64bit
- **RAM:** 16.0 GB
- **Python Version:** 3.11.16
- **Device Used:** cpu
- **Git Commit:** `f469f8662e698277cf402096edd88190a6809aa7`
- **Config Hash:** `a848122e7927d37e`
- **Run ID:** `segment_20261118_202430_30ef4e`
- **Start Time (UTC):** `2026-11-19T01:54:30Z`
- **End Time (UTC):** `2026-11-19T01:54:46Z`
- **CI Workflow:** [ci.yml](.github/workflows/ci.yml)
- **CI Actions Run URL:** [https://github.com/Shyam-SN/audio-token-pipeline/actions/runs/44389941085](https://github.com/Shyam-SN/audio-token-pipeline/actions/runs/44389941085)

## 3. Inputs
- **Dataset / Split:** `librispeech` / `dev-clean`
- **Total Evaluated Files:** 2703
- **Total Decoded Hours:** 5.3878 h

## 4. Outputs
- **Segments Created:** 2676
- **Total Segmented Duration:** 18374.625 s
- **Overall Speech Ratio:** 94.73%
- **Sources with 0 Segments:** 37

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
| Total Test Coverage | 85.44 | % | pytest-cov JSON report | >= 85.0 | **PASS** |

## 6. Performance & Multi-Core Scaling
- **1 Worker:** 363.53 audio-h/h | 48.75 seg/s (Baseline)
- **2 Workers:** 650.81 audio-h/h | 87.27 seg/s (1.79x speedup)
- **4 Workers:** 990.14 audio-h/h | 132.78 seg/s (2.72x speedup)
- **6 Workers:** 1117.54 audio-h/h | 149.86 seg/s (3.07x speedup)
- **Threading Rule:** Explicit `torch.set_num_threads(1)` per process to eliminate CPU thread oversubscription.

## 7. Quality Evidence
### 29.4s File Verification (`1272-128104-0004`)
| Segment ID | Source ID | Start (ms) | End (ms) | Duration (s) | Silero Prob | Speech Coverage |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `librispeech_dev-clean_1272-128104-0004_07244790_seg_00000` | `librispeech_dev-clean_1272-128104-0004_07244790` | 376 | 29288 | 28.912 | 0.8437 | **98.34%** |

### Sample Segments Created (from DuckDB `segments`)
| Segment ID | Source ID | Start (ms) | End (ms) | Duration (s) | Silero Prob |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `librispeech_dev-clean_1272-128104-0000_4e25e225_seg_00000` | `librispeech_dev-clean_1272-128104-0000_4e25e225` | 344 | 5704 | 5.36 | 0.9137 |
| `librispeech_dev-clean_1272-128104-0001_46a9d586_seg_00000` | `librispeech_dev-clean_1272-128104-0001_46a9d586` | 344 | 4680 | 4.336 | 0.9004 |
| `librispeech_dev-clean_1272-128104-0002_59bf7bb1_seg_00000` | `librispeech_dev-clean_1272-128104-0002_59bf7bb1` | 408 | 12232 | 11.824 | 0.9012 |
| `librispeech_dev-clean_1272-128104-0003_60d72657_seg_00000` | `librispeech_dev-clean_1272-128104-0003_60d72657` | 408 | 9704 | 9.296 | 0.9094 |
| `librispeech_dev-clean_1272-128104-0004_07244790_seg_00000` | `librispeech_dev-clean_1272-128104-0004_07244790` | 376 | 29288 | 28.912 | 0.8437 |

### Sources with 0 Segments (37 files)
The following files contained no speech segments $\ge 2.0$s after VAD pause merging:
- `librispeech_dev-clean_1272-135031-0009_d23fc0e9 (1.91s)`
- `librispeech_dev-clean_1272-135031-0014_659d4e11 (1.74s)`
- `librispeech_dev-clean_1272-141231-0013_ff87e7b4 (1.64s)`
- `librispeech_dev-clean_1272-141231-0016_2de6e800 (1.85s)`
- `librispeech_dev-clean_174-50561-0014_2ecc03fb (1.80s)`
- `librispeech_dev-clean_1919-142785-0021_939c9884 (1.69s)`
- `librispeech_dev-clean_1919-142785-0048_3ba33cd0 (1.84s)`
- `librispeech_dev-clean_1988-24833-0006_3de779f6 (1.98s)`
- `librispeech_dev-clean_2035-147960-0015_c9e80b5c (1.56s)`
- `librispeech_dev-clean_2035-147961-0033_07d67e4e (1.95s)`
- `librispeech_dev-clean_2078-142845-0023_591f2d39 (1.75s)`
- `librispeech_dev-clean_2277-149896-0004_ed54e3c1 (1.96s)`
- `librispeech_dev-clean_2412-153947-0012_beb040bc (1.98s)`
- `librispeech_dev-clean_2428-83699-0004_660b675c (1.88s)`
- `librispeech_dev-clean_2428-83699-0009_d52c7a39 (1.85s)`
- `librispeech_dev-clean_2428-83699-0022_b9a64c72 (1.98s)`
- `librispeech_dev-clean_2428-83699-0039_1af6fd1e (1.98s)`
- `librispeech_dev-clean_2428-83705-0036_b89243a2 (1.96s)`
- `librispeech_dev-clean_251-136532-0022_05dd269b (1.53s)`
- `librispeech_dev-clean_3081-166546-0008_9100b854 (1.77s)`
- *...and 17 more.*

## 8. Exact Commands to Reproduce
```bash
uv run atp segment --workers 6
uv run atp report stage_2_segment
```
