"""Đọc tin nhóm qua Telethon (Telegram app) — ổn định hơn Telegram Web."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Union

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors.rpcerrorlist import ChannelPrivateError
from telethon.tl.custom.message import Message

from link_resolve import bag_remaining_seconds, enrich_message_text
from message_extract import extract_message_content
from settings import FEED_DECODE_WORKERS, ROOT, TELEGRAM_CHAT_IDS, TELEGRAM_SESSION_PATH

load_dotenv(ROOT / ".env")

logger = logging.getLogger(__name__)


def _load_telegram_creds() -> tuple[int, str, str]:
    import os

    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"].strip()
    phone = os.environ.get("TELEGRAM_PHONE", "").strip()
    return api_id, api_hash, phone


def _parse_chat_ids(raw: str) -> List[int]:
    out: List[int] = []
    for part in (raw or "").replace(";", ",").split(","):
        token = part.strip().lstrip("#")
        if not token:
            continue
        if token.startswith("-100"):
            out.append(int(token))
        elif token.startswith("-"):
            out.append(int("-100" + token[1:]))
        else:
            out.append(int("-100" + token))
    return out


def _sender_name(message: Message) -> str:
    try:
        sender = message.sender
        if sender is None:
            return "Unknown"
        username = getattr(sender, "username", None)
        if username:
            return f"@{username}"
        first = getattr(sender, "first_name", None) or ""
        last = getattr(sender, "last_name", None) or ""
        name = f"{first} {last}".strip()
        return name or str(getattr(sender, "id", "Unknown"))
    except Exception:
        return "Unknown"


_DECODE_POOL = None


def _decode_pool():
    global _DECODE_POOL
    if _DECODE_POOL is None:
        from concurrent.futures import ThreadPoolExecutor

        _DECODE_POOL = ThreadPoolExecutor(
            max_workers=max(1, FEED_DECODE_WORKERS), thread_name_prefix="decode"
        )
    return _DECODE_POOL


async def _emit_message(
    message: Message,
    publish: Callable[[Dict[str, Any]], Any],
    *,
    has_clients: Optional[Callable[[], bool]] = None,
) -> None:
    if has_clients is not None and not has_clients():
        return
    content = extract_message_content(message)
    text = content["text"]
    if not text and not content["urls"]:
        return

    msg_id = f"{message.chat_id}:{message.id}"
    chat_title = ""
    try:
        chat = message.chat
        chat_title = getattr(chat, "title", None) or str(message.chat_id)
    except Exception:
        chat_title = str(message.chat_id)
    msg_ts = message.date.timestamp() if message.date else None
    # Chỉ giải mã 1 link chính; hết TIME trên tin → bỏ luôn, không bắn
    remain = bag_remaining_seconds(text, message_ts=msg_ts)
    if remain is not None and remain <= 3:
        logger.info("skip msg %s — hết TIME (%.0fs)", msg_id, remain)
        return

    if has_clients is not None and not has_clients():
        return

    extra = content["urls"]
    loop = asyncio.get_running_loop()
    enriched = await loop.run_in_executor(
        _decode_pool(),
        lambda: enrich_message_text(text, message_ts=msg_ts, extra_urls=extra),
    )
    if enriched.get("skip"):
        logger.info("skip msg %s — %s", msg_id, enriched.get("skip_reason") or "skip")
        return
    links = enriched.get("links") or []
    if not any(l.get("deeplink") for l in links):
        # Chưa giải mã được → không bắn tin thô
        return

    # Hết TIME trong lúc chờ decode → bỏ
    remain_after = bag_remaining_seconds(text, message_ts=msg_ts)
    if remain_after is not None and remain_after <= 3:
        logger.info("skip msg %s sau decode — hết TIME (%.0fs)", msg_id, remain_after)
        return

    payload = {
        "id": msg_id,
        "sender": _sender_name(message),
        "chat": chat_title,
        "outgoing": bool(message.out),
        "timestamp_ms": int(message.date.timestamp() * 1000) if message.date else None,
        "text": text,
        "display_text": enriched.get("display_text") or text,
        "display_html": content["display_html"],
        "links": links,
        "bag_remain_s": remain_after,
    }
    result = publish(payload)
    if asyncio.iscoroutine(result):
        await result


StatusCallback = Callable[[Dict[str, Any]], Union[None, Any]]


async def _set_status(cb: Optional[StatusCallback], **fields: Any) -> None:
    if cb is None:
        return
    payload = {**fields, "type": "telethon_status"}
    result = cb(payload)
    if asyncio.iscoroutine(result):
        await result


async def run_telethon_feed(
    publish: Callable[[Dict[str, Any]], Any],
    *,
    stop: Optional[asyncio.Event] = None,
    set_status: Optional[StatusCallback] = None,
    has_clients: Optional[Callable[[], bool]] = None,
) -> None:
    api_id, api_hash, _phone = _load_telegram_creds()
    chat_ids = _parse_chat_ids(TELEGRAM_CHAT_IDS)
    if not chat_ids:
        raise RuntimeError("TELEGRAM_CHAT_IDS trống")

    if not TELEGRAM_SESSION_PATH.is_file():
        await _set_status(
            set_status,
            phase="need_login",
            message="Chưa có file session. Chạy: python login_telethon.py",
        )
        raise RuntimeError(
            f"Thiếu session {TELEGRAM_SESSION_PATH}. Chạy login_telethon.py (OTP Telegram)."
        )

    await _set_status(set_status, phase="connecting", message="Đang kết nối Telethon…")

    client = TelegramClient(
        str(TELEGRAM_SESSION_PATH),
        api_id,
        api_hash,
        connection_retries=None,
        retry_delay=5,
        auto_reconnect=True,
    )

    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        await _set_status(
            set_status,
            phase="need_login",
            message="Session chưa login / hết hạn. Chạy login_telethon.py",
        )
        raise RuntimeError(
            "Telethon session chưa login. Chạy: cd thaihung-v3 && python login_telethon.py"
        )

    me = await client.get_me()
    await _set_status(
        set_status,
        phase="connecting",
        username=getattr(me, "username", None),
        message=f"Đã login @{me.username or me.id}",
    )

    entities = []
    for cid in chat_ids:
        try:
            entity = await client.get_entity(cid)
        except ChannelPrivateError:
            logger.warning(
                "Bỏ qua chat_id=%s: private / không có quyền (join lại nhóm hoặc đổi session)",
                cid,
            )
            continue
        except Exception:
            logger.exception("Bỏ qua chat_id=%s: không resolve được entity", cid)
            continue
        entities.append(entity)
        logger.info("Listening chat_id=%s title=%s", cid, getattr(entity, "title", cid))

    if not entities:
        await client.disconnect()
        await _set_status(
            set_status,
            phase="no_chats",
            username=getattr(me, "username", None),
            message="Đã login Telethon nhưng acc chưa vào được nhóm #‑3431776950 (moon_2).",
        )
        raise RuntimeError(
            "Không nhóm nào trong TELEGRAM_CHAT_IDS truy cập được. "
            "Join nhóm bằng acc Telethon hoặc kiểm tra TELEGRAM_CHAT_IDS."
        )

    titles = [getattr(e, "title", str(e.id)) for e in entities]
    await _set_status(
        set_status,
        phase="listening",
        username=getattr(me, "username", None),
        chats=titles,
        message=f"Telethon · đang nghe: {', '.join(titles)}",
    )

    @client.on(events.NewMessage(chats=entities))
    async def _handler(event: events.NewMessage.Event) -> None:
        try:
            await _emit_message(event.message, publish, has_clients=has_clients)
        except Exception:
            logger.exception("Failed to emit message chat=%s", event.chat_id)

    logger.info("Telethon feed ready (%s chats)", len(entities))

    try:
        if stop is None:
            await client.run_until_disconnected()
        else:
            await stop.wait()
    finally:
        await client.disconnect()
