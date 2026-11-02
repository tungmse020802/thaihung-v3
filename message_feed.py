"""Đọc tin Telegram Web (Playwright profile) và đẩy qua asyncio loop."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time
from typing import Any, Callable, Dict, Set

from playwright.sync_api import Page, sync_playwright

from browser import launch_context
from settings import (
    FEED_HEADLESS,
    FEED_MESSAGE_LIMIT,
    FEED_POLL_SECONDS,
    FEED_SKIP_EXISTING_ON_START,
    TELEGRAM_CHAT_URL,
)
from link_resolve import enrich_message_text
from telegram_js import MESSAGE_EXTRACTOR_JS, SCROLL_TO_LATEST_JS

logger = logging.getLogger(__name__)


def _message_key(item: dict) -> str:
    raw = str(item.get("message_key") or "").strip()
    if raw:
        return raw
    blob = "|".join(
        [
            str(item.get("sender_name") or ""),
            str(item.get("timestamp_ms") or ""),
            str(item.get("text") or ""),
        ]
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _poll_once(page: Page) -> list[dict]:
    try:
        page.evaluate(SCROLL_TO_LATEST_JS)
    except Exception:
        pass
    raw = page.evaluate(MESSAGE_EXTRACTOR_JS, FEED_MESSAGE_LIMIT)
    return list(raw or [])


def run_telegram_feed_poller(
    *,
    loop: asyncio.AbstractEventLoop,
    publish: Callable[[Dict[str, Any]], None],
    stop_event: threading.Event,
) -> None:
    seen: Set[str] = set()
    bootstrapped = False

    with sync_playwright() as playwright:
        context = launch_context(playwright, headless=FEED_HEADLESS, inject_device=True)
        page = context.pages[0] if context.pages else context.new_page()
        logger.info("Opening chat %s", TELEGRAM_CHAT_URL)
        page.goto(TELEGRAM_CHAT_URL, wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_timeout(4000)

        while not stop_event.is_set():
            try:
                items = _poll_once(page)
                if not bootstrapped and FEED_SKIP_EXISTING_ON_START:
                    for item in items:
                        seen.add(_message_key(item))
                    bootstrapped = True
                    logger.info("Bootstrap: đánh dấu %s tin cũ, chỉ push tin mới", len(seen))
                else:
                    bootstrapped = True
                    for item in items:
                        key = _message_key(item)
                        if key in seen:
                            continue
                        seen.add(key)
                        enriched = enrich_message_text(str(item.get("text") or ""))
                        payload = {
                            "id": key,
                            "sender": str(item.get("sender_name") or "").strip() or "Unknown",
                            "outgoing": bool(item.get("outgoing")),
                            "timestamp_ms": item.get("timestamp_ms"),
                            "text": enriched["text"],
                            "display_text": enriched["display_text"],
                            "links": enriched["links"],
                        }
                        publish(payload)
            except Exception:
                logger.exception("Poll Telegram Web failed")

            stop_event.wait(FEED_POLL_SECONDS)

        try:
            context.close()
        except Exception:
            pass


def start_poller_thread(
    loop: asyncio.AbstractEventLoop,
    hub_publish: Callable[[Dict[str, Any]], asyncio.Future],
) -> tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()

    def publish(payload: Dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(hub_publish(payload), loop)

    thread = threading.Thread(
        target=run_telegram_feed_poller,
        kwargs={"loop": loop, "publish": publish, "stop_event": stop_event},
        name="telegram-web-feed",
        daemon=True,
    )
    thread.start()
    return thread, stop_event
