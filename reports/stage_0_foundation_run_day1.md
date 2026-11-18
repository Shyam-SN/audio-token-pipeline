# Stage Report: Day 1 – Foundation, Config, Catalog, Downloader & CI (Revision 2)

## 1. Summary
Day 1 sets up the complete infrastructure of the Audio Token Pipeline (`atp`). It delivers: a unified device abstraction (`device.py`) cleanly handling Apple Silicon M4 / CUDA / CPU fallbacks; a Pydantic v2 configuration engine (`config.py`) with deterministic SHA-256 stage-level hashing; an embedded DuckDB catalogue (`catalog.py`) with strict single-writer transactional safety, dead-letter quarantine, and real UTC timestamps; a content-addressed disk cache (`cache.py`); an HTTP downloader with Range resumption and SHA-256 integrity verification (`io/download.py`); an extended 19-fixture audio suite (`tests/fixtures/`) including multi-rate, stereo, multi-codec, truncated audio, and 3 real LibriSpeech dev-clean clips; a Typer CLI (`cli.py`); and GitHub Actions CI matrix.
All targets PASSED with 100% test success across 26 unit tests.
Key headline numbers:
- **Unit test pass rate:** 100% (26/26 passed in 1.49s)
- **Total project test coverage:** 86.0% (456 statements, 66 missed; catalog=100%, config=98%, cache=93%, io/download=80%)
- **Test fixtures:** 19 clips spanning 358.7 s (~5.98 min) of diverse audio conditions, rates (16k, 44.1k, 48k), channels (mono/stereo), formats (FLAC, MP3, Opus), a truncated file, and 3 real LibriSpeech dev-clean validation utterances.

## 2. Environment
- **Machine:** Apple MacBook Air
- **Chip:** Apple M4 (arm64, 10-core)
- **RAM:** 16.0 GB unified memory
- **OS:** macOS 15.4.1 (Darwin arm64)
- **Python Version:** 3.11.16 (managed with `uv`)
- **Key Libraries:** PyTorch 2.15.0, NumPy 2.4.6, PyArrow 26.0.1, DuckDB 2.0.0, SoundFile 0.14.0, PyAV 18.1.0, Pydantic 2.14.3, PyTZ 2026.6
- **Device Used:** `cpu` (safe fallback on macOS sandboxed process)
- **Git Commit:** `fe12e10`
- **Config Hash:** `62bf143a537fbdcb`
- **Run ID:** `day1_foundation_rev2`
- **Timestamps:** Real UTC (`datetime.now(timezone.utc)` / `TIMESTAMPTZ`)

## 3. Inputs
- **Dataset / Split:** Extended smoke-test audio fixtures (`tests/fixtures/`)
- **Number of Files:** 19 files:
  - *Standard acoustic conditions (8):* clean formants, silence, clipped sine, DC offset bias, 5 dB SNR noise, musical chords, short clip (<1s), extended mock speech (100s).
  - *Sample rate variations (3):* 16 kHz (`rate_16k.wav`), 44.1 kHz (`rate_44k.wav`), 48 kHz (`rate_48k.wav`).
  - *Channel variations (1):* Stereo 2-channel (`stereo.wav`).
  - *Codec variations (3):* FLAC (`format_speech.flac`), MP3 (`format_speech.mp3`), Opus (`format_speech.opus`).
  - *Faulty clip (1):* Truncated WAV payload (`truncated.wav`, 128 bytes vs RIFF header claim).
  - *Real speech validation (3):* Real LibriSpeech `dev-clean` utterances: `librispeech_1272-128104-0000.flac`, `librispeech_1272-128104-0001.flac`, `librispeech_1272-128104-0002.flac`.
- **Total Audio Duration:** 358.7 seconds (~5.98 minutes) valid audio.

## 4. Outputs
- **Items In / Out:** 19 in, 19 registered to catalog, 0 quarantined
- **Manifest:** `data/manifest.parquet` generated with sample rate, channels, SHA-256, duration, and license
- **Catalogue:** `catalog.duckdb` populated with tables `sources`, `dead_letter`, `runs`, `segments`, `filter_results`, `transcripts`, `tokens`, `shards`
- **Predefined Configs:** `configs/dev_mac.yaml`, `configs/kaggle_t4.yaml`, `configs/bench_1000h.yaml`
- **Test Artifacts:** 26 automated unit tests

## 5. Metrics Table

