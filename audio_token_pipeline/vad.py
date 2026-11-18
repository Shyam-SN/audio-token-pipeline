"""Self-contained Silero VAD implementation using bundled ONNX model for 100% offline, zero-network execution."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime
import torch

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_PATH = Path(__file__).parent / "data" / "silero_vad.onnx"
_CACHED_SESSION: OnnxSileroVad | None = None


class OnnxSileroVad:
    """Lightweight ONNX wrapper for Silero VAD."""

    def __init__(self, model_path: Path | str | None = None) -> None:
        p = Path(model_path) if model_path else _DEFAULT_MODEL_PATH
        if not p.is_file():
            # Fallback to user home cache if present
            alt = Path.home() / ".cache/torch/hub/snakers4_silero-vad_master/src/silero_vad/data/silero_vad.onnx"
            if alt.is_file():
                p = alt
            else:
                raise FileNotFoundError(f"Silero VAD ONNX model not found at {p}")

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = onnxruntime.InferenceSession(str(p), providers=["CPUExecutionProvider"], sess_options=opts)
        self.reset_states()

    def reset_states(self, batch_size: int = 1) -> None:
        self._state = np.zeros((2, batch_size, 128), dtype=np.float32)
        self._context = np.zeros((batch_size, 64), dtype=np.float32)

    def __call__(self, x: torch.Tensor | np.ndarray, sr: int = 16000) -> float:
        if isinstance(x, torch.Tensor):
            arr = x.detach().cpu().numpy()
        else:
            arr = np.asarray(x, dtype=np.float32)

        if arr.ndim == 1:
            arr = arr[np.newaxis, :]
        batch_size = arr.shape[0]

        if self._state.shape[1] != batch_size:
            self.reset_states(batch_size)

        full_x = np.concatenate([self._context, arr], axis=1)
        ort_inputs = {
            "input": full_x.astype(np.float32),
            "state": self._state,
            "sr": np.array(sr, dtype=np.int64),
        }
        out, state = self.session.run(None, ort_inputs)
        self._state = state
        self._context = full_x[:, -64:]
        return float(out[0, 0])


def get_speech_timestamps_from_probs(
    speech_probs: list[float],
    sampling_rate: int = 16000,
    threshold: float = 0.5,
    min_speech_duration_ms: int = 250,
    max_speech_duration_s: float = float("inf"),
    min_silence_duration_ms: int = 100,
    speech_pad_ms: int = 30,
    return_seconds: bool = False,
    neg_threshold: float | None = None,
    audio_length_samples: int | None = None,
) -> list[dict[str, Any]]:
    """Convert per-window speech probabilities into speech timestamps."""
    window_size_samples = 512 if sampling_rate == 16000 else 256
    if audio_length_samples is None:
        audio_length_samples = len(speech_probs) * window_size_samples

    min_speech_samples = sampling_rate * min_speech_duration_ms / 1000
    speech_pad_samples = sampling_rate * speech_pad_ms / 1000
    max_speech_samples = sampling_rate * max_speech_duration_s - window_size_samples - 2 * speech_pad_samples
    min_silence_samples = sampling_rate * min_silence_duration_ms / 1000

    if neg_threshold is None:
        neg_threshold = max(threshold - 0.15, 0.01)

    triggered = False
    speeches: list[dict[str, Any]] = []
    current_speech: dict[str, int] = {}
    temp_end = 0

    for i, speech_prob in enumerate(speech_probs):
        cur_sample = window_size_samples * i

        if (speech_prob >= threshold) and temp_end:
            temp_end = 0

        if (speech_prob >= threshold) and not triggered:
            triggered = True
            current_speech["start"] = cur_sample
            continue

        if triggered and (cur_sample - current_speech["start"] > max_speech_samples):
            current_speech["end"] = cur_sample
            speeches.append(dict(current_speech))
            current_speech = {}
            triggered = False
            temp_end = 0
            continue

        if (speech_prob < neg_threshold) and triggered:
            if not temp_end:
                temp_end = cur_sample
            sil_dur_now = cur_sample - temp_end

            if sil_dur_now < min_silence_samples:
                continue
            else:
                current_speech["end"] = temp_end
                if (current_speech["end"] - current_speech["start"]) > min_speech_samples:
                    speeches.append(dict(current_speech))
                current_speech = {}
                triggered = False
                temp_end = 0

    if current_speech and (audio_length_samples - current_speech["start"]) > min_speech_samples:
        current_speech["end"] = audio_length_samples
        speeches.append(dict(current_speech))

    # Apply speech padding
    for i, speech in enumerate(speeches):
        if i == 0:
            speech["start"] = int(max(0, speech["start"] - speech_pad_samples))
        if i != len(speeches) - 1:
            next_start = speeches[i + 1]["start"]
            speech["end"] = int(min(next_start, speech["end"] + speech_pad_samples))
        else:
            speech["end"] = int(min(audio_length_samples, speech["end"] + speech_pad_samples))

    if return_seconds:
        return [
            {"start": round(s["start"] / sampling_rate, 3), "end": round(s["end"] / sampling_rate, 3)}
            for s in speeches
        ]
    return speeches


def get_vad_model() -> tuple[OnnxSileroVad, Any]:
    """Retrieve or initialize singleton Silero VAD ONNX model."""
    global _CACHED_SESSION
    if _CACHED_SESSION is None:
        _CACHED_SESSION = OnnxSileroVad()
    return _CACHED_SESSION, None
