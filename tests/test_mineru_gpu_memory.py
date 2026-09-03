from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.parsers.base import ParserError
from app.parsers import mineru_parser


def _snapshot(*, free_gb: float, total_gb: float = 24.0, reusable_gb: float = 0.0):
    gib = 1024**3
    return mineru_parser._GpuMemorySnapshot(
        index=0,
        name="Test GPU",
        free_bytes=int(free_gb * gib),
        total_bytes=int(total_gb * gib),
        reusable_bytes=int(reusable_gb * gib),
    )


@pytest.mark.parametrize(
    ("backend", "expected_gb"),
    [
        ("pipeline", 4.0),
        ("vlm-engine", 8.0),
        ("hybrid-engine", 8.0),
        ("hybrid-http-client", 2.0),
        ("unknown-local-backend", 8.0),
    ],
)
def test_estimate_gpu_memory_by_backend(backend: str, expected_gb: float):
    assert mineru_parser._estimate_gpu_memory_gb(backend) == expected_gb


def test_configured_gpu_memory_overrides_backend_estimate():
    assert mineru_parser._estimate_gpu_memory_gb("pipeline", 6.5) == 6.5


def test_gpu_memory_preflight_reports_shortage(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        mineru_parser,
        "_gpu_memory_snapshot",
        lambda _device: _snapshot(free_gb=3.0),
    )

    with pytest.raises(ParserError, match=r"当前空闲 3\.00 GiB.*至少需要 4\.00 GiB.*模型尚未启动"):
        mineru_parser._ensure_gpu_memory("pipeline", "cuda")


def test_gpu_memory_preflight_counts_reusable_process_memory(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        mineru_parser,
        "_gpu_memory_snapshot",
        lambda _device: _snapshot(free_gb=3.0, reusable_gb=1.0),
    )

    mineru_parser._ensure_gpu_memory("pipeline", "cuda")


def test_parser_does_not_start_mineru_when_gpu_memory_is_insufficient(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    settings = SimpleNamespace(
        mineru_backend="pipeline",
        mineru_device="cuda",
        mineru_lang="en",
        mineru_model_source="modelscope",
        mineru_gpu_memory_gb=0.0,
    )
    started = False

    def fake_run(*_args, **_kwargs):
        nonlocal started
        started = True

    monkeypatch.setattr(mineru_parser, "get_settings", lambda: settings)
    monkeypatch.setattr(mineru_parser, "_cuda_available", lambda: True)
    monkeypatch.setattr(
        mineru_parser,
        "_gpu_memory_snapshot",
        lambda _device: _snapshot(free_gb=2.0),
    )
    monkeypatch.setattr(mineru_parser, "_run_do_parse", fake_run)

    with pytest.raises(ParserError, match="模型尚未启动"):
        mineru_parser.MinerUParser().parse(
            tmp_path / "paper.pdf",
            "paper-id",
            tmp_path / "output",
        )

    assert started is False
