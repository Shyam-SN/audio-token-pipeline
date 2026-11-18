"""PyAV streaming audio decoding and header integrity verification."""

from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import Any

import av
import soundfile as sf

logger = logging.getLogger(__name__)


def read_wav_header_duration(filepath: Path) -> float | None:
    """Parse raw WAV RIFF header to determine nominal payload duration."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(256)
        if len(header) < 44 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            return None

        # Parse fmt chunk
        fmt_idx = header.find(b"fmt ")
        if fmt_idx == -1:
            return None
        channels = struct.unpack("<H", header[fmt_idx + 10 : fmt_idx + 12])[0]
        sample_rate = struct.unpack("<I", header[fmt_idx + 12 : fmt_idx + 16])[0]
        bits_per_sample = struct.unpack("<H", header[fmt_idx + 22 : fmt_idx + 24])[0]

        # Parse data chunk
        data_idx = header.find(b"data")
        if data_idx == -1:
            return None
        data_bytes = struct.unpack("<I", header[data_idx + 4 : data_idx + 8])[0]

        bytes_per_sample = max(1, bits_per_sample // 8)
        bytes_per_second = sample_rate * channels * bytes_per_sample
        if bytes_per_second <= 0:
            return None
        return float(data_bytes) / float(bytes_per_second)
    except Exception:
        return None


def decode_and_verify_audio(filepath: Path | str) -> tuple[bool, dict[str, Any], str | None]:
    """
    Fully decode audio file using PyAV in streaming chunks, verify decoded samples against
    header duration, and return (is_valid, metadata_dict, error_message).
    """
    fpath = Path(filepath)
    if not fpath.exists() or fpath.stat().st_size == 0:
        return False, {}, "EMPTY: file does not exist or has 0 bytes"

    # Step 1: Extract header metadata
    header_dur: float | None = None
    if fpath.suffix.lower() == ".wav":
        header_dur = read_wav_header_duration(fpath)

    try:
        sf_info = sf.info(str(fpath))
        if header_dur is None:
            header_dur = float(sf_info.duration)
        sample_rate = int(sf_info.samplerate)
        channels = int(sf_info.channels)
        format_name = str(sf_info.format)
    except Exception as e:
        return False, {}, f"DECODE_FAIL: header read error: {e}"

    # Step 2: Stream decode every packet to verify payload integrity
    total_samples = 0
    decoded_channels = channels
    decoded_rate = sample_rate

    try:
        container = av.open(str(fpath))
        audio_streams = [s for s in container.streams if s.type == "audio"]
        if not audio_streams:
            return False, {}, "EMPTY: no audio stream found"

        st = audio_streams[0]
        decoded_rate = getattr(st, "rate", None) or sample_rate
        decoded_channels = getattr(st, "channels", None) or channels

        for frame in container.decode(audio=0):
            total_samples += frame.samples

        container.close()
    except Exception as av_err:
        # Fallback to soundfile decode stream
        try:
            total_samples = 0
            with sf.SoundFile(str(fpath)) as f:
                while True:
                    data = f.read(65536)
                    if len(data) == 0:
                        break
                    total_samples += len(data)
        except Exception as sf_err:
            return False, {}, f"DECODE_FAIL: decoding error (av={av_err}, sf={sf_err})"

    if total_samples <= 0:
        return False, {}, "EMPTY: 0 samples decoded"

    decoded_dur = float(total_samples) / float(decoded_rate)

    # Step 3: Compare decoded duration with header duration
    if header_dur is not None:
        duration_diff = abs(decoded_dur - header_dur)
        # If mismatch exceeds 50ms, flag as corrupt/truncated
        if duration_diff > 0.05:
            return (
                False,
                {
                    "header_duration_s": round(header_dur, 4),
                    "decoded_duration_s": round(decoded_dur, 4),
                    "sample_rate": decoded_rate,
                    "channels": decoded_channels,
                    "format": format_name,
                },
                f"DECODE_FAIL: duration mismatch (header: {header_dur:.3f}s, decoded: {decoded_dur:.3f}s)",
            )

    metadata = {
        "duration_s": round(decoded_dur, 4),
        "sample_rate": decoded_rate,
        "channels": decoded_channels,
        "format": format_name,
        "num_samples": total_samples,
    }
    return True, metadata, None
