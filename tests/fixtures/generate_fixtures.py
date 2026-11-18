"""Generate a 5-minute synthetic audio fixture suite for smoke testing and filter verification."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

FIXTURES_DIR = Path(__file__).parent


def generate_fixtures() -> dict[str, Path]:
    """Generate various audio conditions totaling ~5 minutes (300 seconds)."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    sr = 24000
    created_files: dict[str, Path] = {}

    # 1. Clean speech-like harmonic formants (40 seconds)
    t = np.linspace(0, 40, int(sr * 40), endpoint=False, dtype=np.float32)
    # Fundamental 150 Hz with formant harmonics (300 Hz, 750 Hz, 1200 Hz, 2400 Hz)
    clean_audio = (
        0.3 * np.sin(2 * np.pi * 150 * t) +
        0.2 * np.sin(2 * np.pi * 300 * t) +
        0.15 * np.sin(2 * np.pi * 750 * t) +
        0.1 * np.sin(2 * np.pi * 1200 * t)
    ).astype(np.float32)
    # Envelope modulation to simulate syllables
    envelope = (np.sin(2 * np.pi * 3 * t) + 1.0) / 2.0
    clean_audio = clean_audio * envelope
    path_clean = FIXTURES_DIR / "clean_formant.wav"
    sf.write(str(path_clean), clean_audio, sr)
    created_files["clean"] = path_clean

    # 2. Pure silence (30 seconds)
    silence = np.zeros(int(sr * 30), dtype=np.float32)
    path_silence = FIXTURES_DIR / "silence.wav"
    sf.write(str(path_silence), silence, sr)
    created_files["silence"] = path_silence

    # 3. Severely clipped audio (30 seconds)
    t = np.linspace(0, 30, int(sr * 30), endpoint=False, dtype=np.float32)
    loud_sine = 3.0 * np.sin(2 * np.pi * 440 * t)
    clipped = np.clip(loud_sine, -1.0, 1.0).astype(np.float32)
    path_clipped = FIXTURES_DIR / "clipped.wav"
    sf.write(str(path_clipped), clipped, sr)
    created_files["clipped"] = path_clipped

    # 4. DC offset bias (30 seconds)
    t = np.linspace(0, 30, int(sr * 30), endpoint=False, dtype=np.float32)
    dc_audio = (0.2 * np.sin(2 * np.pi * 220 * t) + 0.05).astype(np.float32)
    path_dc = FIXTURES_DIR / "dc_offset.wav"
    sf.write(str(path_dc), dc_audio, sr)
    created_files["dc_offset"] = path_dc

    # 5. Low SNR noisy audio (~5 dB SNR) (40 seconds)
    t = np.linspace(0, 40, int(sr * 40), endpoint=False, dtype=np.float32)
    signal = 0.2 * np.sin(2 * np.pi * 350 * t)
    noise = np.random.default_rng(42).normal(0, 0.15, size=len(t)).astype(np.float32)
    noisy = (signal + noise).astype(np.float32)
    path_noisy = FIXTURES_DIR / "noisy_5db.wav"
    sf.write(str(path_noisy), noisy, sr)
    created_files["noisy"] = path_noisy

    # 6. Polyphonic music simulation (multi-chord) (30 seconds)
    t = np.linspace(0, 30, int(sr * 30), endpoint=False, dtype=np.float32)
    # C major chord: C4 (261.63), E4 (329.63), G4 (392.00)
    music = (
        0.2 * np.sin(2 * np.pi * 261.63 * t) +
        0.2 * np.sin(2 * np.pi * 329.63 * t) +
        0.2 * np.sin(2 * np.pi * 392.00 * t)
    ).astype(np.float32)
    path_music = FIXTURES_DIR / "music_chord.wav"
    sf.write(str(path_music), music, sr)
    created_files["music"] = path_music

    # 7. Short duration clip (< 1s, 0.5s)
    short_audio = np.sin(2 * np.pi * 440 * np.linspace(0, 0.5, int(sr * 0.5), endpoint=False, dtype=np.float32))
    path_short = FIXTURES_DIR / "short_clip.wav"
    sf.write(str(path_short), short_audio, sr)
    created_files["short"] = path_short

    # 8. Extended conversational mock speech (100 seconds)
    t = np.linspace(0, 100, int(sr * 100), endpoint=False, dtype=np.float32)
    speech_mock = (
        0.25 * np.sin(2 * np.pi * 180 * t) +
        0.15 * np.sin(2 * np.pi * 360 * t) +
        0.10 * np.sin(2 * np.pi * 900 * t)
    ).astype(np.float32)
    # Modulation with conversational pauses
    pause_mask = (np.sin(2 * np.pi * 0.2 * t) > -0.2).astype(np.float32)
    speech_mock = speech_mock * pause_mask
    path_long = FIXTURES_DIR / "extended_speech.wav"
    sf.write(str(path_long), speech_mock, sr)
    created_files["extended_speech"] = path_long

    return created_files


if __name__ == "__main__":
    files = generate_fixtures()
    total_dur = sum(sf.info(str(p)).duration for p in files.values())
    print(f"Generated {len(files)} test fixtures, total duration: {total_dur:.1f}s (~{total_dur / 60:.2f} mins)")
