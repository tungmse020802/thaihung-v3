"""Trích text + URL thật từ Telethon (entities dùng offset UTF-16)."""

from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import urlparse

from telethon.extensions import html as tg_html
from telethon.tl.custom.message import Message
from telethon.tl.types import (
    KeyboardButtonUrl,
    MessageEntityTextUrl,
    MessageEntityUrl,
    ReplyInlineMarkup,
)


def _utf16_slice(text: str, offset: int, length: int) -> str:
    raw = text.encode("utf-16-le")
    start = offset * 2
    end = (offset + length) * 2
    if start < 0 or end > len(raw) or start > end:
        return ""
    return raw[start:end].decode("utf-16-le", "replace")


def _interesting(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    path = (urlparse(url).path or "").lower()
    if "junb.io.vn" in host:
        return any(k in path for k in ("/l/", "/s/", "/i/", "countdown", "box-countdown", "/bag"))
    if "thanhtai.io" in host:
        return any(k in path for k in ("/r/", "countdow", "countdown"))
    return False


def extract_message_content(message: Message) -> Dict[str, Any]:
    raw_text = message.message or ""
    text = raw_text.strip()
    try:
        display_html = tg_html.unparse(raw_text, message.entities or []).strip()
    except Exception:
        display_html = ""
    attachments: List[Dict[str, str]] = []
    urls: List[str] = []
    seen: set[str] = set()

    def add_url(url: str, label: str = "") -> None:
        clean = (url or "").strip()
        if not clean or clean in seen:
            return
        seen.add(clean)
        urls.append(clean)
        if _interesting(clean):
            attachments.append({"label": (label or "").strip() or "link", "url": clean})

    for ent in message.entities or []:
        if isinstance(ent, MessageEntityTextUrl):
            label = _utf16_slice(raw_text, ent.offset, ent.length)
            add_url(ent.url, label)
        elif isinstance(ent, MessageEntityUrl):
            add_url(_utf16_slice(raw_text, ent.offset, ent.length))

    markup = message.reply_markup
    if isinstance(markup, ReplyInlineMarkup):
        for row in markup.rows or []:
            for btn in row.buttons or []:
                if isinstance(btn, KeyboardButtonUrl):
                    add_url(btn.url, getattr(btn, "text", "") or "button")
                elif getattr(btn, "url", None):
                    add_url(btn.url, getattr(btn, "text", "") or "button")

    # URL trần trong text (regex nhẹ — đủ cho junb/thanhtai)
    import re

    for match in re.finditer(r"https?://[^\s<>\"']+", text, re.I):
        add_url(match.group(0))

    return {"text": text, "display_html": display_html, "urls": urls, "attachments": attachments}
