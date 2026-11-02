"""Giải mã link trong tin: /i/ offline; /l/ + thanhtai /r/ qua Playwright profile Mac."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent

import os

from settings import (
    DEEPLINK_API_BASE_URL,
    FEED_BROWSER_FALLBACK,
    FEED_DECODE_MAX_AGE_SECONDS,
    FEED_HTTP_DECODE,
    MAC_DECODE_URL,
)

os.environ.setdefault("DEEPLINK_API_BASE_URL", DEEPLINK_API_BASE_URL)

logger = logging.getLogger(__name__)

DEEPLINK_PREFIX = "snssdk1180://live?room_id="
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
ROOM_ID_PATTERN = re.compile(r"room_id=(\d{15,22})(?:\D|$)")
BASE62_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE62_OFFSET = 0xE6875


def extract_room_id(deeplink: str) -> str:
    match = ROOM_ID_PATTERN.search(deeplink or "")
    return match.group(1) if match else ""


def _ok_deeplink(candidate: str) -> str:
    rid = extract_room_id(candidate or "")
    if rid:
        return f"{DEEPLINK_PREFIX}{rid}"
    return ""


def _junb_i_param(url: str) -> str | None:
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if "junb.io.vn" not in host or "/i/" not in path:
        return None
    match = re.search(r"[?&]([A-Za-z0-9]+)=?(?:$|&|#)", url)
    return match.group(1) if match else None


def _decode_junb_i(param: str) -> str:
    if len(param) < 10 or not re.search(r"[A-Z]", param):
        return ""
    w = param[::-1]
    y = 0
    for ch in w:
        if ch not in BASE62_CHARS:
            return ""
        y = y * 62 + BASE62_CHARS.index(ch)
    y -= BASE62_OFFSET
    decoded = str(y)[1:][::-1]
    if not decoded:
        return ""
    t, rest = decoded[0], decoded[1:]
    trim = int(t) if t.isdigit() else 0
    room_id = rest[: max(0, len(rest) - trim)]
    return _ok_deeplink(f"{DEEPLINK_PREFIX}{room_id}")


def _decode_via_mac(url: str) -> str:
    import json
    import urllib.parse
    import urllib.request

    endpoint = f"{MAC_DECODE_URL}/decode?url={urllib.parse.quote(url, safe='')}"
    try:
        with urllib.request.urlopen(endpoint, timeout=18) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return ""
    return str(payload.get("deeplink") or "")


def _needs_profile_browser(url: str) -> bool:
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if "thanhtai.io" in host and ("/r/" in path or "countdow" in path):
        return True
    if "junb.io.vn" in host and ("/l/" in path or "/s/" in path):
        return True
    return False


def _decode_thanhtai_countdown(url: str) -> str:
    """thanhtai TextUrl countdow?data=<base64(room_id)> — offline, không cần device."""
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if "thanhtai.io" not in host:
        return ""
    if "countdow" not in path and "countdown" not in path:
        return ""
    qs = parse_qs(parsed.query)
    raw = (qs.get("data") or [""])[0].strip()
    if not raw:
        return ""
    import base64

    pad = "=" * ((4 - len(raw) % 4) % 4)
    try:
        room = base64.b64decode(raw + pad).decode("ascii", "ignore").strip()
    except Exception:
        return ""
    if re.fullmatch(r"\d{15,22}", room):
        return f"{DEEPLINK_PREFIX}{room}"
    return ""


def resolve_one_url(url: str, context: str = "") -> str:
    return _resolve(url)[0]


def _resolve(url: str, deadline: float | None = None) -> tuple[str, str]:
    """(kết quả, lý do lỗi) — kết quả là deeplink hoặc URL gốc nếu không giải mã được."""
    clean = (url or "").strip()
    if not clean:
        return clean, ""

    offline = _decode_thanhtai_countdown(clean)
    if offline:
        return offline, ""

    param = _junb_i_param(clean)
    if param:
        decoded = _decode_junb_i(param)
        if decoded:
            return decoded, ""

    if not _needs_profile_browser(clean):
        return clean, "không hỗ trợ"

    reason = ""
    if FEED_HTTP_DECODE:
        import http_decode

        if http_decode.supports(clean):
            try:
                return http_decode.decode(clean, deadline=deadline), ""
            except http_decode.JunbSkipped as exc:
                return clean, str(exc)
            except http_decode.DecodeDenied as exc:
                logger.warning("decode denied %s: %s", clean[:70], exc)
                return clean, f"device bị từ chối ({exc})"
            except Exception as exc:
                logger.warning("http decode fail %s: %s", clean[:70], exc)
                reason = str(exc)
                if not FEED_BROWSER_FALLBACK:
                    return clean, reason
    if MAC_DECODE_URL:
        ok = _ok_deeplink(_decode_via_mac(clean))
        return (ok, "") if ok else (clean, reason or "Mac decode lỗi")
    from deeplink_browser import try_resolve_deeplink_via_browser

    ok = _ok_deeplink(try_resolve_deeplink_via_browser(clean) or "")
    return (ok, "") if ok else (clean, reason or "browser không bắt được snssdk")


# "TIME : 01:29s - 21:14:32" — đếm ngược + giờ hết hạn link (giờ VN)
_BAG_TIME_RE = re.compile(
    r"TIME\s*:\s*(\d{1,2}):(\d{2})\s*s(?:\s*-\s*(\d{1,2}):(\d{2}):(\d{2}))?",
    re.IGNORECASE,
)
_LINK_TZ = timezone(timedelta(hours=7))
# Còn dưới ngưỡng này (giây) thì coi như hết hạn — không kịp click
_MIN_BAG_REMAIN_S = float(os.environ.get("FEED_MIN_BAG_REMAIN_S", "3"))


def link_expires_at(text: str, *, message_ts: float | None) -> float | None:
    """Epoch hết hạn của link trong tin. None = tin không có TIME."""
    match = _BAG_TIME_RE.search(text or "")
    if not match:
        return None
    sent = message_ts if message_ts is not None else time.time()
    if match.group(3):
        sent_local = datetime.fromtimestamp(sent, _LINK_TZ)
        end = sent_local.replace(
            hour=int(match.group(3)),
            minute=int(match.group(4)),
            second=int(match.group(5)),
            microsecond=0,
        )
        if end < sent_local - timedelta(hours=12):
            end += timedelta(days=1)
        elif end > sent_local + timedelta(hours=12):
            end -= timedelta(days=1)
        return end.timestamp()
    return sent + int(match.group(1)) * 60 + int(match.group(2))


def bag_remaining_seconds(text: str, *, message_ts: float | None, now: float | None = None) -> float | None:
    """Số giây link còn sống tính đến `now`. None = không đọc được TIME."""
    expires = link_expires_at(text, message_ts=message_ts)
    if expires is None:
        return None
    return expires - (time.time() if now is None else now)


def _should_decode_links(*, message_ts: float | None, text: str = "") -> tuple[bool, str]:
    remain = bag_remaining_seconds(text, message_ts=message_ts)
    if remain is not None:
        if remain <= _MIN_BAG_REMAIN_S:
            return False, f"link hết hạn ({remain:.0f}s)"
        return True, ""
    # Không có TIME trên tin → fallback tuổi tin
    if message_ts is None:
        return True, ""
    if (time.time() - message_ts) > FEED_DECODE_MAX_AGE_SECONDS:
        return False, "tin cũ"
    return True, ""


def _primary_decode_urls(text: str, extra_urls: List[str] | None) -> List[str]:
    """Chỉ lấy 1 link chính /l/ hoặc /r/ (hoặc /i/) — không giải mã hết mọi URL."""
    seen: set[str] = set()
    ordered: List[str] = []
    for match in URL_PATTERN.finditer(text or ""):
        ordered.append(match.group(0))
    for url in extra_urls or []:
        ordered.append(url)

    primaries: List[str] = []
    fallbacks: List[str] = []
    for url in ordered:
        if url in seen:
            continue
        seen.add(url)
        path = (urlparse(url).path or "").lower()
        host = (urlparse(url).netloc or "").lower()
        if ("junb.io.vn" in host and any(p in path for p in ("/l/", "/s/", "/i/"))) or (
            "thanhtai.io" in host and "/r/" in path
        ):
            primaries.append(url)
        elif "thanhtai.io" in host and "countdow" in path:
            fallbacks.append(url)
    # Một tin chỉ giải mã 1 link chính
    if primaries:
        return primaries[:1]
    return fallbacks[:1]


def enrich_message_text(
    text: str,
    *,
    message_ts: float | None = None,
    extra_urls: List[str] | None = None,
) -> Dict[str, Any]:
    links: List[Dict[str, str]] = []
    decode, skip_reason = _should_decode_links(message_ts=message_ts, text=text)
    if not decode:
        return {
            "text": text,
            "display_text": text,
            "links": [],
            "skip": True,
            "skip_reason": skip_reason,
        }

    candidates = _primary_decode_urls(text, extra_urls)
    for original in candidates:
        # Kiểm tra lại TIME ngay trước khi gọi API (tránh hàng đợi junb làm hết giờ)
        still_ok, why = _should_decode_links(message_ts=message_ts, text=text)
        if not still_ok:
            return {
                "text": text,
                "display_text": text,
                "links": [],
                "skip": True,
                "skip_reason": why,
            }
        resolved, reason = _resolve(original, deadline=link_expires_at(text, message_ts=message_ts))
        deeplink = _ok_deeplink(resolved)
        links.append(
            {
                "original": original,
                "deeplink": deeplink,
                "room_id": extract_room_id(resolved),
                "skip_decode": False,
                "error": "" if deeplink else (reason or "không giải mã được"),
            }
        )
        if deeplink:
            break

    return {
        "text": text,
        "display_text": text,
        "links": links,
        "skip": False,
        "skip_reason": "",
    }
