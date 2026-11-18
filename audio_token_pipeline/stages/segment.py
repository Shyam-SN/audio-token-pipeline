"""Stage 2: Silero VAD speech segmentation (resampled straight from source to 16 kHz)."""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import torch
import torchaudio.functional as F

from audio_token_pipeline.catalog import Catalog
from audio_token_pipeline.config import AppConfig

logger = logging.getLogger(__name__)

# Global worker cache for Silero VAD model
_VAD_MODEL = None
_VAD_UTILS = None


def get_vad_model():  # type: ignore[no-untyped-def]
    """Lazy load cached Silero VAD ONNX model per worker process."""
    global _VAD_MODEL, _VAD_UTILS
    if _VAD_MODEL is None:
        torch.set_num_threads(1)
        _VAD_MODEL, _VAD_UTILS = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            onnx=True,
            trust_repo=True,
        )
    return _VAD_MODEL, _VAD_UTILS


def worker_init() -> None:
    """Initialize worker process with 1 torch thread and pre-warm Silero VAD."""
    try:
        torch.set_num_threads(1)
        get_vad_model()
    except Exception:
        pass


@dataclass
class SegmentResult:
    source_id: str
    segments: list[dict[str, Any]]
    speech_ratio: float
    total_audio_s: float
    error: str | None = None


