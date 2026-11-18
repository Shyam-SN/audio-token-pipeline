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
        hub_dir = Path.home() / ".cache/torch/hub/snakers4_silero-vad_master"
        if hub_dir.exists():
            _VAD_MODEL, _VAD_UTILS = torch.hub.load(
                repo_or_dir=str(hub_dir),
                model="silero_vad",
                source="local",
                onnx=True,
                trust_repo=True,
            )
        else:
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
    import inspect
    mod = inspect.getmodule(utils[0])
    get_speech_timestamps_from_probs = getattr(mod, "get_speech_timestamps_from_probs")

    window = 512
    model.reset_states()
    audio_t = torch.from_numpy(audio_16k).float()
    audio_len = len(audio_16k)

    probs: list[float] = []
    for cur in range(0, audio_len, window):
        chunk = audio_t[cur : cur + window]
        if len(chunk) < window:
            chunk = torch.nn.functional.pad(chunk, (0, int(window - len(chunk))))
        probs.append(model(chunk, 16000).item())

    raw_timestamps = get_speech_timestamps_from_probs(
        probs,
        sampling_rate=16000,
        threshold=vad_threshold,
        min_speech_duration_ms=250,
        min_silence_duration_ms=100,
        speech_pad_ms=int(speech_pad_s * 1000),
        audio_length_samples=audio_len,
    )

    if not raw_timestamps:
        return SegmentResult(
            source_id=source_id,
            segments=[],
            speech_ratio=0.0,
            total_audio_s=round(total_audio_s, 4),
        )

    # Merge across short pauses (gap <= 1.2s) as long as combined duration <= 30.0s
    max_pause_samples = int(1.2 * 16000)
    max_samples = int(max_speech_duration_s * 16000)
    min_samples = int(min_speech_duration_s * 16000)

    merged_regions: list[dict[str, int]] = []
    curr = {"start": raw_timestamps[0]["start"], "end": raw_timestamps[0]["end"]}

    for nxt in raw_timestamps[1:]:
        gap = nxt["start"] - curr["end"]
        combined_dur = nxt["end"] - curr["start"]
        if gap <= max_pause_samples and combined_dur <= max_samples:
            curr["end"] = max(curr["end"], nxt["end"])
        else:
            merged_regions.append(curr)
            curr = {"start": nxt["start"], "end": nxt["end"]}
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

    # Drop only pieces under 2s (min_speech_duration_s)
    segments = []
    seg_idx = 0
    for reg in final_regions:
        dur_samples = reg["end"] - reg["start"]
        if dur_samples >= min_samples:
            st_idx = reg["start"] // 512
            en_idx = max(st_idx + 1, (reg["end"] + 511) // 512)
            seg_probs = probs[st_idx:en_idx]
            mean_prob = float(np.mean(seg_probs)) if seg_probs else 0.0

            start_ms = int(round((reg["start"] / 16000.0) * 1000.0))
            end_ms = int(round((reg["end"] / 16000.0) * 1000.0))
            dur_s = round((end_ms - start_ms) / 1000.0, 4)
            segments.append({
                "segment_id": f"{source_id}_seg_{seg_idx:05d}",
                "source_id": source_id,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_s": dur_s,
                "speech_prob": round(mean_prob, 4),
            })
            seg_idx += 1

    # Compute final active speech ratio from retained speech segments
    seg_speech_sec = 0.0
    for s in segments:
        dur_v = s.get("duration_s", 0.0)
        seg_speech_sec += float(dur_v) if isinstance(dur_v, (int, float)) else 0.0
    speech_ratio = min(1.0, seg_speech_sec / total_audio_s) if total_audio_s > 0 else 0.0

    return SegmentResult(
        source_id=source_id,
        segments=segments,
        speech_ratio=round(speech_ratio, 4),
        total_audio_s=round(total_audio_s, 4),
    )


def segment_audio_batch(
    batch: list[tuple[str, str]],
    vad_threshold: float = 0.5,
    min_speech_duration_s: float = 2.0,
    max_speech_duration_s: float = 30.0,
    speech_pad_s: float = 0.2,
) -> list[SegmentResult]:
    """Process a chunk of audio files for speech segmentation in a worker process."""
    return [
        segment_audio_file(
            source_id=sid,
            filepath=fpath,
            vad_threshold=vad_threshold,
            min_speech_duration_s=min_speech_duration_s,
            max_speech_duration_s=max_speech_duration_s,
            speech_pad_s=speech_pad_s,
        )
        for sid, fpath in batch
    ]


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
    git_sha = ""
    try:
        import subprocess
        git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        pass

    run_id = f"segment_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    cat.start_run(run_id, "segment", config.compute_hash(), git_commit=git_sha)
    start_time = time.perf_counter()
    all_segments: list[dict[str, Any]] = []
    total_audio_sec = 0.0
    speech_ratios: list[float] = []
    zero_segment_sources: list[str] = []

    chunk_size = max(1, len(pending_tasks) // (workers * 4)) if workers > 1 else len(pending_tasks)
    task_chunks = [pending_tasks[i : i + chunk_size] for i in range(0, len(pending_tasks), chunk_size)]

    with ProcessPoolExecutor(max_workers=workers, initializer=worker_init) as executor:
        futures = [
            executor.submit(
                segment_audio_batch,
                chunk,
                config.segment.vad_threshold,
                config.segment.min_speech_duration_s,
                config.segment.max_speech_duration_s,
                config.segment.speech_pad_s,
            )
            for chunk in task_chunks
        ]

        for fut in as_completed(futures):
            batch_results = fut.result()
            for res in batch_results:
                if res.segments:
                    all_segments.extend(res.segments)
                else:
                    zero_segment_sources.append(res.source_id)
                speech_ratios.append(res.speech_ratio)
                total_audio_sec += res.total_audio_s

    # Atomic write to catalog (main process only)
    cat.record_segments_batch(all_segments)

    elapsed_s = max(time.perf_counter() - start_time, 1e-4)
    wall_hours = elapsed_s / 3600.0
    audio_hours = total_audio_sec / 3600.0
    throughput = audio_hours / wall_hours if wall_hours > 0 else 0.0
    seg_per_sec = len(all_segments) / elapsed_s if elapsed_s > 0 else 0.0
    avg_speech_ratio = float(np.mean(speech_ratios)) if speech_ratios else 0.0

    cat.finish_run(run_id, "COMPLETED", items_in=len(pending_tasks), items_out=len(all_segments))

    return {
        "items_in": len(pending_tasks),
        "segments_out": len(all_segments),
        "total_audio_seconds": round(total_audio_sec, 3),
        "elapsed_seconds": round(elapsed_s, 3),
        "throughput_audio_hours_per_wall_hour": round(throughput, 2),
        "speed_segments_per_second": round(seg_per_sec, 2),
        "avg_speech_ratio": round(avg_speech_ratio, 4),
        "zero_segment_sources": sorted(zero_segment_sources),
        "workers": workers,
    }
