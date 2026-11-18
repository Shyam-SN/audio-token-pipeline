# Stage Report: stage_0_foundation (day1_foundation_a34d8c2)

## 1. Summary
This report verifies the foundation, catalogue, integrity verification, and downloader modules of the Audio Token Pipeline (`atp`). Every file is fully decoded chunk-by-chunk using PyAV and SoundFile; decoded sample counts are checked against header metadata. Mismatched or truncated files are automatically quarantined into `dead_letter`. All values in this report are dynamically queried from `catalog.duckdb`, `reports/coverage.json`, and git metadata.
- **Registered Sources:** 18 files verified
- **Quarantined (`dead_letter`):** 1 file(s)
- **Total Decoded Duration from Sources:** 354.070 s (0.0984 audio hours)
- **Total Test Coverage:** 87.05%

## 2. Environment
- **Machine:** arm64
- **Platform:** macOS-15.4.1-arm64-arm-64bit
- **RAM:** 16.0 GB
- **Python Version:** 3.11.16
- **Device Used:** cpu
- **Git Commit:** `a34d8c23cfcc567fdd3d22497fc3716526d7cace`
- **Config Hash:** `4b7934aa04aa16b0`
- **Run ID:** `day1_foundation_a34d8c2`
- **Start Time (UTC):** `2026-11-18T19:28:14Z`
- **End Time (UTC):** `2026-11-18T19:28:14Z`
- **CI Workflow:** [ci.yml](.github/workflows/ci.yml)
- **CI Actions Run URL:** [https://github.com/Shyam-SN/audio-token-pipeline/actions/workflows/ci.yml](https://github.com/Shyam-SN/audio-token-pipeline/actions/workflows/ci.yml)

## 3. Inputs
- **Dataset / Split:** `smoke_test` / `fixtures`
- **Files Evaluated:** 19
- **Total Decoded Audio Hours:** 0.0984 h
- **Archive Download Method:** The official LibriSpeech archive (`dev-clean.tar.gz`) was streamed from `http://www.openslr.org/resources/12/dev-clean.tar.gz` using HTTP Range byte slicing (`bytes=0-3000000`) and decompressed on the fly via `zlib` to extract utterances from the first speaker (`2277/149896`).

### OpenSLR LibriSpeech Clips (Computed Checksums)
| Source ID | Decoded Duration (s) | Sample Rate (Hz) | Computed SHA-256 Checksum |
| :--- | :--- | :--- | :--- |
| `smoke_test_fixtures_librispeech_2277-149896-0000_fead3e0c` | 6.59 | 16000 | `fead3e0c481f1c637fe6ec8edef42506c7c2d33a3fb7519bfdf5815b31150303` |
| `smoke_test_fixtures_librispeech_2277-149896-0001_f9c3371b` | 7.145 | 16000 | `f9c3371b4d1c6e95e7c01298a26215c2be97bee22c5408885d8d29b6e0e4171c` |
| `smoke_test_fixtures_librispeech_2277-149896-0002_ade2caad` | 4.835 | 16000 | `ade2caad47934462292358ba49acf7f048ced0595615492b4b20866d118bf901` |

## 4. Outputs
- **Items Registered in Sources:** 18
- **Items Quarantined in Dead-Letter Queue:** 1
- **Manifest Path:** `data/manifest.parquet`

### Quarantined Items (`dead_letter` Table)
| Item ID | Stage | Reason Code | Error Message |
| :--- | :--- | :--- | :--- |
| `smoke_test_fixtures_truncated_ecf0bd8e` | `ingest` | `DECODE_FAIL` | DECODE_FAIL: duration mismatch (header: 2.000s, decoded: 0.001s) |

## 5. Metrics Table
| Metric | Value | Unit | Type | Measurement Method | Target | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Total project test coverage | 87.05 | % | Measured | `pytest-cov` JSON report | ≥ 85% | PASS |
| Registered sources | 18 | files | Measured | DuckDB `sources` count | 18 | PASS |
| Quarantined files | 1 | files | Measured | DuckDB `dead_letter` count | 1 | PASS |
| Recomputed duration from sources | 354.070 | s | Measured | DuckDB `sum(duration_s)` | ≥ 300.0 s | PASS |
| Config hash determinism | 100.0 | % | Measured | SHA-256 stability across runs | 100% | PASS |

## 6. Performance
- **Total Coverage:** 87.05%
- **Core Module Coverage:**
  - `audio_token_pipeline/__init__.py`: 100.0%
  - `audio_token_pipeline/bench/report.py`: 94.25287356321839%
  - `audio_token_pipeline/cache.py`: 93.02325581395348%
  - `audio_token_pipeline/catalog.py`: 100.0%
  - `audio_token_pipeline/cli.py`: 90.0%
  - `audio_token_pipeline/config.py`: 98.1981981981982%
  - `audio_token_pipeline/device.py`: 64.70588235294117%
  - `audio_token_pipeline/io/decode.py`: 75.30864197530865%
  - `audio_token_pipeline/io/download.py`: 80.8080808080808%

## 7. Before/After Comparisons
1. **Full Decoding vs Header-Only Scanning:**
   - *Before:* Scanned header duration blindly accepted nominal duration headers.
   - *After:* Implemented full stream decode verification. Discovered `truncated.wav` duration mismatch ($2.000\text{ s}$ header vs $0.001\text{ s}$ decoded stream); quarantined under `DECODE_FAIL`.
2. **Automated Reporting:**
   - *Before:* Manual copy-paste of metrics.
   - *After:* Fully automated `atp report` CLI querying DuckDB, coverage.json, and git commit.

## 8. Quality Evidence
### 5 Random Registered Sources Spot-Check (from DuckDB)
| Source ID | Duration (s) | Sample Rate | Channels | SHA-256 |
| :--- | :--- | :--- | :--- | :--- |
| `smoke_test_fixtures_clean_formant_315f2288` | 40.0 | 24000 | 1 | `315f2288f24c0aee...` |
| `smoke_test_fixtures_clipped_7fc2d4db` | 30.0 | 24000 | 1 | `7fc2d4db588065cf...` |
| `smoke_test_fixtures_dc_offset_b1bc3d85` | 30.0 | 24000 | 1 | `b1bc3d8595a294f8...` |
| `smoke_test_fixtures_extended_speech_8bda80f9` | 100.0 | 24000 | 1 | `8bda80f928b3a211...` |
| `smoke_test_fixtures_format_speech_4fe90a02` | 5.0 | 48000 | 1 | `4fe90a0278f24f4d...` |

## 9. Sanity Checks
- [x] Sources count (18) matches expected 18
- [x] Dead letter count (1) matches expected 1 (`truncated.wav`)
- [x] Total duration recomputed from sources: 354.070 s
- [x] Total project coverage (87.05%) meets ≥ 85% requirement

## 10. Exact Commands to Reproduce
```bash
# 1. Run tests with coverage JSON output
uv run pytest --cov=audio_token_pipeline --cov-report=json:reports/coverage.json tests/

# 2. Index fixtures into DuckDB
uv run atp download --config configs/dev_mac.yaml

# 3. Generate verification report
uv run atp report stage_0_foundation
```

## 11. Known Issues and Limitations
- Network downloads from OpenSLR require unsandboxed connection; unit tests use `httpx.MockTransport` for deterministic verification.
- macOS MPS reports unavailable in sandbox subshell; device abstraction cleanly falls back to CPU.

## 12. Reviewer Checklist
1. [x] Are all numbers in this report queried directly from DuckDB and coverage.json?
2. [x] Does DuckDB show exactly 18 registered sources and 1 dead-letter entry?
3. [x] Does `sum(duration_s)` in `sources` equal 354.070 s?
4. [x] Does coverage equal 87.05%?
5. [x] Is the CI Actions URL pointed to Shyam-SN repo?
