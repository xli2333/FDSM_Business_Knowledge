from __future__ import annotations

import itertools
import json
import subprocess
from pathlib import Path
from typing import Any

from backend.config import GEMINI_API_KEYS, PRIMARY_GEMINI_KEY


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_SCRIPT_PATH = PROJECT_ROOT / "backend" / "scripts" / "wechat_fudan_bridge.mjs"
_GEMINI_KEY_COUNTER = itertools.count()


class FudanWechatRenderError(RuntimeError):
    pass


def _available_gemini_api_keys() -> tuple[str, ...]:
    keys: list[str] = []
    for raw_key in (PRIMARY_GEMINI_KEY, *GEMINI_API_KEYS):
        cleaned = str(raw_key or "").strip()
        if cleaned and cleaned not in keys:
            keys.append(cleaned)
    return tuple(keys)


def _next_gemini_api_key() -> str:
    keys = _available_gemini_api_keys()
    if not keys:
        return ""
    return keys[next(_GEMINI_KEY_COUNTER) % len(keys)]


def is_fudan_wechat_preview_html(value: str | None) -> bool:
    html = str(value or "")
    return "wechat-preview-shell" in html and "data-wechat-decoration" in html


def _clip_message(value: str, limit: int = 600) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def render_fudan_wechat_batch(
    items: list[dict[str, Any]],
    *,
    timeout_seconds: float = 120.0,
) -> list[dict[str, Any]]:
    if not items:
        return []

    payload = {"items": items}
    try:
        completed = subprocess.run(
            ["node", str(BRIDGE_SCRIPT_PATH)],
            cwd=PROJECT_ROOT,
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FudanWechatRenderError("Fudan WeChat renderer timed out.") from exc
    except FileNotFoundError as exc:
        raise FudanWechatRenderError("Node.js is required for the Fudan WeChat renderer.") from exc

    if completed.returncode != 0:
        stderr = _clip_message(completed.stderr)
        stdout = _clip_message(completed.stdout)
        details = stderr or stdout or f"exit code {completed.returncode}"
        raise FudanWechatRenderError(f"Fudan WeChat renderer failed: {details}")

    try:
        response = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise FudanWechatRenderError("Fudan WeChat renderer returned invalid JSON.") from exc

    results = response.get("results")
    if not isinstance(results, list):
        raise FudanWechatRenderError("Fudan WeChat renderer response missing results.")
    return results


def render_fudan_wechat(item: dict[str, Any], *, timeout_seconds: float = 60.0) -> dict[str, Any]:
    results = render_fudan_wechat_batch([item], timeout_seconds=timeout_seconds)
    if not results:
        raise FudanWechatRenderError("Fudan WeChat renderer returned no result.")
    return results[0]


def build_fudan_render_item(
    *,
    title: str,
    content_markdown: str,
    summary: str = "",
    source_url: str | None = None,
    author: str = "",
    editor: str = "",
    credit_lines: list[str] | None = None,
    opening_highlight_mode: str = "smart_lead",
    omit_credits: bool = True,
    api_key: str | None = None,
) -> dict[str, Any]:
    return {
        "title": str(title or "").strip(),
        "content_markdown": str(content_markdown or "").strip(),
        "summary": str(summary or "").strip(),
        "source_url": str(source_url or "").strip(),
        "author": str(author or "").strip(),
        "editor": str(editor or "").strip(),
        "credit_lines": [str(item or "").strip() for item in (credit_lines or []) if str(item or "").strip()],
        "opening_highlight_mode": str(opening_highlight_mode or "smart_lead").strip() or "smart_lead",
        "omit_credits": bool(omit_credits),
        "api_key": str(api_key or "").strip() or _next_gemini_api_key(),
    }


def render_fudan_preview_html(item: dict[str, Any], *, timeout_seconds: float = 60.0) -> str:
    rendered = render_fudan_wechat(item, timeout_seconds=timeout_seconds)
    return str(rendered.get("previewHtml") or rendered.get("contentHtml") or "").strip()
