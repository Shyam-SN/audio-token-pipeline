"""Unit tests for content-addressed cache."""

from pathlib import Path

from audio_token_pipeline.cache import ContentAddressedCache, compute_cache_key


def test_compute_cache_key() -> None:
    k1 = compute_cache_key("shaA", "ingest", "cfg1", "0.1.0")
    k2 = compute_cache_key("shaA", "ingest", "cfg1", "0.1.0")
    assert k1 == k2

    # Changing any component should alter the cache key
    assert k1 != compute_cache_key("shaB", "ingest", "cfg1", "0.1.0")
    assert k1 != compute_cache_key("shaA", "segment", "cfg1", "0.1.0")
    assert k1 != compute_cache_key("shaA", "ingest", "cfg2", "0.1.0")
    assert k1 != compute_cache_key("shaA", "ingest", "cfg1", "0.2.0")


def test_cache_put_get(tmp_path: Path) -> None:
    cache = ContentAddressedCache(tmp_path / "test_cache")
    key = compute_cache_key("sha123", "ingest", "cfghash", "0.1.0")

    assert not cache.exists(key)
    assert cache.get(key) is None

    payload = {"status": "SUCCESS", "duration_s": 12.4, "sample_rate": 24000}
    cache.put(key, payload)

    assert cache.exists(key)
    retrieved = cache.get(key)
    assert retrieved == payload

    cache.clear()
    assert not cache.exists(key)
