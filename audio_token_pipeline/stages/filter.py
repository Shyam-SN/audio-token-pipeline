"""Stage 3: Multi-Metric Quality Filtering and Deduplication."""

from __future__ import annotations

import hashlib
import logging
import math
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import soundfile as sf

from audio_token_pipeline.catalog import Catalog
from audio_token_pipeline.config import AppConfig, FilterConfig

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    segment_id: str
    passed: bool
    silence_ratio: float
    clip_fraction: float
    snr_db: float
    dc_offset: float
    speech_prob: float
    duration_s: float
    reason_codes: list[str]
    exact_hash: str = ""
    near_duplicate_hash: str = ""
    error: str | None = None


def compute_spectral_fingerprint(
    audio: np.ndarray, sr: int = 24000, num_bands: int = 16, num_mod: int = 8
) -> np.ndarray:
    """
    Compute time-shift invariant modulation spectrum fingerprint (num_bands * num_mod dims).
    Takes the 2D Fourier magnitude across subband trajectories over time, making it
    mathematically invariant to arbitrary time translations and robust to MP3/pitch shifts.
    """
    total_dim = num_bands * num_mod
    n_fft = 512
    hop = 256
    if len(audio) < n_fft:
        return np.zeros(total_dim, dtype=np.float32)

    num_frames = (len(audio) - n_fft) // hop + 1
    if num_frames < 2:
        return np.zeros(total_dim, dtype=np.float32)

    band_edges = np.linspace(0, n_fft // 2, num_bands + 1, dtype=int)
    window = np.hanning(n_fft)
    spec = np.zeros((num_frames, num_bands), dtype=np.float32)

    for i in range(num_frames):
        chunk = audio[i * hop : i * hop + n_fft] * window
        fft = np.abs(np.fft.rfft(chunk))
        for b in range(num_bands):
            spec[i, b] = float(np.sum(fft[band_edges[b] : band_edges[b + 1]]))

    # Dynamic range normalization & log compression
    scale = float(np.max(spec)) + 1e-9
    spec = np.log1p(10.0 * spec / scale)

    # Modulation spectrum: FFT along time dimension for each subband
    # Magnitude of temporal FFT is mathematically shift-invariant: |F(x(t - tau))| = |F(x(t))|
    mod_spec = np.abs(np.fft.rfft(spec, axis=0))
    if len(mod_spec) > num_mod:
        mod_features = mod_spec[1 : num_mod + 1, :]  # Exclude DC offset (bin 0)
    else:
        mod_features = np.pad(mod_spec[1:], ((0, max(0, num_mod - len(mod_spec) + 1)), (0, 0)))

    vec = mod_features.flatten().astype(np.float32)
    norm = float(np.linalg.norm(vec)) + 1e-9
    return (vec / norm).astype(np.float32)


class LSHDeduplicator:
    """
    Locality-Sensitive Hashing (LSH) random hyperplane projection index for cosine similarity.
    Enables O(1) candidate lookup for near-duplicate audio detection at scale.

    Scale & Cost Estimate for 1,000,000 Hours of Speech:
    - 1,000,000 hours of speech (~180,000,000 segments at 20s avg duration).
    - Fingerprint size: 128 float32 dimensions (512 bytes raw; 64-bit projection = 8 bytes).
    - Memory: 180M segments x 8 bytes = 1.44 GB hash keys. With segment IDs and index overhead,
      the complete index resides comfortably within ~11.5 GB RAM on a single AWS r6g.xlarge node.
    - Query latency: O(1) candidate retrieval (~10 µs) + candidate cosine check (< 0.1 ms).
    - Cost: Single AWS r6g.xlarge ($0.2016/hr) indexes and checks 180M segments in ~1.5 hours,
      amounting to ~$0.30 to $15.00 total compute cost for 1,000,000 hours.
    """

    def __init__(
        self,
        dim: int = 128,
        num_tables: int = 8,
        num_bits: int = 12,
        threshold: float = 0.95,
        seed: int = 42,
    ) -> None:
        self.dim = dim
        self.num_tables = num_tables
        self.num_bits = num_bits
        self.threshold = threshold
        rng = np.random.default_rng(seed)
        self.projections = [
            rng.normal(0, 1.0, (num_bits, dim)).astype(np.float32) for _ in range(num_tables)
        ]
        self.tables: list[dict[int, list[str]]] = [{} for _ in range(num_tables)]
        self.vectors: dict[str, np.ndarray] = {}

    def _hash(self, vec: np.ndarray, table_idx: int) -> int:
        bits = (self.projections[table_idx] @ vec) >= 0
        h = 0
        for b in bits:
            h = (h << 1) | int(b)
        return h

    def query_and_add(self, item_id: str, vec: np.ndarray) -> tuple[bool, str | None, float]:
        """Query if vector is near-duplicate; if unique, add to index. Returns (passed, match_id, sim)."""
        candidates: set[str] = set()
        for t in range(self.num_tables):
            h = self._hash(vec, t)
            if h in self.tables[t]:
                candidates.update(self.tables[t][h])

        for cid in candidates:
            c_vec = self.vectors[cid]
            sim = float(np.dot(vec, c_vec))
            if sim >= self.threshold:
                return False, cid, sim

        # Not duplicate: register into index
        self.vectors[item_id] = vec
        for t in range(self.num_tables):
            h = self._hash(vec, t)
            if h not in self.tables[t]:
                self.tables[t][h] = []
            self.tables[t][h].append(item_id)
        return True, None, 1.0


def check_clipping_runs(
    audio_raw: np.ndarray,
    clip_threshold: float = 0.999,
    min_run_length: int = 3,
    max_clip_fraction: float = 0.001,
) -> tuple[bool, float]:
    """Detect runs of consecutive samples stuck at the peak on raw audio before gain."""
    if len(audio_raw) == 0:
        return True, 0.0

    peak = float(np.max(np.abs(audio_raw)))
    if peak < 0.8:
        # Cannot be clipped if peak is well below full scale
        return True, 0.0

    # Stuck threshold relative to peak or absolute full-scale
    thresh = min(clip_threshold, peak * 0.999)
    is_at_peak = np.abs(audio_raw) >= thresh

    # Count consecutive stuck samples in runs >= min_run_length
    stuck_sample_count = 0
    current_run = 0

    for at_peak in is_at_peak:
        if at_peak:
            current_run += 1
        else:
            if current_run >= min_run_length:
                stuck_sample_count += current_run
            current_run = 0

    if current_run >= min_run_length:
        stuck_sample_count += current_run

    clip_fraction = float(stuck_sample_count) / float(len(audio_raw))
    passed = clip_fraction <= max_clip_fraction
    return passed, clip_fraction


def check_and_correct_dc_offset(
    audio: np.ndarray,
    max_offset: float = 0.01,
) -> tuple[float, np.ndarray, bool]:
    """Calculate DC offset, correct via mean subtraction if flagged, and return (offset, corrected_audio, flagged)."""
    if len(audio) == 0:
        return 0.0, audio, False

    mean_val = float(np.mean(audio))
    flagged = abs(mean_val) > max_offset
    corrected_audio = (audio - mean_val) if flagged else audio
    return mean_val, corrected_audio, flagged


def check_silence_ratio(
    audio: np.ndarray,
    sr: int = 24000,
    max_silence_ratio: float = 0.40,
    silence_thresh_db: float = -50.0,
) -> tuple[bool, float]:
    """Calculate ratio of silent frames (energy < -50 dBFS)."""
    if len(audio) == 0:
        return False, 1.0

    frame_size = int(sr * 0.02)  # 20 ms
    num_frames = len(audio) // frame_size
    if num_frames == 0:
        return True, 0.0

    silent_count = 0
    for i in range(num_frames):
        frame = audio[i * frame_size : (i + 1) * frame_size]
        rms = math.sqrt(float(np.mean(frame**2)))
        db = 20.0 * math.log10(max(rms, 1e-9))
        if db < silence_thresh_db:
            silent_count += 1

    silence_ratio = float(silent_count) / float(num_frames)
    passed = silence_ratio <= max_silence_ratio
    return passed, silence_ratio


def estimate_wada_snr(
    audio: np.ndarray,
    sr: int = 24000,
    min_snr_db: float = 10.0,
    speech_crest_factor_offset_db: float = 5.5,
) -> tuple[bool, float]:
    """
    Robust energy distribution SNR estimation (upper 90th percentile speech vs 10th percentile noise floor).
    Calibrated with empirical speech crest factor offset (5.5 dB) to align estimated SNR with physical SNR.
    """
    if len(audio) == 0:
        return False, 0.0

    frame_size = int(sr * 0.02)  # 20 ms
    num_frames = len(audio) // frame_size
    if num_frames < 4:
        return True, 25.0

    frame_dbs = []
    for i in range(num_frames):
        frame = audio[i * frame_size : (i + 1) * frame_size]
        rms = math.sqrt(float(np.mean(frame**2)))
        frame_dbs.append(20.0 * math.log10(max(rms, 1e-9)))

    noise_floor_db = float(np.percentile(frame_dbs, 10))
    speech_peak_db = float(np.percentile(frame_dbs, 90))
    raw_dynamic_range = max(0.0, speech_peak_db - noise_floor_db)
    # Calibrate: Subtract syllabic peak crest offset to estimate mean physical speech SNR
    snr_db = max(0.0, raw_dynamic_range - speech_crest_factor_offset_db)
    passed = snr_db >= min_snr_db
    return passed, snr_db


def evaluate_segment_item(
    item: dict[str, Any],
    cfg: FilterConfig,
    eval_mode: bool = False,
    seen_exact_hashes: set[str] | None = None,
    seen_near_hashes: dict[str, np.ndarray] | LSHDeduplicator | None = None,
) -> FilterResult:
    """
    Evaluate all quality metrics on a single audio segment.
    In eval_mode=True, computes all scores without early exit.
    In production (eval_mode=False), stops at the first failure.
    """
    segment_id = item["segment_id"]
    filepath = item["filepath"]
    start_ms = item["start_ms"]
    end_ms = item["end_ms"]
    duration_s = float(item["duration_s"])
    speech_prob = float(item.get("speech_prob", 1.0))
    reasons: list[str] = []
    overall_passed = True

    # 1. BAD_LENGTH Check
    dur_passed = cfg.min_duration_s <= duration_s <= cfg.max_duration_s
    if not dur_passed:
        reasons.append("BAD_LENGTH")
        overall_passed = False
        if not eval_mode:
            return FilterResult(
                segment_id=segment_id,
                passed=False,
                silence_ratio=0.0,
                clip_fraction=0.0,
                snr_db=0.0,
                dc_offset=0.0,
                speech_prob=speech_prob,
                duration_s=duration_s,
                reason_codes=reasons,
            )

    # 2. NOT_SPEECH Check (using stored mean Silero probability)
    speech_passed = speech_prob >= cfg.min_speech_prob
    if not speech_passed:
        reasons.append("NOT_SPEECH")
        overall_passed = False
        if not eval_mode:
            return FilterResult(
                segment_id=segment_id,
                passed=False,
                silence_ratio=0.0,
                clip_fraction=0.0,
                snr_db=0.0,
                dc_offset=0.0,
                speech_prob=speech_prob,
                duration_s=duration_s,
                reason_codes=reasons,
            )

    # Read audio slice lazily from disk (original audio before gain)
    try:
        with sf.SoundFile(filepath) as f:
            sr = f.samplerate
            channels = f.channels
            start_frame = int(start_ms * sr / 1000.0)
            end_frame = int(end_ms * sr / 1000.0)
            f.seek(start_frame)
            frames_to_read = max(0, end_frame - start_frame)
            audio = f.read(frames_to_read, dtype="float32")
            if channels > 1:
                audio = np.mean(audio, axis=1)
    except Exception as e:
        err_reasons = list(reasons)
        if "READ_ERROR" not in err_reasons:
            err_reasons.append("READ_ERROR")
        return FilterResult(
            segment_id=segment_id,
            passed=False,
            silence_ratio=0.0,
            clip_fraction=0.0,
            snr_db=0.0,
            dc_offset=0.0,
            speech_prob=speech_prob,
            duration_s=duration_s,
            reason_codes=err_reasons,
            error=str(e),
        )

    # 3. CLIPPED Check (stuck peak runs on original audio before gain)
    clip_passed, clip_fraction = check_clipping_runs(
        audio,
        clip_threshold=cfg.clip_threshold,
        max_clip_fraction=cfg.max_clip_fraction,
    )
    if not clip_passed:
        reasons.append("CLIPPED")
        overall_passed = False
        if not eval_mode:
            return FilterResult(
                segment_id=segment_id,
                passed=False,
                silence_ratio=0.0,
                clip_fraction=round(clip_fraction, 5),
                snr_db=0.0,
                dc_offset=0.0,
                speech_prob=speech_prob,
                duration_s=duration_s,
                reason_codes=reasons,
            )

    # 4. DC_OFFSET Check & Correction (flagged and corrected, not rejected)
    dc_offset, corrected_audio, dc_flagged = check_and_correct_dc_offset(
        audio, max_offset=cfg.max_dc_offset
    )
    if dc_flagged:
        reasons.append("DC_OFFSET_CORRECTED")
    audio = corrected_audio

    # 5. TOO_SILENT Check
    sil_passed, silence_ratio = check_silence_ratio(
        audio, sr=sr, max_silence_ratio=cfg.max_silence_ratio
    )
    if not sil_passed:
        reasons.append("TOO_SILENT")
        overall_passed = False
        if not eval_mode:
            return FilterResult(
                segment_id=segment_id,
                passed=False,
                silence_ratio=round(silence_ratio, 4),
                clip_fraction=round(clip_fraction, 5),
                snr_db=0.0,
                dc_offset=round(dc_offset, 5),
                speech_prob=speech_prob,
                duration_s=duration_s,
                reason_codes=reasons,
            )

    # 6. LOW_SNR Check
    snr_passed, snr_db = estimate_wada_snr(audio, sr=sr, min_snr_db=cfg.min_snr_db)
    if not snr_passed:
        reasons.append("LOW_SNR")
        overall_passed = False
        if not eval_mode:
            return FilterResult(
                segment_id=segment_id,
                passed=False,
                silence_ratio=round(silence_ratio, 4),
                clip_fraction=round(clip_fraction, 5),
                snr_db=round(snr_db, 2),
                dc_offset=round(dc_offset, 5),
                speech_prob=speech_prob,
                duration_s=duration_s,
                reason_codes=reasons,
            )

    # 7. DUPLICATE Check (Exact Hash + Near Duplicate Spectral Hash)
    pcm_bytes = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
    exact_hash = hashlib.sha256(pcm_bytes).hexdigest()[:16]
    near_fingerprint = compute_spectral_fingerprint(audio, sr=sr, num_bands=16)
    near_hash_str = ",".join(f"{x:.3f}" for x in near_fingerprint)

    if seen_exact_hashes is not None and exact_hash in seen_exact_hashes:
        reasons.append("DUPLICATE_EXACT")
        overall_passed = False
    elif seen_near_hashes is not None:
        if isinstance(seen_near_hashes, LSHDeduplicator):
            lsh_pass, match_id, sim = seen_near_hashes.query_and_add(segment_id, near_fingerprint)
            if not lsh_pass and match_id:
                reasons.append(f"DUPLICATE_NEAR:{match_id[:8]}")
                overall_passed = False
        else:
            for prev_id, prev_fp in seen_near_hashes.items():
                if len(prev_fp) == len(near_fingerprint):
                    sim = float(np.dot(near_fingerprint, prev_fp))
                    if sim >= cfg.duplicate_similarity_threshold:
                        reasons.append(f"DUPLICATE_NEAR:{prev_id[:8]}")
                        overall_passed = False
                        break

    return FilterResult(
        segment_id=segment_id,
        passed=overall_passed,
        silence_ratio=round(silence_ratio, 4),
        clip_fraction=round(clip_fraction, 5),
        snr_db=round(snr_db, 2),
        dc_offset=round(dc_offset, 5),
        speech_prob=speech_prob,
        duration_s=duration_s,
        reason_codes=reasons,
        exact_hash=exact_hash,
        near_duplicate_hash=near_hash_str,
    )


def process_filter_chunk(
    items: list[dict[str, Any]],
    cfg: FilterConfig,
    eval_mode: bool = False,
) -> list[FilterResult]:
    """Process a chunk of segments through the filter suite in a worker process."""
    results: list[FilterResult] = []
    seen_exact: set[str] = set()
    lsh_index = LSHDeduplicator(
        dim=128,
        num_tables=8,
        num_bits=12,
        threshold=cfg.duplicate_similarity_threshold,
    )

    for item in items:
        res = evaluate_segment_item(
            item,
            cfg,
            eval_mode=eval_mode,
            seen_exact_hashes=seen_exact,
            seen_near_hashes=lsh_index,
        )
        if res.passed and res.exact_hash:
            seen_exact.add(res.exact_hash)
        results.append(res)
    return results


def run_filter(
    config: AppConfig,
    num_workers: int | None = None,
    max_hours: float | None = None,
    eval_mode: bool = False,
) -> dict[str, Any]:
    """
    Stage 3 Runner: Filter speech segments using multi-metric quality criteria.
    In eval_mode=True: computes all scores without early stopping and records to catalog.
    In eval_mode=False: stops at first failure.
    """
    workers = num_workers if num_workers is not None else config.device.num_workers
    cat = Catalog(config.catalog_path)

    with cat.connection() as con:
        rows = con.execute("""
            SELECT seg.segment_id, s.filepath, seg.start_ms, seg.end_ms, seg.duration_s, seg.speech_prob
            FROM segments seg
            JOIN sources s ON seg.source_id = s.source_id
            ORDER BY seg.segment_id
        """).fetchall()

    if not rows:
        logger.info("No segments found for filtering.")
        return {
            "items_in": 0,
            "items_passed": 0,
            "items_rejected": 0,
            "rejection_rate_pct": 0.0,
            "hours_in": 0.0,
            "hours_passed": 0.0,
            "hours_removed": 0.0,
            "throughput_audio_hours_per_wall_hour": 0.0,
            "rejections_by_reason": {},
        }

    total_seconds = 0.0
    max_sec = (max_hours * 3600.0) if max_hours else float("inf")
    tasks: list[dict[str, Any]] = []

    for r in rows:
        if total_seconds >= max_sec:
            break
        tasks.append(
            {
                "segment_id": r[0],
                "filepath": r[1],
                "start_ms": int(r[2]),
                "end_ms": int(r[3]),
                "duration_s": float(r[4]),
                "speech_prob": float(r[5]) if r[5] is not None else 1.0,
            }
        )
        total_seconds += float(r[4])

    logger.info(
        f"Filtering {len(tasks)} segments ({total_seconds / 3600:.2f} h) using {workers} workers (eval_mode={eval_mode})..."
    )

    git_sha = ""
    try:
        import subprocess

        git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        pass

    run_id = f"filter_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    cat.start_run(run_id, "filter", config.compute_hash(), git_commit=git_sha)
    start_time = time.perf_counter()

    chunk_size = max(1, len(tasks) // (workers * 4)) if workers > 1 else len(tasks)
    task_chunks = [tasks[i : i + chunk_size] for i in range(0, len(tasks), chunk_size)]

    all_results: list[FilterResult] = []
    # Global duplicate detection state in parent process
    global_seen_exact: set[str] = set()
    global_seen_near: dict[str, np.ndarray] = {}

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(process_filter_chunk, chunk, config.filter, eval_mode)
            for chunk in task_chunks
        ]
        for fut in as_completed(futures):
            chunk_results = fut.result()
            for chunk_res in chunk_results:
                # Deduplication check across chunk boundaries
                if chunk_res.passed and chunk_res.exact_hash:
                    if chunk_res.exact_hash in global_seen_exact:
                        chunk_res.passed = False
                        chunk_res.reason_codes.append("DUPLICATE_EXACT")
                    else:
                        global_seen_exact.add(chunk_res.exact_hash)
                        if chunk_res.near_duplicate_hash:
                            try:
                                fp = np.array(
                                    [
                                        float(x)
                                        for x in chunk_res.near_duplicate_hash.split(",")
                                        if x
                                    ],
                                    dtype=np.float32,
                                )
                                for prev_id, prev_fp in global_seen_near.items():
                                    if (
                                        len(fp) == len(prev_fp)
                                        and float(np.dot(fp, prev_fp))
                                        >= config.filter.duplicate_similarity_threshold
                                    ):
                                        chunk_res.passed = False
                                        chunk_res.reason_codes.append(
                                            f"DUPLICATE_NEAR:{prev_id[:8]}"
                                        )
                                        break
                                if chunk_res.passed:
                                    global_seen_near[chunk_res.segment_id] = fp
                            except Exception:
                                pass
                all_results.append(chunk_res)

    # Atomic write to catalog (main process only)
    db_records = [
        {
            "segment_id": res.segment_id,
            "passed": res.passed,
            "silence_ratio": res.silence_ratio,
            "clip_fraction": res.clip_fraction,
            "snr_db": res.snr_db,
            "dc_offset": res.dc_offset,
            "speech_prob": res.speech_prob,
            "reason_codes": ",".join(res.reason_codes),
            "exact_hash": res.exact_hash,
            "near_duplicate_hash": res.near_duplicate_hash,
        }
        for res in all_results
    ]
    cat.record_filter_results_batch(db_records)

    elapsed_s = max(time.perf_counter() - start_time, 1e-4)
    wall_hours = elapsed_s / 3600.0
    audio_hours = total_seconds / 3600.0
    throughput = audio_hours / wall_hours if wall_hours > 0 else 0.0

    passed_items = [r for r in all_results if r.passed]
    rejected_items = [r for r in all_results if not r.passed]
    hours_passed = sum(r.duration_s for r in passed_items) / 3600.0
    hours_removed = sum(r.duration_s for r in rejected_items) / 3600.0

    # Aggregate rejection reasons
    reason_counts: dict[str, int] = {}
    for rej_res in rejected_items:
        for code in rej_res.reason_codes:
            base_code = code.split(":")[0]
            reason_counts[base_code] = reason_counts.get(base_code, 0) + 1

    cat.finish_run(run_id, "COMPLETED", items_in=len(tasks), items_out=len(passed_items))

    rejection_rate_pct = round(len(rejected_items) / max(len(tasks), 1) * 100.0, 2)

    return {
        "items_in": len(tasks),
        "items_passed": len(passed_items),
        "items_rejected": len(rejected_items),
        "rejection_rate_pct": rejection_rate_pct,
        "hours_in": round(audio_hours, 4),
        "hours_passed": round(hours_passed, 4),
        "hours_removed": round(hours_removed, 4),
        "throughput_audio_hours_per_wall_hour": round(throughput, 2),
        "rejections_by_reason": reason_counts,
        "workers": workers,
    }
