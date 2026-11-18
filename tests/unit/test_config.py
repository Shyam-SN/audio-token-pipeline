"""Unit tests for configuration models and hash stability."""

from pathlib import Path

from audio_token_pipeline.config import AppConfig


def test_default_config() -> None:
    cfg = AppConfig()
    assert cfg.version == "0.1.0"
    assert cfg.ingest.target_sample_rate == 24000
    assert cfg.ingest.target_channels == 1
    assert cfg.ingest.target_lufs == -23.0


def test_config_hash_stability() -> None:
    cfg1 = AppConfig()
    cfg2 = AppConfig()

    hash1 = cfg1.compute_hash()
    hash2 = cfg2.compute_hash()
    assert hash1 == hash2
    assert len(hash1) == 16

    # Modifying ingest should change the hash
    cfg2.ingest.target_sample_rate = 16000
    assert cfg1.compute_hash() != cfg2.compute_hash()
    assert cfg1.compute_hash("ingest") != cfg2.compute_hash("ingest")
    # But shouldn't change the segment stage hash
    assert cfg1.compute_hash("segment") == cfg2.compute_hash("segment")


def test_yaml_roundtrip(tmp_path: Path) -> None:
    cfg = AppConfig()
    yaml_path = tmp_path / "test_config.yaml"
    cfg.to_yaml(yaml_path)

    loaded = AppConfig.from_yaml(yaml_path)
    assert loaded.version == cfg.version
    assert loaded.compute_hash() == cfg.compute_hash()


def test_load_all_predefined_configs() -> None:
    for name in ["dev_mac.yaml", "kaggle_t4.yaml", "bench_1000h.yaml"]:
        p = Path("configs") / name
        assert p.exists(), f"Predefined config {name} is missing"
        cfg = AppConfig.from_yaml(p)
        assert cfg.compute_hash() is not None
