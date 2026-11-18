"""Content-addressed caching mechanism for pipeline idempotency and resumability."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from audio_token_pipeline import __version__

logger = logging.getLogger(__name__)


def compute_cache_key(
    input_hash: str,
    stage_name: str,
    config_hash: str,
    code_version: str = __version__,
) -> str:
    """
    Generate a deterministic content-addressed SHA-256 cache key.
    Formula: SHA-256(input_hash + ":" + stage_name + ":" + config_hash + ":" + code_version)
    """
    raw = f"{input_hash}:{stage_name}:{config_hash}:{code_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ContentAddressedCache:
    """Filesystem-based content-addressed cache store."""

    def __init__(self, cache_dir: Path | str = ".cache/atp"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_entry_path(self, cache_key: str) -> Path:
        """Partition by the first 2 characters of the key to prevent directory overload."""
        prefix = cache_key[:2]
        return self.cache_dir / prefix / f"{cache_key}.json"

    def exists(self, cache_key: str) -> bool:
        """Check if an item exists in the cache."""
        return self._get_entry_path(cache_key).is_file()

    def get(self, cache_key: str) -> dict[str, Any] | None:
        """Retrieve cached payload by key."""
        path = self._get_entry_path(cache_key)
        if not path.is_file():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning(f"Failed to read cache entry {cache_key}: {e}")
            return None

    def put(self, cache_key: str, data: dict[str, Any]) -> Path:
        """Store payload by key atomically."""
        path = self._get_entry_path(cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True, default=str)
        temp_path.replace(path)
        return path

    def clear(self) -> None:
        """Remove all cache entries."""
        import shutil
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
