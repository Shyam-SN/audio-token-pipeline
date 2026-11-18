"""Resumable parallel downloader with SHA-256 integrity verification and Parquet manifest generation."""

from __future__ import annotations

import hashlib
import logging
import tarfile
from collections.abc import Callable
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import soundfile as sf

from audio_token_pipeline.catalog import Catalog

logger = logging.getLogger(__name__)


def compute_file_sha256(filepath: Path | str, chunk_size: int = 1024 * 1024) -> str:
    """Compute the SHA-256 hash of a file efficiently without loading it fully into RAM."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def download_file_resumable(
    url: str,
    dest_path: Path,
    expected_sha256: str | None = None,
    progress_callback: Callable[[int], None] | None = None,
) -> Path:
    """
    Download a file with HTTP Range support for resumption and optional SHA-256 verification.
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(dest_path.suffix + ".part")

    existing_bytes = temp_path.stat().st_size if temp_path.exists() else 0

    headers = {}
    if existing_bytes > 0:
        headers["Range"] = f"bytes={existing_bytes}-"

    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        with client.stream("GET", url, headers=headers) as response:
            if response.status_code == 416:  # Range Not Satisfiable -> already completed
                pass
            elif response.status_code not in (200, 206):
                raise RuntimeError(
                    f"Download failed for {url} with status {response.status_code}: {response.text}"
                )

            mode = "ab" if response.status_code == 206 else "wb"
            if response.status_code == 200:
                existing_bytes = 0

            with open(temp_path, mode) as f:
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    f.write(chunk)
                    if progress_callback:
                        progress_callback(len(chunk))

    if expected_sha256:
        calculated_sha = compute_file_sha256(temp_path)
        if calculated_sha.lower() != expected_sha256.lower():
            raise ValueError(
                f"Checksum mismatch for {dest_path.name}: expected {expected_sha256}, got {calculated_sha}"
            )

    temp_path.replace(dest_path)
    return dest_path


def scan_audio_metadata(filepath: Path) -> dict[str, str | int | float | None]:
    """Inspect audio file header without full PCM decoding to obtain duration, rate, and channels."""
    try:
        info = sf.info(str(filepath))
        return {
            "duration_s": float(info.duration),
            "sample_rate": int(info.samplerate),
            "channels": int(info.channels),
            "format": str(info.format),
            "subtype": str(info.subtype),
        }
    except Exception as e:
        logger.debug(f"SoundFile header inspection failed for {filepath}: {e}")
        return {
            "duration_s": None,
            "sample_rate": None,
            "channels": None,
            "format": None,
            "subtype": None,
        }


def extract_archive(archive_path: Path, extract_dir: Path) -> None:
    """Safely extract tar.gz / tar archives avoiding path traversal."""
    extract_dir.mkdir(parents=True, exist_ok=True)
    if archive_path.name.endswith(".tar.gz") or archive_path.name.endswith(".tgz"):
        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                target_path = extract_dir / member.name
                if not target_path.resolve().is_relative_to(extract_dir.resolve()):
                    raise ValueError(f"Path traversal detected in archive: {member.name}")
            tar.extractall(extract_dir)
    elif archive_path.name.endswith(".tar"):
        with tarfile.open(archive_path, "r:") as tar:
            tar.extractall(extract_dir)


def build_manifest_parquet(
    audio_dir: Path,
    manifest_path: Path,
    dataset_name: str,
    split_name: str,
    license_str: str,
    max_hours: float | None = None,
    catalog: Catalog | None = None,
) -> Path:
    """
    Scan audio files, calculate checksums and header metadata, register into Catalog,
    and output a local manifest.parquet.
    """
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    audio_extensions = {".flac", ".wav", ".mp3", ".ogg", ".opus", ".m4a"}

    files = [
        p for p in audio_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in audio_extensions
    ]
    files.sort()

    records = []
    total_seconds = 0.0
    max_seconds = max_hours * 3600.0 if max_hours else float("inf")

    for fpath in files:
        if total_seconds >= max_seconds:
            break

        meta = scan_audio_metadata(fpath)
        sha = compute_file_sha256(fpath)
        duration = float(meta["duration_s"]) if meta["duration_s"] is not None else 0.0

        rel_path = str(fpath.relative_to(audio_dir))
        source_id = f"{dataset_name}_{split_name}_{fpath.stem}_{sha[:8]}"

        record = {
            "source_id": source_id,
            "filepath": str(fpath.resolve()),
            "relative_path": rel_path,
            "dataset": dataset_name,
            "split": split_name,
            "duration_s": duration,
            "sample_rate": meta["sample_rate"],
            "channels": meta["channels"],
            "format": meta["format"],
            "sha256": sha,
            "license": license_str,
        }
        records.append(record)
        total_seconds += duration

        if catalog:
            catalog.register_source(
                source_id=source_id,
                filepath=str(fpath.resolve()),
                dataset=dataset_name,
                split=split_name,
                duration_s=duration,
                sample_rate=meta["sample_rate"],  # type: ignore[arg-type]
                channels=meta["channels"],  # type: ignore[arg-type]
                sha256=sha,
                status="PENDING",
            )

    table = pa.Table.from_pylist(records)
    pq.write_table(table, str(manifest_path))
    logger.info(
        f"Manifest written to {manifest_path} with {len(records)} files ({round(total_seconds / 3600, 2)} hours)"
    )
    return manifest_path
