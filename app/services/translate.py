from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
import httpx
from fastapi import HTTPException, status

from app.schemas.document import ContentBlock, Document
from app.schemas.llm import PageTranslation, TranslationFile, TranslationOut
from app.services.documents import load_document, paper_dir
from app.services.llm_settings import is_llm_configured, load_llm_config_raw

logger = logging.getLogger("paperlens.translate")

PROMPT_VERSION = 1
_SKIP_TYPES = {"formula", "figure", "table", "header", "footer"}
_HAS_LETTER = re.compile(r"[A-Za-z\u4e00-\u9fff]")
_HASH_LIKE = re.compile(r"^[0-9a-f]{16,}$", re.I)


def translation_path(paper_id: str, lang: str = "zh-CN") -> Path:
    return paper_dir(paper_id) / "translations" / f"{lang}.json"


def load_translation_file(paper_id: str, lang: str = "zh-CN") -> TranslationFile:
    path = translation_path(paper_id, lang)
    if not path.exists():
        return TranslationFile(paper_id=paper_id, target_lang=lang, prompt_version=PROMPT_VERSION)
    try:
        return TranslationFile.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return TranslationFile(paper_id=paper_id, target_lang=lang, prompt_version=PROMPT_VERSION)


def save_translation_file(data: TranslationFile) -> None:
    path = translation_path(data.paper_id, data.target_lang)
    path.parent.mkdir(parents=True, exist_ok=True)
    data.updated_at = datetime.now(timezone.utc).isoformat()
    path.write_text(data.model_dump_json(indent=2), encoding="utf-8")


def _should_skip_text(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if _HASH_LIKE.match(t):
        return True
    if not _HAS_LETTER.search(t):
        return True
    if t.count("\\") >= 3 and len(t) < 80:
        return True
    return False


def collect_page_sentences(document: Document, page_no: int) -> list[tuple[str, str]]:
    page = next((p for p in document.pages if p.page == page_no), None)
    if page is None:
        return []
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for block in page.blocks:
        if block.type in _SKIP_TYPES:
            continue
        for sent in block.sentences or []:
            if sent.id in seen:
                continue
            if _should_skip_text(sent.text):
                continue
            seen.add(sent.id)
            out.append((sent.id, sent.text))
    return out


def get_translations(paper_id: str, lang: str = "zh-CN") -> TranslationOut:
    raw = load_llm_config_raw()
    file = load_translation_file(paper_id, lang)
    return TranslationOut(
        paper_id=paper_id,
        target_lang=lang,
        configured=is_llm_configured(raw),
        pages=file.pages,
    )


def _parse_model_json(content: str) -> dict[str, str]:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if isinstance(data, dict) and isinstance(data.get("sentences"), list):
        rows = data["sentences"]
    elif isinstance(data, list):
        rows = data
    elif isinstance(data, dict) and all(isinstance(v, str) for v in data.values()):
        return {str(k): str(v) for k, v in data.items()}
    else:
        raise ValueError("模型返回 JSON 结构无法识别")
    mapped: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("id") or "").strip()
        zh = str(row.get("zh") or row.get("text") or "").strip()
        if sid:
            mapped[sid] = zh
    return mapped


def _chat_translate(items: list[tuple[str, str]], cfg: dict) -> dict[str, str]:
    base = str(cfg.get("base_url") or "").rstrip("/")
    model = str(cfg.get("model") or "").strip()
    key = str(cfg.get("api_key") or "").strip()
    url = f"{base}/chat/completions"
    payload_items = [{"id": i, "text": t} for i, t in items]
    body = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a professional academic translator. Translate English paper sentences "
                    "into Simplified Chinese. Keep technical terms, paper titles, and model names "
                    "consistent. Do not translate LaTeX, citations like [12], or equation numbers. "
                    "Return JSON: {\"sentences\": [{\"id\": \"...\", \"zh\": \"...\"}, ...]} "
                    "with the same ids and count as the input, in the same order."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"sentences": payload_items}, ensure_ascii=False),
            },
        ],
    }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, headers=headers, json=body)
            if resp.status_code == 400:
                dropped = False
                for extra in ("response_format", "thinking"):
                    if extra in body:
                        body.pop(extra)
                        dropped = True
                if dropped:
                    resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500] if e.response is not None else str(e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"翻译接口失败: {detail}") from e
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"无法连接翻译接口: {e}") from e

    try:
        content = data["choices"][0]["message"]["content"]
        mapped = _parse_model_json(content)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"无法解析模型输出: {e}") from e

    missing = [sid for sid, _ in items if sid not in mapped or not mapped[sid].strip()]
    if missing:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"译文与原文句子未对齐（缺 {len(missing)} 条）",
        )
    return {sid: mapped[sid].strip() for sid, _ in items}


def translate_page(paper_id: str, page_no: int, lang: str = "zh-CN") -> TranslationOut:
    document = load_document(paper_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文档尚未解析完成")
    if page_no < 1 or page_no > document.page_count:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "页码无效")

    cfg = load_llm_config_raw()
    file = load_translation_file(paper_id, lang)
    key = str(page_no)
    existing = file.pages.get(key)
    if existing and existing.status == "ready" and existing.sentences:
        return get_translations(paper_id, lang)

    if not is_llm_configured(cfg):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "尚未配置模型（设置页填写 Base URL 与 Model）")

    items = collect_page_sentences(document, page_no)
    if not items:
        file.pages[key] = PageTranslation(status="ready", error=None, sentences={})
        file.provider = "openai_compatible"
        file.model = str(cfg.get("model") or "")
        file.prompt_version = PROMPT_VERSION
        save_translation_file(file)
        return get_translations(paper_id, lang)

    try:
        mapped = _chat_translate(items, cfg)
        file.pages[key] = PageTranslation(status="ready", error=None, sentences=mapped)
    except HTTPException as e:
        file.pages[key] = PageTranslation(status="failed", error=str(e.detail), sentences={})
        file.provider = "openai_compatible"
        file.model = str(cfg.get("model") or "")
        save_translation_file(file)
        raise

    file.provider = "openai_compatible"
    file.model = str(cfg.get("model") or "")
    file.prompt_version = PROMPT_VERSION
    save_translation_file(file)
    return get_translations(paper_id, lang)
