"""本地 MinerU pipeline / hybrid 解析。"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.parsers.base import BaseParser, ParserError
from app.parsers.mineru_map import (
    copy_mineru_images,
    document_from_content_list,
    document_from_middle,
    find_json,
    pdf_page_sizes,
)
from app.schemas.document import Document

logger = logging.getLogger("paperlens.parser.mineru")

_GIB = 1024**3
# MinerU 官方最低显存要求：pipeline 4GB，本地 VLM / hybrid 8GB；HTTP client
# 的模型在远端，仅保留本地轻量处理所需的 2GB。
_BACKEND_MIN_GPU_GB = {
    "pipeline": 4.0,
    "http-client": 2.0,
    "vlm": 8.0,
    "hybrid": 8.0,
}


@dataclass(frozen=True)
class _GpuMemorySnapshot:
    index: int
    name: str
    free_bytes: int
    total_bytes: int
    reusable_bytes: int = 0


def _estimate_gpu_memory_gb(backend: str, configured_gb: float = 0.0) -> float:
    """按后端估算启动所需显存；显式配置优先。"""
    if configured_gb > 0:
        return configured_gb
    normalized = backend.strip().lower()
    if "http-client" in normalized:
        return _BACKEND_MIN_GPU_GB["http-client"]
    if "hybrid" in normalized:
        return _BACKEND_MIN_GPU_GB["hybrid"]
    if "vlm" in normalized:
        return _BACKEND_MIN_GPU_GB["vlm"]
    if normalized == "pipeline":
        return _BACKEND_MIN_GPU_GB["pipeline"]
    # 未知的本地后端按较重的 VLM 预算，避免低估后直接 OOM。
    return _BACKEND_MIN_GPU_GB["vlm"]


def _cuda_device_index(torch_module: object, device: str) -> int:
    if ":" in device:
        try:
            return int(device.split(":", 1)[1])
        except ValueError:
            pass
    return int(torch_module.cuda.current_device())  # type: ignore[attr-defined]


def _gpu_memory_snapshot(device: str) -> _GpuMemorySnapshot | None:
    """读取 CUDA 驱动报告的实时空闲显存，不触发 MinerU 模型加载。"""
    try:
        import torch

        index = _cuda_device_index(torch, device)
        free_bytes, total_bytes = torch.cuda.mem_get_info(index)
        # 同一进程已经保留的 PyTorch 显存可被后续解析复用；否则模型常驻后，
        # 第二篇论文会因只看驱动层 free 而被误判。
        reusable_bytes = int(torch.cuda.memory_reserved(index))
        name = str(torch.cuda.get_device_name(index))
        return _GpuMemorySnapshot(
            index=index,
            name=name,
            free_bytes=int(free_bytes),
            total_bytes=int(total_bytes),
            reusable_bytes=reusable_bytes,
        )
    except Exception:  # noqa: BLE001
        logger.warning("无法读取 CUDA 显存信息，跳过 MinerU 启动前显存检查", exc_info=True)
        return None


def _ensure_gpu_memory(backend: str, device: str, configured_gb: float = 0.0) -> None:
    required_gb = _estimate_gpu_memory_gb(backend, configured_gb)
    snapshot = _gpu_memory_snapshot(device)
    if snapshot is None:
        return

    free_gb = snapshot.free_bytes / _GIB
    total_gb = snapshot.total_bytes / _GIB
    reusable_gb = snapshot.reusable_bytes / _GIB
    usable_gb = free_gb + reusable_gb
    logger.info(
        "MinerU GPU 显存预检: backend=%s gpu=%s(%s) required=%.2fGiB "
        "free=%.2fGiB reusable=%.2fGiB total=%.2fGiB",
        backend,
        snapshot.index,
        snapshot.name,
        required_gb,
        free_gb,
        reusable_gb,
        total_gb,
    )
    if usable_gb + 1e-9 >= required_gb:
        return

    shortage_gb = required_gb - usable_gb
    raise ParserError(
        "MinerU 启动前显存检查未通过："
        f"GPU {snapshot.index}（{snapshot.name}）当前空闲 {free_gb:.2f} GiB / "
        f"总计 {total_gb:.2f} GiB，{backend} 后端预计至少需要 {required_gb:.2f} GiB，"
        f"仍缺少 {shortage_gb:.2f} GiB。模型尚未启动。请释放显存、改用 "
        "PAPERLENS_MINERU_DEVICE=cpu，或通过 PAPERLENS_MINERU_GPU_MEMORY_GB "
        "设置适合当前模型的检查阈值。"
    )


def _is_oom(exc: BaseException) -> bool:
    text = str(exc).lower()
    names = type(exc).__name__.lower()
    return (
        "out of memory" in text
        or "cuda oom" in text
        or "cuda out of memory" in text
        or "cublas" in text and "alloc" in text
        or "outofmemory" in names
    )


def _mineru_version() -> str:
    try:
        from importlib.metadata import version

        return version("mineru")
    except Exception:  # noqa: BLE001
        return "3"


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001
        return False


def _prepare_env(device: str, model_source: str) -> None:
    os.environ["MINERU_DEVICE_MODE"] = device
    if model_source:
        os.environ.setdefault("MINERU_MODEL_SOURCE", model_source)


def _run_do_parse(
    pdf_path: Path,
    mineru_dir: Path,
    *,
    backend: str,
    lang: str,
    device: str,
    model_source: str,
) -> None:
    try:
        from mineru.cli.common import do_parse
    except ImportError as e:
        raise ParserError(
            "未安装 MinerU。请执行: uv sync --extra mineru（Windows 需 Python 3.11/3.12）"
        ) from e

    _prepare_env(device, model_source)
    mineru_dir.mkdir(parents=True, exist_ok=True)
    pdf_bytes = pdf_path.read_bytes()
    kwargs = dict(
        output_dir=str(mineru_dir),
        pdf_file_names=[pdf_path.stem[:40] or "doc"],
        pdf_bytes_list=[pdf_bytes],
        p_lang_list=[lang],
        backend=backend,
        formula_enable=True,
        table_enable=True,
        f_draw_layout_bbox=False,
        f_draw_span_bbox=False,
        f_dump_md=False,
        f_dump_middle_json=True,
        f_dump_model_output=False,
        f_dump_orig_pdf=False,
        f_dump_content_list=True,
    )
    try:
        do_parse(**kwargs)
    except TypeError:
        kwargs.pop("f_dump_orig_pdf", None)
        do_parse(**kwargs)


class MinerUParser(BaseParser):
    name = "mineru"
    version = "1"

    def parse(self, pdf_path: Path, paper_id: str, output_dir: Path) -> Document:
        settings = get_settings()
        backend = (settings.mineru_backend or "pipeline").strip()
        device = (settings.mineru_device or "cuda").strip().lower()
        if device.startswith("cuda") and not _cuda_available():
            logger.warning("CUDA 不可用，MinerU 回退 CPU")
            device = "cpu"
            if backend not in {"pipeline"} and "hybrid" in backend:
                backend = "pipeline"
        elif device.startswith("cuda"):
            _ensure_gpu_memory(
                backend,
                device,
                getattr(settings, "mineru_gpu_memory_gb", 0.0),
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        mineru_dir = output_dir / "mineru"
        images_dir = output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        tried_cpu = device == "cpu"
        last_error: BaseException | None = None
        while True:
            try:
                _run_do_parse(
                    pdf_path,
                    mineru_dir,
                    backend=backend,
                    lang=settings.mineru_lang or "en",
                    device=device,
                    model_source=settings.mineru_model_source or "modelscope",
                )
                break
            except ParserError:
                raise
            except Exception as e:  # noqa: BLE001
                last_error = e
                if not tried_cpu and _is_oom(e):
                    logger.exception("MinerU GPU OOM，回退 pipeline+cpu")
                    device = "cpu"
                    backend = "pipeline"
                    tried_cpu = True
                    continue
                raise ParserError(f"MinerU 解析失败: {e}") from e

        if last_error and not mineru_dir.exists():
            raise ParserError(f"MinerU 解析失败: {last_error}") from last_error

        image_map = copy_mineru_images(mineru_dir, images_dir)
        version = _mineru_version()
        self.version = version

        middle_path = find_json(mineru_dir, "_middle.json", "layout.json")
        if middle_path is not None:
            middle = json.loads(middle_path.read_text(encoding="utf-8"))
            return document_from_middle(
                middle,
                paper_id=paper_id,
                parser=self.name,
                parser_version=version,
                image_map=image_map,
            )

        content_path = find_json(mineru_dir, "_content_list.json", "content_list.json")
        if content_path is None:
            raise ParserError("MinerU 未产出 middle.json / content_list.json")
        items = json.loads(content_path.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            items = items.get("content_list") or []
        return document_from_content_list(
            items,
            paper_id=paper_id,
            parser=self.name,
            parser_version=version,
            image_map=image_map,
            page_sizes=pdf_page_sizes(pdf_path),
        )
