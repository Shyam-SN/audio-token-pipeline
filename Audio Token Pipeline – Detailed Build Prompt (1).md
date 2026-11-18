# Audio Token Pipeline – Detailed Build Prompt

Paste everything below into Claude Code (or any coding assistant) as the project brief.

## 1. Role and goal

You are a senior ML infrastructure engineer and my pair programmer. Together we will build **Audio Token Pipeline**, an open-source, production-quality pipeline that turns raw audio into training-ready speech codec tokens at high throughput.

The purpose is a portfolio project that proves, with hard numbers, that I can own the audio data pipeline of a company training generalist speech foundation models on millions of hours of audio (target company: Kalpa Labs, YC F25). Every design choice must be measured. The README must open with results, not prose.

Success means a founder can open the repo and, in 60 seconds, see: hours processed, throughput (audio hours per wall-clock hour), real-time factor per stage, GPU utilisation, filter precision/recall, and cost per 1,000 hours with a 1M-hour projection.

## 2. Hardware and environment constraints

- **Development machine:** MacBook, Apple M4, 16 GB unified memory, macOS. No CUDA locally.
- **Mac acceleration:** use MLX (mlx-whisper) and PyTorch MPS where they help; fall back to CPU cleanly.
- **Scale benchmark:** Kaggle notebook, single NVIDIA T4 or P100 (about 30 free GPU-hours/week). Optional paid run on RunPod/Vast.ai (A100/L4) only if budget allows; design so it is optional.
- **Device abstraction:** one `device` setting (`cpu | mps | cuda`) in config; every model-loading function goes through a single `get_device()` helper.
- **Memory rule:** never load a full audio file into memory; stream decode. Flag any step that could exceed 16 GB and propose a workaround before writing it.
- **Python:** 3.11, managed with `uv`. Pin all dependencies in a lockfile.
- **OS portability:** code must run on macOS (dev), Linux (Kaggle/Docker), and in CPU-only GitHub Actions CI.

## 3. Datasets

1. **Smoke test:** a 5-minute fixture bundled in `tests/fixtures/` (mix of clean speech, silence, music, clipped and noisy clips).
2. **Development:** LibriSpeech `dev-clean`, `dev-other`, then `train-clean-100` (\~100 h).
3. **Scale benchmark:** a 1,000+ hour slice of LibriLight (or Common Voice / multilingual alternative if licensing or download size is a problem). Add a multilingual slice (e.g. Common Voice Hindi or Tamil, \~50 h) to show language handling.
4. **Downloader requirements:** resumable downloads, SHA-256 verification against published checksums, parallel fetching, a `--max-hours` cap, and a local manifest (`data/manifest.parquet`) listing every source file with duration, sample rate, codec and checksum.
5. **Licensing:** record each dataset's license in the manifest and README.

## 4. Repository structure

```
audio-token-pipeline/
  pyproject.toml
  uv.lock
  README.md
  Dockerfile
  configs/
    dev_mac.yaml
    kaggle_t4.yaml
    bench_1000h.yaml
  audio_token_pipeline/
    __init__.py
    cli.py
    config.py            # Pydantic models for all configs
    device.py            # get_device(), backend detection
    catalog.py           # DuckDB catalogue
    cache.py             # content-addressed cache
    io/
      download.py
      decode.py          # PyAV streaming decode
    stages/
      ingest.py
      segment.py
      filter.py
      transcribe.py
      tokenize.py
      shard.py
    feed/
      dataset.py         # streaming IterableDataset
      train_probe.py     # dummy training loop for starvation tests
    bench/
      profiler.py
      metrics.py
      cost_model.py
      report.py
    qa/
      fault_injection.py
      filter_eval.py
  tests/
    unit/
    integration/
    fixtures/
  notebooks/
    kaggle_benchmark.ipynb
  docs/
    design_decisions.md
    runbook.md
    writeup.md
  .github/workflows/ci.yml
```

## 5. Core engineering principles

