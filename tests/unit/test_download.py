"""Unit tests for downloader, checksum verification, resumable HTTP downloads, and manifest generation."""

import hashlib
from pathlib import Path

import httpx
import pyarrow.parquet as pq
import pytest

from audio_token_pipeline.catalog import Catalog
from audio_token_pipeline.io.download import (
    build_manifest_parquet,
    compute_file_sha256,
    download_file_resumable,
    scan_audio_metadata,
)

FIXTURES_DIR = Path("tests/fixtures")


def test_compute_file_sha256(tmp_path: Path) -> None:
    test_file = tmp_path / "hello.txt"
    test_file.write_text("audio-token-pipeline test string", encoding="utf-8")

    sha = compute_file_sha256(test_file)
    assert len(sha) == 64
    assert sha == compute_file_sha256(test_file)


def test_scan_audio_metadata() -> None:
    clean_fixture = FIXTURES_DIR / "clean_formant.wav"
    assert clean_fixture.exists(), "Clean fixture should exist"

    meta = scan_audio_metadata(clean_fixture)
    assert meta["sample_rate"] == 24000
    assert meta["channels"] == 1
    assert meta["duration_s"] is not None
    assert abs(float(meta["duration_s"]) - 40.0) < 0.1


def test_scan_audio_metadata_extended_fixtures() -> None:
    # 16k rate
    f16k = FIXTURES_DIR / "rate_16k.wav"
    if f16k.exists():
        m16 = scan_audio_metadata(f16k)
        assert m16["sample_rate"] == 16000

    # 44.1k rate
    f44k = FIXTURES_DIR / "rate_44k.wav"
    if f44k.exists():
        m44 = scan_audio_metadata(f44k)
        assert m44["sample_rate"] == 44100

    # 48k rate
    f48k = FIXTURES_DIR / "rate_48k.wav"
    if f48k.exists():
        m48 = scan_audio_metadata(f48k)
        assert m48["sample_rate"] == 48000

    # Stereo
    fst = FIXTURES_DIR / "stereo.wav"
    if fst.exists():
        mst = scan_audio_metadata(fst)
        assert mst["channels"] == 2

    # FLAC format
    fflac = FIXTURES_DIR / "format_speech.flac"
    if fflac.exists():
        mflac = scan_audio_metadata(fflac)
        assert mflac["format"] == "FLAC"

    # Real LibriSpeech clip
    libri_clips = list(FIXTURES_DIR.glob("librispeech_*.flac"))
    assert len(libri_clips) >= 3, "Should have at least 3 real LibriSpeech dev-clean clips"
    for l_clip in libri_clips[:3]:
        m_lib = scan_audio_metadata(l_clip)
        assert m_lib["sample_rate"] == 16000
        assert m_lib["channels"] == 1
        assert m_lib["duration_s"] is not None and m_lib["duration_s"] > 0


def test_build_manifest_parquet(tmp_path: Path) -> None:
    manifest_out = tmp_path / "manifest.parquet"
    db_path = tmp_path / "cat.duckdb"
    catalog = Catalog(db_path)

    build_manifest_parquet(
        audio_dir=FIXTURES_DIR,
        manifest_path=manifest_out,
        dataset_name="smoke_test",
        split_name="fixtures",
        license_str="MIT",
        max_hours=1.0,
        catalog=catalog,
    )

    assert manifest_out.exists()
    table = pq.read_table(str(manifest_out))
    records = table.to_pylist()
    assert len(records) >= 15  # All generated fixture files + real LibriSpeech clips
    assert "source_id" in table.column_names
    assert "sha256" in table.column_names
    assert "duration_s" in table.column_names

    # Verify DuckDB was populated
    summary = catalog.get_stage_status_summary()
    assert summary["sources_total"] == len(records)


def test_download_file_resumable_full(tmp_path: Path) -> None:
    content = b"AUDIO_DATA_PAYLOAD" * 50
    expected_sha = hashlib.sha256(content).hexdigest()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, headers={"Content-Length": str(len(content))})

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    out_file = tmp_path / "downloaded.bin"

    res = download_file_resumable(
        url="http://mock.server/audio.bin",
        dest_path=out_file,
        expected_sha256=expected_sha,
        client=client,
    )
    assert res.exists()
    assert res.read_bytes() == content


def test_download_file_resumable_checksum_mismatch(tmp_path: Path) -> None:
    content = b"AUDIO_DATA_PAYLOAD" * 50
    wrong_sha = "0" * 64

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, headers={"Content-Length": str(len(content))})

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    out_file = tmp_path / "bad_checksum.bin"

    with pytest.raises(ValueError, match="Checksum mismatch"):
        download_file_resumable(
            url="http://mock.server/audio.bin",
            dest_path=out_file,
            expected_sha256=wrong_sha,
            client=client,
        )


def test_download_file_resumable_resume(tmp_path: Path) -> None:
    full_content = b"PREFIX_INITIAL_BYTES_" + b"REMAINING_STREAM_BYTES" * 30
    full_sha = hashlib.sha256(full_content).hexdigest()

    out_file = tmp_path / "resumed.bin"
    temp_part = tmp_path / "resumed.bin.part"

    # Simulate an interrupted download where initial 21 bytes were written
    initial_bytes = b"PREFIX_INITIAL_BYTES_"
    temp_part.write_bytes(initial_bytes)
    initial_len = len(initial_bytes)

    range_header_captured: list[str] = []

    def mock_range_handler(request: httpx.Request) -> httpx.Response:
        range_hdr = request.headers.get("Range")
        if range_hdr:
            range_header_captured.append(range_hdr)
            start_offset = int(range_hdr.split("=")[1].split("-")[0])
            slice_data = full_content[start_offset:]
            return httpx.Response(
                206,
                content=slice_data,
                headers={
                    "Content-Range": f"bytes {start_offset}-{len(full_content)-1}/{len(full_content)}",
                    "Content-Length": str(len(slice_data)),
                },
            )
        return httpx.Response(200, content=full_content)

    client = httpx.Client(transport=httpx.MockTransport(mock_range_handler))

    res = download_file_resumable(
        url="http://mock.server/audio.bin",
        dest_path=out_file,
        expected_sha256=full_sha,
        client=client,
    )

    assert len(range_header_captured) == 1
    assert range_header_captured[0] == f"bytes={initial_len}-"
    assert res.exists()
    assert res.read_bytes() == full_content
    assert not temp_part.exists()


def test_download_file_resumable_http_error(tmp_path: Path) -> None:
    def mock_error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"Not Found")

    client = httpx.Client(transport=httpx.MockTransport(mock_error_handler))
    out_file = tmp_path / "missing.bin"

    with pytest.raises(RuntimeError, match="Download failed for http://mock.server/missing with status 404"):
        download_file_resumable(
            url="http://mock.server/missing",
            dest_path=out_file,
            client=client,
        )