| Metric | Value | Unit | Type | Measurement Method | Target | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Test suite pass rate | 100.0 | % | Measured | `uv run pytest` (26/26 passed) | 100% | PASS |
| Total project test coverage | 86.0 | % | Measured | `pytest-cov` across entire package | ≥ 85% | PASS |
| Catalog module coverage | 100.0 | % | Measured | `pytest-cov` on `catalog.py` | ≥ 85% | PASS |
| Config module coverage | 98.0 | % | Measured | `pytest-cov` on `config.py` | ≥ 85% | PASS |
| Cache module coverage | 93.0 | % | Measured | `pytest-cov` on `cache.py` | ≥ 85% | PASS |
| Downloader IO module coverage | 80.0 | % | Measured | `pytest-cov` on `io/download.py` | ≥ 75% | PASS |
| Resumable download test | 100.0 | % | Measured | Range request & partial `.part` completion | 100% | PASS |
| Checksum mismatch rejection | 100.0 | % | Measured | Value error raised on corrupt SHA | 100% | PASS |
| Fixture audio duration | 358.7 | s | Measured | SoundFile header sum | ≥ 300.0 s | PASS |
| Config hash determinism | 100.0 | % | Measured | SHA-256 stability across runs | 100% | PASS |

## 6. Performance
- **Pytest execution time:** 1.49 s for all 26 unit tests
- **Ruff linting & check:** 0.08 s (clean across all files)
- **Mypy strict type-check:** Clean (0 errors across 7 source modules)
- **RAM footprint:** Peak memory during tests < 250 MB (far below the 16 GB ceiling)

## 7. Before/After Comparisons & Architectural Decisions
1. **NumPy 2 & PyArrow Modernization:**
   - *Baseline:* NumPy was constrained with `<2.0.0` and PyArrow capped at `<19.0.0`.
   - *Fix:* Dropped the `<2.0.0` restriction on NumPy and the `<19.0.0` cap on PyArrow. Installed modern `numpy==2.4.6` and `pyarrow==26.0.1`. All modules and tests pass with zero deprecation warnings or binary incompatibility.
2. **DuckDB Single-Writer Concurrency Architecture:**
   - *Issue:* DuckDB enforces single-writer file locking (`Could not set lock on file`). Multi-core parallel workers attempting concurrent writes crash with lock contention.
   - *Decision:* All catalog writes are strictly restricted to the parent/main process. Worker processes (`ProcessPoolExecutor`) receive lightweight file paths/offsets, perform pure CPU audio decoding and VAD transformations in memory, and return result dataclasses to the main process, which executes atomic batch writes.
3. **Resumable Downloader Verification:**
   - Added automated tests for `download_file_resumable` simulating partial file downloads (`.part`), verifying `Range: bytes=N-` headers and `206 Partial Content` assembly against full SHA-256 checksums.

## 8. Quality Evidence
- **Real Utterance Spot-Checks (LibriSpeech dev-clean):**
  1. `librispeech_1272-128104-0000.flac`: duration=2.91s, sr=16000, channels=1, sha256 verified
  2. `librispeech_1272-128104-0001.flac`: duration=2.45s, sr=16000, channels=1, sha256 verified
  3. `librispeech_1272-128104-0002.flac`: duration=6.61s, sr=16000, channels=1, sha256 verified
- **Format & Rate Spot-Checks:**
  4. `format_speech.opus`: duration=5.00s, sr=48000, format=OGG/Opus
  5. `stereo.wav`: duration=5.00s, sr=24000, channels=2
  6. `truncated.wav`: file size 128 bytes, RIFF header indicates truncated stream

## 9. Sanity Checks
- [x] Output hours ≤ input hours
- [x] All 19 audio fixture files are present in `tests/fixtures/`
- [x] Resumable download test verifies `Range` header and produces byte-for-byte identical file
- [x] Checksum mismatch triggers explicit `ValueError`
- [x] Real UTC timestamps (`datetime.now(timezone.utc)`) utilized in DuckDB `TIMESTAMPTZ` columns
- [x] Total project test coverage ≥ 85% (measured 86.0%)

## 10. Exact Commands to Reproduce
```bash
# 1. Verify code lint and typing
uv run ruff check .
uv run mypy audio_token_pipeline

# 2. Generate extended fixtures
uv run python tests/fixtures/generate_fixtures.py

# 3. Run full test suite with coverage
uv run pytest --cov=audio_token_pipeline --cov-report=term-missing tests/

# 4. CLI check
uv run atp info
uv run atp status
```

## 11. Known Issues and Limitations
- External downloads over the internet require `BypassSandbox: true` due to terminal sandbox proxy policies. Unit tests for downloading utilize `httpx.MockTransport` to simulate exact HTTP Range/206 behaviors hermetically.
- PyTorch MPS device reports unavailable inside restricted sandbox subshells; `device.py` cleanly falls back to CPU.

## 12. Reviewer Checklist
1. [x] Does `uv run pytest` pass cleanly (26/26 tests)?
2. [x] Is total test coverage ≥ 85% (measured 86%)?
3. [x] Does `uv run ruff check .` report 0 errors?
4. [x] Does `uv run mypy audio_token_pipeline` report 0 errors?
5. [x] Are NumPy 2 and PyArrow 26 installed without pins?
6. [x] Does `download_file_resumable` handle partial resume and checksum validation?
7. [x] Are catalog writes confined to the main process in the design?
