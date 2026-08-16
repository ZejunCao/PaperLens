from __future__ import annotations

import json
from pathlib import Path

from app.config import get_settings
from app.schemas.llm import LlmConfigOut, LlmConfigUpdate

_DEFAULT_BASE = "https://api.openai.com/v1"


def llm_config_path() -> Path:
    return get_settings().data_dir / "llm_config.json"


def _mask_key(key: str) -> str:
    raw = (key or "").strip()
    if not raw:
        return ""
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:3]}***{raw[-4:]}"


def load_llm_config_raw() -> dict:
    path = llm_config_path()
    if not path.exists():
        return {"base_url": _DEFAULT_BASE, "api_key": "", "model": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"base_url": _DEFAULT_BASE, "api_key": "", "model": ""}
    if not isinstance(data, dict):
        return {"base_url": _DEFAULT_BASE, "api_key": "", "model": ""}
    return {
        "base_url": str(data.get("base_url") or _DEFAULT_BASE).rstrip("/"),
        "api_key": str(data.get("api_key") or ""),
        "model": str(data.get("model") or ""),
    }


def is_llm_configured(raw: dict | None = None) -> bool:
    data = raw if raw is not None else load_llm_config_raw()
    base = (data.get("base_url") or "").strip()
    model = (data.get("model") or "").strip()
    key = (data.get("api_key") or "").strip()
    if not base or not model:
        return False
    local = "127.0.0.1" in base or "localhost" in base
    return bool(key) or local


def save_llm_config(update: LlmConfigUpdate) -> LlmConfigOut:
    current = load_llm_config_raw()
    base = (update.base_url or _DEFAULT_BASE).strip().rstrip("/") or _DEFAULT_BASE
    model = (update.model or "").strip()
    if update.api_key is None:
        key = current.get("api_key") or ""
    else:
        incoming = update.api_key.strip()
        key = (current.get("api_key") or "") if incoming == "" else incoming
    payload = {"base_url": base, "api_key": key, "model": model}
    path = llm_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return to_llm_out(payload)


def to_llm_out(raw: dict | None = None) -> LlmConfigOut:
    data = raw if raw is not None else load_llm_config_raw()
    key = str(data.get("api_key") or "")
    return LlmConfigOut(
        base_url=str(data.get("base_url") or _DEFAULT_BASE),
        api_key_set=bool(key.strip()),
        api_key_masked=_mask_key(key),
        model=str(data.get("model") or ""),
        configured=is_llm_configured(data),
    )
