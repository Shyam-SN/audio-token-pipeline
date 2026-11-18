"""Unit tests for audio decode verification."""

from pathlib import Path

from audio_token_pipeline.io.decode import decode_and_verify_audio, read_wav_header_duration


def test_decode_non_existent_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.wav"
    is_valid, meta, err = decode_and_verify_audio(missing)
    assert not is_valid
    assert err is not None and "EMPTY" in err


def test_decode_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.wav"
    empty.touch()
    is_valid, meta, err = decode_and_verify_audio(empty)
    assert not is_valid
    assert err is not None and "EMPTY" in err


def test_read_wav_header_duration_invalid(tmp_path: Path) -> None:
    not_wav = tmp_path / "not_wav.txt"
    not_wav.write_text("plain text file", encoding="utf-8")
    assert read_wav_header_duration(not_wav) is None