- **Every stage is independent, idempotent and resumable.** A stage reads from the catalogue, processes only items not yet done, writes outputs, and marks completion atomically.
- **Content-addressed caching:** cache key = SHA-256 of (input content hash + stage name + stage config hash + code version). Changing one stage's config re-runs only that stage and downstream.
- **Single source of truth:** a DuckDB catalogue (`catalog.duckdb`) with tables for `sources`, `segments`, `filter_results`, `transcripts`, `tokens`, `shards`, `runs`.
- **Structured logging:** JSON logs with run ID, stage, item ID, duration and outcome.
- **Fail loudly, quarantine quietly:** corrupt or failing items go to a dead-letter table with an error code, never crash the run.
- **Simple, general, scalable methods** over clever special cases.
- **Measure before optimising.** No optimisation lands without before/after numbers in `docs/design_decisions.md`.

## 6. Pipeline stages in detail

Build in this order. Each stage has a CLI command, a config block, unit tests, and a throughput metric.

### Stage 1 – Ingest (`atp ingest`)

- Decode flac, mp3, opus, ogg, m4a and wav with PyAV in streaming chunks; ffmpeg CLI only as fallback.
- Resample to **24 kHz mono float32** (Mimi's native rate); keep a 16 kHz copy only if a downstream model needs it, computed on the fly, never stored.
- Loudness-normalise to -23 LUFS (EBU R128) with pyloudnorm; record original LUFS and peak in the catalogue.
- Reject unreadable or zero-length files into the dead-letter table with codes `DECODE_FAIL`, `EMPTY`, `BAD_RATE`.
- Parallelism: `ProcessPoolExecutor` sized to performance cores; pass **file paths, not arrays**, between processes.
- Metric: audio hours decoded per wall-clock hour; CPU utilisation per core.

### Stage 2 – Segmentation (`atp segment`)

- Silero VAD (ONNX runtime for speed on CPU) at 16 kHz on a downsampled view.
- Merge speech regions into segments of **2–30 s**, padding 0.2 s each side, splitting long regions at the lowest-energy point.
- Store segments as (source\_id, start\_ms, end\_ms), not as new audio files; audio is sliced lazily downstream.
- Metric: segments per second, speech ratio per source, segment length histogram.

### Stage 3 – Quality filtering (`atp filter`)

Each filter returns a score and pass/fail with a reason code. All thresholds live in config.

| Filter | Method | Reason code |
| --- | --- | --- |
| Silence ratio | frame energy below threshold > 40% | `TOO_SILENT` |
| Clipping | fraction of samples at ±0.999 > 0.1% | `CLIPPED` |
| SNR estimate | WADA-SNR or energy-based estimate < 10 dB | `LOW_SNR` |
| DC offset | mean amplitude > 0.01 | `DC_OFFSET` |
| Duration | outside 2–30 s | `BAD_LENGTH` |
| Near-duplicate | Chromaprint fingerprint or embedding cosine > 0.95 | `DUPLICATE` |
| Non-speech / music | small audio classifier (e.g. PANNs or YAMNet) speech prob < 0.6 | `NOT_SPEECH` |
| Language mismatch | Whisper language ID differs from expected | `WRONG_LANG` |

**Fault-injection evaluation (this is a headline result):**

1. Take 1,000 clean clips and generate corrupted copies: hard clipping, added white/pink/babble noise at 0–5 dB SNR, inserted silence, DC shift, truncated files, exact and near duplicates (re-encoded, pitch-shifted 1%), music overlays.
2. Run all filters; report **precision, recall and F1 per filter** and an overall confusion matrix.
3. Target: ≥ 95% recall on every injected fault with ≤ 2% false rejections of clean audio.
4. Save results to `bench/results/filter_eval.json` and a chart in the README.

### Stage 4 – Transcription and alignment (`atp transcribe`)

- Mac: `mlx-whisper` with `large-v3-turbo`. CUDA: `faster-whisper` (CTranslate2, float16 or int8).
- **Length-bucketed batching**: sort segments by duration and batch similar lengths to cut padding waste; report padding % before and after.
- Store text, detected language, avg log-prob, no-speech prob, word timestamps.
- Drop segments with avg log-prob < -1.0 or no-speech prob > 0.6 (`LOW_CONF`).
- Metric: real-time factor (audio seconds per compute second), GPU/ANE utilisation, padding %.

### Stage 5 – Codec tokenisation (`atp tokenize`)

- Primary codec: **Kyutai Mimi** (12.5 Hz frames, 8+ RVQ codebooks). Comparison codec: **EnCodec 24 kHz**.
- Batch by length; use `torch.inference_mode()`, half precision on CUDA, pinned memory and non-blocking transfers.
- **Overlap CPU and GPU**: a producer process decodes and slices audio into a bounded queue while the GPU encodes the previous batch.
- Store tokens as `int16` NumPy arrays (codebooks × frames).
- Report: tokens per second of audio, compression ratio vs raw PCM, encode RTF, GPU utilisation.
- Quality check: decode 100 random samples back to audio and report reconstruction metrics (PESQ or ViSQOL, plus mel distance) so tokens are proven usable.

### Stage 6 – Sharding and delivery (`atp shard`)

- Write **WebDataset tar shards** of \~1 GB (configurable). Each sample: `tokens.npy`, `transcript.json`, `meta.json` (source, language, duration, filter scores, codec + version).
- Shard names include dataset version and index: `atp-v0.3-train-000123.tar`.
- Per-shard SHA-256 and a top-level `manifest.json` (shard list, sample counts, total hours, token counts, config hash, git commit).
- Train/validation split by **speaker or source ID**, never by segment, to avoid leakage.
- Versioning: a new version only re-shards changed items; record lineage in DuckDB.
- Optional upload to S3-compatible storage (MinIO locally) with checksum verification after upload.

### Stage 7 – Training feed (`atp feed-bench`)

- A streaming `IterableDataset` over shards: shard-level shuffle per epoch + in-memory sample shuffle buffer (size in config).
- Correct worker splitting (`worker_init_fn`, `split_by_worker`, `split_by_node`) so no sample is duplicated across workers or ranks.
- Dynamic batching by **token budget** (e.g. 64k tokens per batch) instead of fixed batch size.
- `train_probe.py`: a small transformer (\~20–50M params) doing next-token prediction on the codec tokens. Its job is not quality; it measures whether the dataloader ever starves the GPU.
- Report: **data stall %** (time GPU waits on data / total step time), samples/s, tokens/s, GPU utilisation, for 0, 2, 4, 8 workers.
- Target: data stall < 5% on the T4.

## 7. Benchmarking and performance engineering

This section is the heart of the project. The repo must prove engineering judgement with numbers.

### Metrics to collect for every run

| Metric | Unit | Where |
| --- | --- | --- |
| Throughput per stage | audio hours / wall-clock hour | every stage |
| Real-time factor | audio s / compute s | transcribe, tokenize |
| GPU / accelerator utilisation | % (nvidia-smi, powermetrics on Mac) | transcribe, tokenize, feed |
| Peak memory | GB RAM and GB VRAM | every stage |
| Padding waste | % of batch that is padding | transcribe, tokenize |
| Data stall | % of step time | feed |
| Rejection rate | % by reason code | filter |
| Cost | $ per 1,000 audio hours | end to end |

### Required bottleneck investigations

Find, fix and document at least these (before/after numbers each):

1. **IPC overhead:** passing NumPy arrays between processes vs passing paths/offsets and decoding in the worker.
2. **Padding waste:** random batching vs length-bucketed batching in Whisper and the codec.
3. **CPU–GPU overlap:** sequential decode-then-encode vs a producer/consumer queue with pinned memory.
4. **Small-file I/O:** many tiny files vs WebDataset tar streaming.
5. **Precision:** float32 vs float16/bfloat16 vs int8 (faster-whisper), with an accuracy check (WER on LibriSpeech test-clean) so speed never silently costs quality.

Each investigation gets a short entry in `docs/design_decisions.md`: problem, hypothesis, measurement method, result table, decision.

### Profiling tools

- `py-spy record` flame graphs for CPU stages (commit SVGs to `docs/profiles/`).
- `torch.profiler` traces for GPU stages.
- `nvidia-smi dmon` logging on Kaggle; `powermetrics` / Activity Monitor GPU history on Mac.
- A `atp bench` command that runs a fixed 10-hour benchmark and writes `bench/results/<run_id>.json`.

### Reproducibility

- Fixed seeds, pinned versions, the exact config and git commit stored with every result.
- A results table in the README is generated from the JSON files by `bench/report.py`, never typed by hand.

## 8. Cost model (`bench/cost_model.py`)

- Inputs: measured throughput per stage on each machine, hourly price per machine (config, with a dated source link), storage $/GB-month, egress $/GB.
- Outputs: **$ per 1,000 audio hours** on (a) M4 Mac (electricity only), (b) Kaggle T4 (free, plus its paid-cloud equivalent), (c) projected A100 and H100 at public on-demand prices.
- Project **1 million hours**: wall-clock time on N GPUs, total compute $, storage size for raw audio vs codec tokens, and the bottleneck stage at that scale.
- State every assumption in a table; label projections as projections, never as measured.

## 9. Testing and CI

- **Unit tests:** every filter on synthetic signals (pure tone, silence, clipped sine, noise at known SNR); resampler output length and rate; cache key stability; shard checksum round-trip.
- **Integration test:** 5-minute fixture end to end through all stages in < 3 minutes on CPU.
- **Property tests (Hypothesis):** segment boundaries never overlap and stay inside source duration.
- **Regression test:** WER on a fixed 100-clip set must not worsen by > 0.5 points after any change.
- **CI (GitHub Actions):** lint (ruff), type-check (mypy --strict on core modules), tests on Ubuntu + macOS, CPU only.
- Coverage target: ≥ 85% on `stages/`, `qa/`, `cache.py`, `catalog.py`.

## 10. CLI and configuration

- Typer CLI: `atp download | ingest | segment | filter | transcribe | tokenize | shard | feed-bench | bench | report | run`.
- `atp run --config configs/kaggle_t4.yaml` runs every stage with resume.
- Global flags: `--max-hours`, `--device`, `--workers`, `--dry-run`, `--force-stage <name>`.
- `atp status` prints a table of items per stage: done, pending, rejected, failed.

## 11. Observability and operations

- JSON logs plus a `runs` table (start, end, config hash, hours in/out, errors).
- A small Streamlit dashboard: throughput over time, rejection reasons, GPU utilisation, cost so far.
- `docs/runbook.md`: how to resume a crashed run, re-run one stage, add a new filter, recall a bad shard version.

## 12. Deliverables

1. Public GitHub repo with all of the above, MIT licensed.
2. **README** that opens with the results table (hours processed, end-to-end throughput, RTF per stage, GPU utilisation, data stall %, filter precision/recall, $ per 1,000 h, 1M-hour projection), then an architecture diagram, quickstart (3 commands), design decisions, and limitations.
3. Kaggle notebook reproducing the 1,000-hour benchmark.
4. `docs/writeup.md` and a blog post: "I processed X hours of speech into codec tokens for $Y – here's what bottlenecked."
5. A 2-minute screen recording: run the pipeline, show the dashboard and results.

## 13. Day-by-day plan (10 days)

| Day | Work | Done when |
| --- | --- | --- |
| 1 | Repo skeleton, config, device helper, catalogue, downloader, CI | `uv run pytest` green in CI |
| 2 | Ingest + segmentation on LibriSpeech dev | segments in DuckDB, throughput logged |
| 3 | Quality filters + fault injection suite | precision/recall table generated |
| 4 | Transcription with mlx-whisper, bucketed batching | RTF and padding % before/after |
| 5 | Mimi + EnCodec tokenisation, CPU–GPU overlap | tokens stored, reconstruction metrics |
| 6 | Sharding, manifest, versioning, training feed + probe | data stall % measured |
| 7 | Kaggle T4 port, 100 h run, fix bottlenecks | 3+ before/after investigations written |
| 8 | 1,000 h benchmark run, cost model | results JSON + cost table |
| 9 | README, dashboard, diagrams, writeup | founder can read results in 60 s |
| 10 | Polish, recording, outreach | email sent to founders |

## 14. Outreach (after the repo is live)

- Email founders@kalpalabs.ai and DM Prashant Shishodia and Gautam Jha on LinkedIn/X.
- Subject: "Processed X hours of audio into Mimi tokens at Y× real-time for $Z".
- Body: 3 lines – what you built, the 2–3 headline numbers, the repo link. Ask for 15 minutes. Resume attached, but the repo leads.
- Post the writeup on X and LinkedIn, tagging the codec and tool authors (Kyutai, faster-whisper, WebDataset).

## 15. How to work with me (the assistant)

- Follow the build order. Before each stage, propose the design, the data structures and the metric in a few lines, then wait for my OK.
- Write tests with the code, not after.
- After each stage, print: what was built, measured numbers, known issues, next step.
- Never fake or estimate a benchmark number; if something wasn't measured, say so.
- Flag anything that won't fit in 16 GB RAM or a 15 GB T4, with a workaround.
- Keep code simple, typed and readable; prefer general methods that scale over clever special cases.

## 16. Stage reports for independent verification

After every stage finishes, write a detailed report I can hand to a separate reviewer (another AI or engineer) to cross-check. Save each one as `reports/stage_<N>_<name>_<run_id>.md` plus a machine-readable `reports/stage_<N>_<name>_<run_id>.json` with the same numbers.

Every report must contain these sections, in this order:

1. **Summary:** what the stage does, one paragraph; pass/fail against its targets; the 3 most important numbers.
2. **Environment:** machine, chip, RAM, OS, Python and key library versions, device used (cpu/mps/cuda), git commit, config hash, run ID, start and end time.
3. **Inputs:** dataset and split, number of files/segments, total audio hours, input checksums or manifest hash.
4. **Outputs:** item counts in and out, rejections by reason code, output paths, output checksums, storage size.
5. **Metrics table:** every metric for this stage with value, unit, how it was measured, and the target. Mark each **Measured** or **Estimated**; never mix them.
6. **Performance:** throughput, real-time factor, CPU/GPU utilisation, peak memory, padding waste or data stall where relevant, and a link to the profile (flame graph or torch trace).
7. **Before/after comparisons:** for any optimisation in this stage, the baseline, the change, the new number, and the speed-up, all from the same input.
8. **Quality evidence:** for filters, precision/recall/F1 per fault type and the confusion matrix; for transcription, WER on the fixed test set; for tokenisation, reconstruction scores; plus 5 random samples listed by ID so a reviewer can spot-check them.
9. **Sanity checks:** automatic checks with pass/fail. Examples: output hours ≤ input hours; no overlapping segments; every shard checksum verifies; token frame counts match duration × frame rate; no NaN or empty outputs.
10. **Exact commands to reproduce:** the CLI commands and config file that reproduce every number in the report.
11. **Known issues and limitations:** anything flaky, skipped, approximated or not yet measured, stated plainly.
12. **Reviewer checklist:** 5–10 specific questions a reviewer should check, e.g. "Does reported throughput match total hours ÷ wall time in the run log?"

Rules:

- Numbers in the report come only from logged measurements or the DuckDB catalogue, generated by code (`atp report --stage <name>`), never typed by hand.
- Show raw values alongside derived ones (e.g. total seconds and wall time next to the throughput they produce), so every figure can be recalculated.
- If a target is missed, say so in the summary. Don't bury it.
- After the final stage, also produce `reports/final_report.md` that links all stage reports and gives the end-to-end results table used in the README.
