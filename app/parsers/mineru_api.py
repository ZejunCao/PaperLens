"""MinerU 官方精准解析 API（mineru.net）。"""

from __future__ import annotations

import json
import time
import zipfile
from io import BytesIO
from pathlib import Path

import httpx

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

_POLL_SECONDS = 3.0
_MAX_WAIT = 30 * 60


class MinerUApiParser(BaseParser):
    name = "mineru_api"
    version = "v4"

    def parse(self, pdf_path: Path, paper_id: str, output_dir: Path) -> Document:
        settings = get_settings()
        token = (settings.mineru_api_token or "").strip()
        if not token:
            raise ParserError("未配置 PAPERLENS_MINERU_API_TOKEN，无法使用远程 MinerU API")

        base = (settings.mineru_api_base or "https://mineru.net").rstrip("/")
        model = settings.mineru_api_model or "vlm"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        output_dir.mkdir(parents=True, exist_ok=True)
        mineru_dir = output_dir / "mineru"
        images_dir = output_dir / "images"
        mineru_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)

        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            apply = client.post(
                f"{base}/api/v4/file-urls/batch",
                headers=headers,
                json={
                    "files": [{"name": pdf_path.name, "data_id": paper_id}],
                    "model_version": model,
                    "enable_formula": True,
                    "enable_table": True,
                },
            )
            apply.raise_for_status()
            body = apply.json()
            if body.get("code") != 0:
                raise ParserError(f"MinerU API 申请上传失败: {body.get('msg')}")
            batch_id = body["data"]["batch_id"]
            urls = body["data"]["file_urls"]
            if not urls:
                raise ParserError("MinerU API 未返回上传地址")

            put = client.put(urls[0], content=pdf_path.read_bytes())
            if put.status_code not in {200, 201}:
                raise ParserError(f"MinerU API 上传失败: HTTP {put.status_code}")

            zip_url = self._poll_zip(client, base, headers, batch_id)
            zres = client.get(zip_url)
            zres.raise_for_status()

        self._extract_zip(zres.content, mineru_dir)
        image_map = copy_mineru_images(mineru_dir, images_dir)

        middle_path = find_json(mineru_dir, "_middle.json", "layout.json")
        if middle_path is not None:
            middle = json.loads(middle_path.read_text(encoding="utf-8"))
            if isinstance(middle, list):
                middle = {"pdf_info": middle, "_backend": "api"}
            return document_from_middle(
                middle,
                paper_id=paper_id,
                parser=self.name,
                parser_version=self.version,
                image_map=image_map,
            )

        content_path = find_json(mineru_dir, "_content_list.json", "content_list.json")
        if content_path is None:
            raise ParserError("MinerU API Zip 中没有 layout.json / content_list.json")
        items = json.loads(content_path.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            items = items.get("content_list") or []
        return document_from_content_list(
            items,
            paper_id=paper_id,
            parser=self.name,
            parser_version=self.version,
            image_map=image_map,
            page_sizes=pdf_page_sizes(pdf_path),
        )

    def _poll_zip(
        self,
        client: httpx.Client,
        base: str,
        headers: dict[str, str],
        batch_id: str,
    ) -> str:
        deadline = time.monotonic() + _MAX_WAIT
        while time.monotonic() < deadline:
            res = client.get(f"{base}/api/v4/extract-results/batch/{batch_id}", headers=headers)
            res.raise_for_status()
            body = res.json()
            if body.get("code") != 0:
                raise ParserError(f"MinerU API 查询失败: {body.get('msg')}")
            results = body.get("data", {}).get("extract_result") or []
            if not results:
                time.sleep(_POLL_SECONDS)
                continue
            item = results[0]
            state = item.get("state")
            if state == "done":
                url = item.get("full_zip_url")
                if not url:
                    raise ParserError("MinerU API 完成但未返回 Zip")
                return url
            if state == "failed":
                raise ParserError(f"MinerU API 解析失败: {item.get('err_msg') or state}")
            time.sleep(_POLL_SECONDS)
        raise ParserError("MinerU API 解析超时")

    def _extract_zip(self, blob: bytes, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(BytesIO(blob)) as zf:
            zf.extractall(dest)
