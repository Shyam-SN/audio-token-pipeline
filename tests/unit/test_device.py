"""Unit tests for device abstraction and backend detection."""

import pytest
import torch

from audio_token_pipeline.device import (
    get_device_info,
    get_torch_device,
    resolve_device,
)


def test_resolve_device_explicit() -> None:
    # CPU should always resolve to CPU
    assert resolve_device("cpu") == "cpu"

    # Auto should resolve to cpu, mps, or cuda
    dev = resolve_device("auto")
    assert dev in ("cpu", "mps", "cuda")


def test_resolve_device_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    # If CUDA is requested on a non-CUDA host, it should cleanly fall back to CPU
    monkeypatch.setattr("audio_token_pipeline.device.is_cuda_available", lambda: False)
    assert resolve_device("cuda") == "cpu"


def test_get_torch_device() -> None:
    torch_dev = get_torch_device("cpu")
    assert isinstance(torch_dev, torch.device)
    assert torch_dev.type == "cpu"


def test_get_device_info() -> None:
    info = get_device_info()
    assert "platform" in info
    assert "python_version" in info
    assert "cuda_available" in info
    assert "mps_available" in info
    assert "optimal_device" in info
    assert isinstance(info["optimal_device"], str)
