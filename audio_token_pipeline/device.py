"""Device abstraction and backend detection for CPU, MPS (Apple Silicon), and CUDA."""

from __future__ import annotations

import logging
import platform
from typing import Literal

logger = logging.getLogger(__name__)

DeviceType = Literal["cpu", "mps", "cuda"]


def is_cuda_available() -> bool:
    """Check if CUDA is available via PyTorch."""
    try:
        import torch
        return bool(torch.cuda.is_available())
    except ImportError:
        return False


def is_mps_available() -> bool:
    """Check if Apple Silicon MPS is available and built."""
    if platform.system() != "Darwin":
        return False
    try:
        import torch
        return bool(torch.backends.mps.is_available() and torch.backends.mps.is_built())
    except ImportError:
        # Check macOS arm64 environment even if torch is not yet imported
        return platform.machine() == "arm64"


def detect_optimal_device() -> DeviceType:
    """Auto-detect the best available compute device."""
    if is_cuda_available():
        return "cuda"
    if is_mps_available():
        return "mps"
    return "cpu"


def resolve_device(requested: str | None = None) -> DeviceType:
    """
    Resolve requested device ('cpu' | 'mps' | 'cuda' | 'auto') to an available device.
    Falls back gracefully if requested acceleration is unavailable.
    """
    if not requested or requested.lower() == "auto":
        return detect_optimal_device()

    req = requested.lower().strip()
    if req == "cuda":
        if is_cuda_available():
            return "cuda"
        logger.warning("CUDA requested but not available. Falling back to CPU.")
        return "cpu"
    elif req == "mps":
        if is_mps_available():
            return "mps"
        logger.warning("MPS requested but not available. Falling back to CPU.")
        return "cpu"
    elif req == "cpu":
        return "cpu"
    else:
        logger.warning(f"Unknown device '{requested}'. Defaulting to CPU.")
        return "cpu"


def get_device(requested: str | None = None) -> str:
    """Return device string ('cpu', 'mps', or 'cuda')."""
    return resolve_device(requested)


def get_torch_device(requested: str | None = None):  # type: ignore[no-untyped-def]
    """Return a torch.device object."""
    import torch
    dev = resolve_device(requested)
    return torch.device(dev)


def get_device_info() -> dict[str, str | int | float | bool]:
    """Return diagnostic information about current machine and hardware accelerators."""
    info: dict[str, str | int | float | bool] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "cuda_available": is_cuda_available(),
        "mps_available": is_mps_available(),
        "optimal_device": detect_optimal_device(),
    }

    # RAM detection (in GB)
    try:
        import os
        if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names and "SC_PHYS_PAGES" in os.sysconf_names:
            total_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
            info["ram_gb"] = round(total_bytes / (1024**3), 2)
    except Exception:
        pass

    # CUDA device name if present
    if is_cuda_available():
        try:
            import torch
            info["cuda_device_name"] = torch.cuda.get_device_name(0)
            info["cuda_device_count"] = torch.cuda.device_count()
            info["cuda_vram_gb"] = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2)
        except Exception:
            pass

    return info
