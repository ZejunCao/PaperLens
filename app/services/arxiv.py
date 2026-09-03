"""arXiv URL / ID parsing and PDF download helpers."""

from __future__ import annotations

import re
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

import httpx
from fastapi import HTTPException, status

# 2301.12345 / 2301.12345v2 / hep-th/9901001 / hep-th/9901001v1
ARXIV_ID_RE = re.compile(
    r"(?P<id>(?:\d{4}\.\d{4,5}(?:v\d+)?)|(?:[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?))",
    re.IGNORECASE,
)
ARXIV_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:export\.)?arxiv\.org/(?:abs|pdf|html|src)/"
    r"(?P<id>(?:\d{4}\.\d{4,5}(?:v\d+)?)|(?:[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?))"
    r"(?:\.pdf)?",
    re.IGNORECASE,
)

logger = logging.getLogger("paperlens.arxiv")
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


def normalize_arxiv_id(raw: str) -> str:
    """从链接或裸 ID 中提取规范 arXiv ID；失败则抛 400。"""
    text = (raw or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入 arXiv 链接或 ID")

    m = ARXIV_URL_RE.search(text)
    if m:
        return m.group("id")

    # 允许裸 ID，或用户粘贴了带空白的短串
    bare = text.removeprefix("arxiv:").removeprefix("arXiv:").strip()
    m2 = ARXIV_ID_RE.fullmatch(bare)
    if m2:
        return m2.group("id")

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="无法识别 arXiv 链接或 ID（示例：https://arxiv.org/abs/2301.07041 或 2301.07041）",
    )


def arxiv_pdf_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


def fetch_arxiv_metadata(arxiv_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
    """Fetch authoritative metadata from the public arXiv Atom endpoint.

    Metadata failure is non-fatal: importing the PDF remains useful offline.
    """
    try:
        response = httpx.get(
            "https://export.arxiv.org/api/query",
            params={"id_list": arxiv_id},
            headers={"User-Agent": "PaperLens/0.1 (arxiv-import)"},
            timeout=timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        entry = root.find(f"{ATOM}entry")
        if entry is None:
            return {}

        def text(tag: str) -> str | None:
            node = entry.find(tag)
            value = re.sub(r"\s+", " ", node.text or "").strip() if node is not None else ""
            return value or None

        published_text = text(f"{ATOM}published")
        published_at = datetime.fromisoformat(published_text.replace("Z", "+00:00")) if published_text else None
        authors = [
            re.sub(r"\s+", " ", node.text or "").strip()
            for node in entry.findall(f"{ATOM}author/{ATOM}name")
            if (node.text or "").strip()
        ]
        institutions = list(
            dict.fromkeys(
                re.sub(r"\s+", " ", node.text or "").strip()
                for node in entry.findall(f"{ATOM}author/{ARXIV}affiliation")
                if (node.text or "").strip()
            )
        )
        categories = [node.attrib.get("term", "") for node in entry.findall(f"{ATOM}category")]
        return {
            "title": text(f"{ATOM}title"),
            "authors": authors,
            "institutions": institutions,
            "abstract": text(f"{ATOM}summary"),
            "publication": text(f"{ARXIV}journal_ref"),
            "published_at": published_at,
            "doi": text(f"{ARXIV}doi"),
            "arxiv_id": arxiv_id,
            "source_url": f"https://arxiv.org/abs/{arxiv_id}",
            "keywords": [value for value in categories if value],
            "metadata_source": "arxiv",
        }
    except (httpx.HTTPError, ET.ParseError, ValueError) as error:
        logger.warning("arXiv metadata unavailable id=%s: %s", arxiv_id, error)
        return {
            "arxiv_id": arxiv_id,
            "source_url": f"https://arxiv.org/abs/{arxiv_id}",
            "metadata_source": "arxiv-id",
        }


def download_arxiv_pdf(arxiv_id: str, *, max_bytes: int, timeout: float = 120.0) -> bytes:
    """本地下载 arXiv PDF；校验大小与 %PDF 头。"""
    url = arxiv_pdf_url(arxiv_id)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            with client.stream("GET", url, headers={"User-Agent": "PaperLens/0.1 (arxiv-import)"}) as resp:
                if resp.status_code == 404:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"未找到 arXiv 论文：{arxiv_id}",
                    )
                if resp.status_code >= 400:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"下载 arXiv PDF 失败（HTTP {resp.status_code}）",
                    )

                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"文件过大（上限 {max_bytes} 字节）",
                        )
                    chunks.append(chunk)
                data = b"".join(chunks)
    except HTTPException:
        raise
    except httpx.TimeoutException as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="下载 arXiv PDF 超时，请稍后重试",
        ) from e
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"下载 arXiv PDF 网络错误：{e}",
        ) from e

    if not data:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="下载到的文件为空")
    if not data.startswith(b"%PDF"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="下载结果不是有效 PDF（可能被拦截或链接无效）",
        )
    return data
