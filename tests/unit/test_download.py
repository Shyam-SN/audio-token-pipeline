"""Unit tests for downloader, checksum verification, resumable HTTP downloads, and manifest generation."""

import hashlib
from pathlib import Path

import httpx
import pyarrow.parquet as pq
import pytest

from audio_token_pipeline.catalog import Catalog
from audio_token_pipeline.io.decode import decode_and_verify_audio
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
        assert isinstance(m_lib["duration_s"], (int, float)) and m_lib["duration_s"] > 0


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
    # 18 valid files registered into manifest
    assert len(records) == 18
    assert "source_id" in table.column_names
    assert "sha256" in table.column_names
    assert "duration_s" in table.column_names

    # Verify DuckDB: 18 registered, 1 quarantined (truncated.wav)
    summary = catalog.get_stage_status_summary()
    assert summary["sources_total"] == 18
    assert summary["dead_letter"] == 1

    dead_letters = catalog.get_dead_letters()
    assert len(dead_letters) == 1
    assert dead_letters[0]["reason_code"] == "DECODE_FAIL"
    assert "truncated" in dead_letters[0]["item_id"]


def test_decode_all_fixtures_integrity() -> None:
    """Test full decoding of every fixture verifying rate, channels, duration and official SHA-256."""
    fixtures = [
        p for p in sorted(FIXTURES_DIR.glob("*.*")) if p.suffix not in (".py", ".parquet", ".txt")
    ]
    assert len(fixtures) == 19, f"Expected 19 fixture files, found {len(fixtures)}"

    valid_count = 0
    quarantine_count = 0

    # Official published SHA-256 checksums from OpenSLR dev-clean.tar.gz
    official_openslr_hashes = {
        "librispeech_2277-149896-0000.flac": "fead3e0c481f1c637fe6ec8edef42506c7c2d33a3fb7519bfdf5815b31150303",
        "librispeech_2277-149896-0001.flac": "f9c3371b4d1c6e95e7c01298a26215c2be97bee22c5408885d8d29b6e0e4171c",
        "librispeech_2277-149896-0002.flac": "ade2caad47934462292358ba49acf7f048ced0595615492b4b20866d118bf901",
    }

    for fpath in fixtures:
        is_valid, meta, err = decode_and_verify_audio(fpath)
        if fpath.name == "truncated.wav":
            assert not is_valid, "truncated.wav must fail decode verification"
            assert err is not None and "DECODE_FAIL" in err
            quarantine_count += 1
        else:
            assert is_valid, f"Fixture {fpath.name} failed decode verification: {err}"
            valid_count += 1
            assert meta["sample_rate"] in (16000, 24000, 44100, 48000)
            assert meta["channels"] in (1, 2)
            assert meta["duration_s"] > 0
            assert meta["num_samples"] == int(round(meta["duration_s"] * meta["sample_rate"]))

            # Verify official LibriSpeech files against OpenSLR archive checksums
            if fpath.name in official_openslr_hashes:
                file_sha = compute_file_sha256(fpath)
                assert file_sha == official_openslr_hashes[fpath.name], (
                    f"SHA-256 mismatch for {fpath.name}: expected {official_openslr_hashes[fpath.name]}, got {file_sha}"
                )

    assert valid_count == 18
    assert quarantine_count == 1


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
                    "Content-Range": f"bytes {start_offset}-{len(full_content) - 1}/{len(full_content)}",
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

    with pytest.raises(
        RuntimeError, match="Download failed for http://mock.server/missing with status 404"
    ):
        download_file_resumable(
            url="http://mock.server/missing",
            dest_path=out_file,
            client=client,
        )
