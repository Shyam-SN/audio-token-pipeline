"""Pydantic configuration models for all pipeline stages and hardware profiles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class DeviceConfig(BaseModel):
    device: Literal["auto", "cpu", "mps", "cuda"] = "auto"
    num_workers: int = Field(default=4, ge=1, description="Number of worker processes for CPU stages")
    pin_memory: bool = True
    memory_limit_gb: float = Field(default=14.0, description="Max RAM consumption flag threshold (Mac M4 is 16GB)")


class DatasetConfig(BaseModel):
    name: str = "librispeech"
    split: str = "dev-clean"
    urls: list[str] = Field(default_factory=list)
    download_dir: Path = Path("data/raw")
    manifest_path: Path = Path("data/manifest.parquet")
    license: str = "CC-BY-4.0"
    max_hours: float | None = None


class IngestConfig(BaseModel):
    target_sample_rate: int = 24000
    target_channels: int = 1
    target_lufs: float = -23.0
    resample_quality: str = "soxr_hq"
    supported_formats: list[str] = Field(
        default_factory=lambda: ["flac", "mp3", "opus", "ogg", "m4a", "wav"]
    )


class SegmentConfig(BaseModel):
    vad_model: str = "silero_vad"
    vad_threshold: float = 0.5
    sample_rate: int = 16000
    min_speech_duration_s: float = 2.0
    max_speech_duration_s: float = 30.0
    speech_pad_s: float = 0.2
    energy_split_window_s: float = 0.5


class FilterConfig(BaseModel):
    max_silence_ratio: float = 0.40
    max_clip_fraction: float = 0.001
    clip_threshold: float = 0.999
    min_snr_db: float = 10.0
    max_dc_offset: float = 0.01
    min_duration_s: float = 2.0
    max_duration_s: float = 30.0
    duplicate_similarity_threshold: float = 0.95
    min_speech_prob: float = 0.60
    whisper_expected_lang: str | None = None


class TranscribeConfig(BaseModel):
    model_name: str = "large-v3-turbo"
    backend: Literal["auto", "mlx", "faster-whisper", "whisper"] = "auto"
    compute_type: str = "float16"
    min_avg_logprob: float = -1.0
    max_no_speech_prob: float = 0.6
    bucket_batch_size: int = 16
    max_padding_ratio: float = 0.20


class TokenizeConfig(BaseModel):
    codec: Literal["mimi", "encodec"] = "mimi"
    target_bandwidth: float = 12.5  # 12.5 Hz frame rate for Mimi
    num_codebooks: int = 8
    sample_rate: int = 24000
    dtype: str = "int16"
    batch_size: int = 8
    queue_size: int = 16


class ShardConfig(BaseModel):
    target_shard_size_mb: int = 1024  # 1 GB per shard
    output_dir: Path = Path("data/shards")
    version: str = "v0.1.0"
    shard_pattern: str = "atp-{version}-{split}-{shard_id:06d}.tar"
    train_val_split_seed: int = 42
    val_ratio: float = 0.05


class FeedBenchConfig(BaseModel):
    token_budget_per_batch: int = 65536
    shuffle_buffer_size: int = 5000
    num_workers: int = 4
    probe_model_layers: int = 4
    probe_model_dim: int = 512
    max_steps: int = 500
    target_max_stall_pct: float = 5.0


class AppConfig(BaseModel):
    version: str = "0.1.0"
    catalog_path: Path = Path("catalog.duckdb")
    cache_dir: Path = Path(".cache/atp")
    device: DeviceConfig = Field(default_factory=DeviceConfig)
    dataset: DatasetConfig = Field(default_factory=DatasetConfig)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    segment: SegmentConfig = Field(default_factory=SegmentConfig)
    filter: FilterConfig = Field(default_factory=FilterConfig)
    transcribe: TranscribeConfig = Field(default_factory=TranscribeConfig)
    tokenize: TokenizeConfig = Field(default_factory=TokenizeConfig)
    shard: ShardConfig = Field(default_factory=ShardConfig)
    feed: FeedBenchConfig = Field(default_factory=FeedBenchConfig)

    def compute_hash(self, stage_name: str | None = None) -> str:
        """Compute a deterministic SHA-256 hash of the configuration (or a specific stage)."""
        if stage_name:
            stage_data = getattr(self, stage_name, None)
            if stage_data is not None:
                payload = stage_data.model_dump(mode="json")
            else:
                payload = {"stage": stage_name}
        else:
            payload = self.model_dump(mode="json")

        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def from_yaml(cls, path: Path | str) -> AppConfig:
        """Load configuration from a YAML file."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)

    def to_yaml(self, path: Path | str) -> None:
        """Save configuration to a YAML file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.model_dump(mode="json"), f, sort_keys=False)
