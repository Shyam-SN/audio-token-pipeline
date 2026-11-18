"""Generate a comprehensive synthetic audio fixture suite for smoke testing, format, and filter verification."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

FIXTURES_DIR = Path(__file__).parent


def generate_fixtures() -> dict[str, Path]:
    """Generate various audio conditions, rates, channel layouts, codecs, and faulty files."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    sr_default = 24000
    created_files: dict[str, Path] = {}

    # 1. Clean speech-like harmonic formants (40 seconds, 24kHz mono)
    t = np.linspace(0, 40, int(sr_default * 40), endpoint=False, dtype=np.float32)
    clean_audio = (
        0.3 * np.sin(2 * np.pi * 150 * t) +
        0.2 * np.sin(2 * np.pi * 300 * t) +
        0.15 * np.sin(2 * np.pi * 750 * t) +
        0.1 * np.sin(2 * np.pi * 1200 * t)
    ).astype(np.float32)
    envelope = (np.sin(2 * np.pi * 3 * t) + 1.0) / 2.0
    clean_audio = clean_audio * envelope
    path_clean = FIXTURES_DIR / "clean_formant.wav"
    sf.write(str(path_clean), clean_audio, sr_default)
    created_files["clean"] = path_clean

    # 2. Pure silence (30 seconds, 24kHz mono)
    silence = np.zeros(int(sr_default * 30), dtype=np.float32)
    path_silence = FIXTURES_DIR / "silence.wav"
    sf.write(str(path_silence), silence, sr_default)
    created_files["silence"] = path_silence

    # 3. Severely clipped audio (30 seconds, 24kHz mono)
    t = np.linspace(0, 30, int(sr_default * 30), endpoint=False, dtype=np.float32)
    loud_sine = 3.0 * np.sin(2 * np.pi * 440 * t)
    clipped = np.clip(loud_sine, -1.0, 1.0).astype(np.float32)
    path_clipped = FIXTURES_DIR / "clipped.wav"
    sf.write(str(path_clipped), clipped, sr_default)
    created_files["clipped"] = path_clipped

    # 4. DC offset bias (30 seconds, 24kHz mono)
    t = np.linspace(0, 30, int(sr_default * 30), endpoint=False, dtype=np.float32)
    dc_audio = (0.2 * np.sin(2 * np.pi * 220 * t) + 0.05).astype(np.float32)
    path_dc = FIXTURES_DIR / "dc_offset.wav"
    sf.write(str(path_dc), dc_audio, sr_default)
    created_files["dc_offset"] = path_dc

    # 5. Low SNR noisy audio (~5 dB SNR) (40 seconds, 24kHz mono)
    t = np.linspace(0, 40, int(sr_default * 40), endpoint=False, dtype=np.float32)
    signal = 0.2 * np.sin(2 * np.pi * 350 * t)
    noise = np.random.default_rng(42).normal(0, 0.15, size=len(t)).astype(np.float32)
    noisy = (signal + noise).astype(np.float32)
    path_noisy = FIXTURES_DIR / "noisy_5db.wav"
    sf.write(str(path_noisy), noisy, sr_default)
    created_files["noisy"] = path_noisy

    # 6. Polyphonic music simulation (multi-chord) (30 seconds, 24kHz mono)
    t = np.linspace(0, 30, int(sr_default * 30), endpoint=False, dtype=np.float32)
    music = (
        0.2 * np.sin(2 * np.pi * 261.63 * t) +
        0.2 * np.sin(2 * np.pi * 329.63 * t) +
        0.2 * np.sin(2 * np.pi * 392.00 * t)
    ).astype(np.float32)
    path_music = FIXTURES_DIR / "music_chord.wav"
    sf.write(str(path_music), music, sr_default)
    created_files["music"] = path_music

    # 7. Short duration clip (< 1s, 0.5s)
    short_audio = np.sin(2 * np.pi * 440 * np.linspace(0, 0.5, int(sr_default * 0.5), endpoint=False, dtype=np.float32))
    path_short = FIXTURES_DIR / "short_clip.wav"
    sf.write(str(path_short), short_audio, sr_default)
    created_files["short"] = path_short

    # 8. Extended mock conversational speech (100 seconds, 24kHz mono)
    t = np.linspace(0, 100, int(sr_default * 100), endpoint=False, dtype=np.float32)
    speech_mock = (
        0.25 * np.sin(2 * np.pi * 180 * t) +
        0.15 * np.sin(2 * np.pi * 360 * t) +
        0.10 * np.sin(2 * np.pi * 900 * t)
    ).astype(np.float32)
    pause_mask = (np.sin(2 * np.pi * 0.2 * t) > -0.2).astype(np.float32)
    speech_mock = speech_mock * pause_mask
    path_long = FIXTURES_DIR / "extended_speech.wav"
    sf.write(str(path_long), speech_mock, sr_default)
    created_files["extended_speech"] = path_long

    # 9. Sample Rate Variations: 16kHz, 44.1kHz, 48kHz (5 seconds each)
    t16 = np.linspace(0, 5, int(16000 * 5), endpoint=False, dtype=np.float32)
    sig16 = 0.3 * np.sin(2 * np.pi * 440 * t16)
    path_16k = FIXTURES_DIR / "rate_16k.wav"
    sf.write(str(path_16k), sig16, 16000)
    created_files["rate_16k"] = path_16k

    t44 = np.linspace(0, 5, int(44100 * 5), endpoint=False, dtype=np.float32)
    sig44 = 0.3 * np.sin(2 * np.pi * 440 * t44)
    path_44k = FIXTURES_DIR / "rate_44k.wav"
    sf.write(str(path_44k), sig44, 44100)
    created_files["rate_44k"] = path_44k

    t48 = np.linspace(0, 5, int(48000 * 5), endpoint=False, dtype=np.float32)
    sig48 = 0.3 * np.sin(2 * np.pi * 440 * t48)
    path_48k = FIXTURES_DIR / "rate_48k.wav"
    sf.write(str(path_48k), sig48, 48000)
    created_files["rate_48k"] = path_48k

    # 10. Stereo audio (2 channels, 5 seconds)
    t_st = np.linspace(0, 5, int(sr_default * 5), endpoint=False, dtype=np.float32)
    left_ch = 0.3 * np.sin(2 * np.pi * 440 * t_st)
    right_ch = 0.3 * np.sin(2 * np.pi * 880 * t_st)
    stereo_audio = np.stack([left_ch, right_ch], axis=-1)
    path_stereo = FIXTURES_DIR / "stereo.wav"
    sf.write(str(path_stereo), stereo_audio, sr_default)
    created_files["stereo"] = path_stereo

    # 11. Codec / Format Variations: FLAC, MP3, Opus (5 seconds each)
    t_fmt = np.linspace(0, 5, int(sr_default * 5), endpoint=False, dtype=np.float32)
    sig_fmt = 0.3 * np.sin(2 * np.pi * 300 * t_fmt)

    path_flac = FIXTURES_DIR / "format_speech.flac"
    sf.write(str(path_flac), sig_fmt, sr_default, format="FLAC")
    created_files["flac"] = path_flac

    path_mp3 = FIXTURES_DIR / "format_speech.mp3"
    sf.write(str(path_mp3), sig_fmt, sr_default, format="MP3")
    created_files["mp3"] = path_mp3

    path_opus = FIXTURES_DIR / "format_speech.opus"
    # Opus requires standard rates (e.g. 48000)
    t_opus = np.linspace(0, 5, int(48000 * 5), endpoint=False, dtype=np.float32)
    sig_opus = 0.3 * np.sin(2 * np.pi * 300 * t_opus)
    sf.write(str(path_opus), sig_opus, 48000, format="OGG", subtype="OPUS")
    created_files["opus"] = path_opus

    # 12. Truncated audio file (corrupted header/payload mismatch)
    path_trunc = FIXTURES_DIR / "truncated.wav"
    # Write a normal 2-second wav
    t_tr = np.linspace(0, 2, int(sr_default * 2), endpoint=False, dtype=np.float32)
    sf.write(str(path_trunc), 0.3 * np.sin(2 * np.pi * 440 * t_tr), sr_default)
    # Truncate to 128 bytes, leaving invalid partial payload
    with open(path_trunc, "r+b") as f:
        f.truncate(128)
    created_files["truncated"] = path_trunc

    # 13. Include 3 real LibriSpeech dev-clean clips if present
    for lib_path in FIXTURES_DIR.glob("librispeech_*.flac"):
        created_files[lib_path.stem] = lib_path

    return created_files


if __name__ == "__main__":
    files = generate_fixtures()
    valid_dur = 0.0
    for p in files.values():
        try:
            valid_dur += sf.info(str(p)).duration
        except Exception:
            pass
    print(f"Generated {len(files)} test fixtures, total valid duration: {valid_dur:.1f}s (~{valid_dur / 60:.2f} mins)")