def find_lowest_energy_split(audio_16k: np.ndarray, start_sample: int, end_sample: int) -> int:
    """Find the frame with minimum energy within a candidate split window."""
    window = audio_16k[start_sample:end_sample]
    frame_size = 320  # 20 ms at 16 kHz
    num_frames = len(window) // frame_size
    if num_frames <= 1:
        return (start_sample + end_sample) // 2

    energies = [
        float(np.sum(window[i * frame_size : (i + 1) * frame_size] ** 2))
        for i in range(num_frames)
    ]
    min_idx = int(np.argmin(energies))
    return start_sample + (min_idx * frame_size) + (frame_size // 2)


def segment_audio_file(
    source_id: str,
    filepath: str,
    vad_threshold: float = 0.5,
    min_speech_duration_s: float = 2.0,
    max_speech_duration_s: float = 30.0,
    speech_pad_s: float = 0.2,
) -> SegmentResult:
    """
    Load source audio, resample on the fly straight to 16 kHz mono float32,
    detect speech regions with Silero VAD, merge/split into 2-30s segments.
    """
    fpath = Path(filepath)
    if not fpath.is_file():
        return SegmentResult(source_id=source_id, segments=[], speech_ratio=0.0, total_audio_s=0.0, error="File missing")

    try:
        audio, sr = sf.read(str(fpath), dtype="float32", always_2d=True)
    except Exception as e:
        return SegmentResult(source_id=source_id, segments=[], speech_ratio=0.0, total_audio_s=0.0, error=f"Decode fail: {e}")

    # Convert to mono by averaging channels
    if audio.shape[1] > 1:
        audio_mono = np.mean(audio, axis=1)
    else:
        audio_mono = audio[:, 0]

    orig_len = len(audio_mono)
    total_audio_s = orig_len / float(sr) if sr > 0 else 0.0

    # Resample straight to 16 kHz mono float32
    if sr != 16000:
        tensor_in = torch.from_numpy(audio_mono).unsqueeze(0)
        resampled_tensor = F.resample(tensor_in, sr, 16000)
        audio_16k = resampled_tensor.squeeze(0).numpy()
    else:
        audio_16k = audio_mono

    # Silero VAD inference
    model, utils = get_vad_model()
    get_speech_timestamps = utils[0]

    tensor_16k = torch.from_numpy(audio_16k)
    raw_timestamps = get_speech_timestamps(
        tensor_16k,
        model,
        threshold=vad_threshold,
        sampling_rate=16000,
        min_speech_duration_ms=250,
        min_silence_duration_ms=100,
        return_seconds=False,
    )

    if not raw_timestamps:
        return SegmentResult(
            source_id=source_id,
            segments=[],
            speech_ratio=0.0,
            total_audio_s=round(total_audio_s, 4),
        )

    # Compute total detected speech duration for speech_ratio
    total_speech_samples = sum(ts["end"] - ts["start"] for ts in raw_timestamps)
    speech_ratio = min(1.0, float(total_speech_samples) / float(len(audio_16k))) if len(audio_16k) > 0 else 0.0

    # Merge and pad speech regions into segments of 2.0 to 30.0 seconds
    pad_samples = int(speech_pad_s * 16000)
    max_samples = int(max_speech_duration_s * 16000)
    min_samples = int(min_speech_duration_s * 16000)
    total_len = len(audio_16k)

    # Apply padding to raw intervals
    padded_intervals = []
    for ts in raw_timestamps:
        st = max(0, ts["start"] - pad_samples)
        en = min(total_len, ts["end"] + pad_samples)
        padded_intervals.append({"start": st, "end": en})

    # Merge overlapping or close intervals
    merged_regions: list[dict[str, int]] = []
    curr = padded_intervals[0].copy()

    for nxt in padded_intervals[1:]:
        # If overlapping or gap < 300ms and combined duration <= 30s
        gap = nxt["start"] - curr["end"]
        combined_dur = nxt["end"] - curr["start"]
        if gap <= 4800 and combined_dur <= max_samples:  # 4800 samples = 300ms
            curr["end"] = max(curr["end"], nxt["end"])
        else:
            merged_regions.append(curr)
            curr = nxt.copy()
    merged_regions.append(curr)

    # Split any regions exceeding max_speech_duration_s (30s) at lowest-energy point
    final_regions: list[dict[str, int]] = []
    for reg in merged_regions:
        st = reg["start"]
        en = reg["end"]
        while (en - st) > max_samples:
            # Target split between 20s and 30s
            split_win_start = st + int(20.0 * 16000)
            split_win_end = st + max_samples
            split_point = find_lowest_energy_split(audio_16k, split_win_start, split_win_end)
            final_regions.append({"start": st, "end": split_point})
            st = split_point
        final_regions.append({"start": st, "end": en})

    # Filter out segments shorter than min_speech_duration_s (2.0s)
    segments = []
    seg_idx = 0
    for reg in final_regions:
        dur_samples = reg["end"] - reg["start"]
        if dur_samples >= min_samples:
            start_ms = int(round((reg["start"] / 16000.0) * 1000.0))
            end_ms = int(round((reg["end"] / 16000.0) * 1000.0))
            dur_s = round((end_ms - start_ms) / 1000.0, 4)
            segments.append({
                "segment_id": f"{source_id}_seg_{seg_idx:05d}",
                "source_id": source_id,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_s": dur_s,
                "speech_prob": 1.0,
            })
            seg_idx += 1

    # Compute final active speech ratio from retained speech segments
    seg_speech_sec = 0.0
    for s in segments:
        dur_val = s.get("duration_s", 0.0)
        seg_speech_sec += float(dur_val) if isinstance(dur_val, (int, float)) else 0.0
    speech_ratio = min(1.0, seg_speech_sec / total_audio_s) if total_audio_s > 0 else 0.0

    return SegmentResult(
        source_id=source_id,
        segments=segments,
        speech_ratio=round(speech_ratio, 4),
        total_audio_s=round(total_audio_s, 4),
    )


def run_segment(
    config: AppConfig,
    num_workers: int | None = None,
    max_hours: float | None = None,
) -> dict[str, Any]:
    """
    Run Stage 2 Segmentation in parallel across sources.
    Parent process performs all DuckDB catalogue writes (single-writer rule).
    """
    cat = Catalog(config.catalog_path)
    workers = num_workers or config.device.num_workers or 6

    with cat.connection() as con:
        rows = con.execute(
            "SELECT source_id, filepath, duration_s FROM sources WHERE status = 'INGESTED' ORDER BY source_id"
        ).fetchall()

    if not rows:
        # Fall back to any registered sources
        with cat.connection() as con:
            rows = con.execute("SELECT source_id, filepath, duration_s FROM sources ORDER BY source_id").fetchall()

    if not rows:
        logger.info("No sources found for segmentation.")
        return {"items_in": 0, "segments_out": 0, "speed_segments_per_sec": 0.0}

    total_seconds = 0.0
    max_sec = (max_hours * 3600.0) if max_hours else float("inf")
    pending_tasks = []
    for r in rows:
        if total_seconds >= max_sec:
            break
        pending_tasks.append((r[0], r[1]))
        total_seconds += float(r[2]) if r[2] else 0.0

    logger.info(f"Segmenting {len(pending_tasks)} sources using {workers} workers (ProcessPoolExecutor)...")
    run_id = f"segment_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    cat.start_run(run_id, "segment", config.compute_hash())
    start_time = time.perf_counter()
    all_segments: list[dict[str, Any]] = []
    total_audio_sec = 0.0
    speech_ratios: list[float] = []

    with ProcessPoolExecutor(max_workers=workers, initializer=worker_init) as executor:
        future_map = {
            executor.submit(
                segment_audio_file,
                source_id,
                fpath,
                config.segment.vad_threshold,
                config.segment.min_speech_duration_s,
                config.segment.max_speech_duration_s,
                config.segment.speech_pad_s,
            ): source_id
            for source_id, fpath in pending_tasks
        }

        for fut in as_completed(future_map):
            res: SegmentResult = fut.result()
            if res.segments:
                all_segments.extend(res.segments)
            speech_ratios.append(res.speech_ratio)
            total_audio_sec += res.total_audio_s

    # Atomic write to catalog (main process only)
    cat.record_segments_batch(all_segments)

    elapsed_s = max(time.perf_counter() - start_time, 1e-4)
    seg_per_sec = len(all_segments) / elapsed_s if elapsed_s > 0 else 0.0
    avg_speech_ratio = float(np.mean(speech_ratios)) if speech_ratios else 0.0

    cat.finish_run(run_id, "COMPLETED", items_in=len(pending_tasks), items_out=len(all_segments))

    return {
        "items_in": len(pending_tasks),
        "segments_out": len(all_segments),
        "total_audio_seconds": round(total_audio_sec, 3),
        "elapsed_seconds": round(elapsed_s, 3),
        "speed_segments_per_second": round(seg_per_sec, 2),
        "avg_speech_ratio": round(avg_speech_ratio, 4),
        "workers": workers,
    }
