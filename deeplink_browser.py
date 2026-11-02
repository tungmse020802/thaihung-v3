"""Giải mã junb /l/ và thanhtai /r/ bằng Chromium persistent profile (thaihung-v3/browser-data).

Giữ 1 tab — goto + bắt request snssdk1180://live?room_id= (15–22 số).
"""

from __future__ import annotations

import atexit
import logging
import queue
import re
import threading
import time
from typing import Any, Optional
from urllib.parse import urlparse

from playwright.sync_api import Page, Playwright, Request, sync_playwright

from browser import launch_context
from settings import DEEPLINK_TIMEOUT_MS, FEED_HEADLESS, PROFILE_DIR

logger = logging.getLogger(__name__)

DEEPLINK_PREFIX = "snssdk1180://live?room_id="
SNSSDK_PATTERN = re.compile(r"snssdk1180://live\?room_id=(\d{15,22})(?:\D|$)")

_playwright: Playwright | None = None
_context = None
_page: Page | None = None
_worker: threading.Thread | None = None
_queue: queue.Queue | None = None
_lock = threading.Lock()
_last_junb_ts = 0.0
_junb_cooldown_until = 0.0
JUNB_MIN_GAP_S = 3.0
JUNB_COOLDOWN_S = 60.0


def parse_snssdk(text: str) -> Optional[str]:
    match = SNSSDK_PATTERN.search(text or "")
    if not match:
        return None
    return f"{DEEPLINK_PREFIX}{match.group(1)}"


def _needs_open_link_click(url: str) -> bool:
    path = (urlparse(url).path or "").lower()
    return "/l/" in path or "/s/" in path or "/j/" in path


def _ensure_browser() -> None:
    global _playwright, _context, _page
    if _context is not None:
        return
    logger.info("Playwright profile: %s headless=%s", PROFILE_DIR, FEED_HEADLESS)
    _playwright = sync_playwright().start()
    _context = launch_context(_playwright, headless=FEED_HEADLESS, inject_device=False)
    _page = _context.pages[0] if _context.pages else _context.new_page()


def _pump(page: Page, captured: list[str], seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while not captured and time.monotonic() < deadline:
        page.wait_for_timeout(200)
        if not captured:
            _maybe_page(page, captured)


def _maybe_page(page: Page, captured: list[str]) -> None:
    parsed = parse_snssdk(page.content() if not page.is_closed() else "")
    if parsed and not captured:
        captured.append(parsed)


def _trip_junb_cooldown() -> None:
    global _junb_cooldown_until
    _junb_cooldown_until = time.monotonic() + JUNB_COOLDOWN_S
    logger.warning("junb verify 429 — cooldown %.0fs", JUNB_COOLDOWN_S)


def _click_open_link(page: Page) -> None:
    page.wait_for_selector("#openLinkBtn", state="visible", timeout=5000)
    page.wait_for_timeout(250)
    page.evaluate(
        """() => {
          const btn = document.querySelector('#openLinkBtn');
          if (btn) btn.click();
        }"""
    )
    logger.info("clicked #openLinkBtn")


def _resolve_on_worker(url: str, timeout_ms: int) -> str:
    global _page, _last_junb_ts, _junb_cooldown_until
    _ensure_browser()
    assert _context is not None
    page = _page
    if page is None or page.is_closed():
        page = _context.pages[0] if _context.pages else _context.new_page()
        _page = page

    if _needs_open_link_click(url):
        remain = _junb_cooldown_until - time.monotonic()
        if remain > 0:
            raise ValueError(f"junb verify 429 cooldown {remain:.0f}s")
        wait = JUNB_MIN_GAP_S - (time.monotonic() - _last_junb_ts)
        if wait > 0:
            logger.info("junb throttle %.1fs", wait)
            time.sleep(wait)
        _last_junb_ts = time.monotonic()

    captured: list[str] = []
    seen_hosts: list[str] = []
    verify_status: list[int] = []
    done = threading.Event()

    def _maybe(raw: str) -> None:
        parsed = parse_snssdk(raw)
        if parsed and not captured:
            captured.append(parsed)
            done.set()

    def on_request(request: Request) -> None:
        raw = request.url
        if len(seen_hosts) < 12:
            seen_hosts.append(raw[:120])
        _maybe(raw)

    ctx = page.context
    def on_response(response) -> None:
        raw = response.url
        if any(k in raw.lower() for k in ("verify", "/ld", "ld?", "snssdk", "room_id")):
            body = ""
            try:
                body = (response.text() or "")[:180].replace("\n", " ")
            except Exception:
                body = ""
            logger.info("resp %s %s %s", response.status, raw[:160], body)
            if "verify" in raw.lower():
                verify_status.append(int(response.status))
            _maybe(raw)
            _maybe(body)

    ctx.on("request", on_request)
    ctx.on("requestfailed", on_request)
    ctx.on("response", on_response)

    def on_new_page(new_page: Page) -> None:
        try:
            _maybe(new_page.url)
        except Exception:
            pass

    ctx.on("page", on_new_page)
    cdp = None
    try:
        cdp = ctx.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.send("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True})

        def on_cdp(params: dict) -> None:
            req = params.get("request") or {}
            _maybe(str(req.get("url") or ""))

        cdp.on("Network.requestWillBeSent", on_cdp)
    except Exception:
        logger.warning("CDP Network.enable failed", exc_info=True)

    try:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception as exc:
            logger.info("goto: %s", exc)

        logger.info("after goto page.url=%s hash=%s", page.url, urlparse(url).fragment)
        _pump(page, captured, 1.5)

        if _needs_open_link_click(url) and not captured:
            if 429 in verify_status:
                _trip_junb_cooldown()
                raise ValueError("junb verify 429 — tạm nghỉ 60s, không click thêm")
            try:
                _click_open_link(page)
            except Exception as exc:
                logger.info("openLinkBtn: %s", exc)
            _pump(page, captured, 8.0)
            if 429 in verify_status and not captured:
                _trip_junb_cooldown()
                raise ValueError("junb verify 429 sau click — tạm nghỉ 60s")
        else:
            _pump(page, captured, 4.0)

        interesting = [u for u in seen_hosts if any(k in u.lower() for k in ("snssdk", "verify", "ld?", "/ld", "room_id", "live"))]
        if captured:
            logger.info("captured %s verify=%s", captured[0], verify_status)
            return captured[0]
        logger.info("no snssdk page=%s verify=%s interesting=%s", page.url, verify_status, interesting or seen_hosts[:8])
        raise ValueError(
            f"Không bắt được snssdk1180 (15–22 số) cho {url} | page={page.url} | verify={verify_status} | req={interesting or seen_hosts[:8]}"
        )
    finally:
        try:
            ctx.remove_listener("request", on_request)
            ctx.remove_listener("requestfailed", on_request)
            ctx.remove_listener("response", on_response)
            ctx.remove_listener("page", on_new_page)
        except Exception:
            pass
        if cdp is not None:
            try:
                cdp.detach()
            except Exception:
                pass


def _worker_loop() -> None:
    assert _queue is not None
    while True:
        item = _queue.get()
        try:
            if item is None:
                return
            url, holder, event = item
            try:
                if url == "__warm__":
                    _ensure_browser()
                    holder["result"] = "ok"
                else:
                    holder["result"] = _resolve_on_worker(
                        url, int(holder.get("timeout_ms", DEEPLINK_TIMEOUT_MS))
                    )
            except Exception as exc:
                holder["error"] = exc
            finally:
                event.set()
        finally:
            _queue.task_done()


def _ensure_worker() -> None:
    global _worker, _queue
    with _lock:
        if _worker is not None and _worker.is_alive():
            return
        _queue = queue.Queue()
        _worker = threading.Thread(target=_worker_loop, name="thaihung-deeplink", daemon=True)
        _worker.start()


def warm_browser() -> None:
    _ensure_worker()
    assert _queue is not None
    holder: dict[str, Any] = {}
    event = threading.Event()
    _queue.put(("__warm__", holder, event))
    if not event.wait(timeout=60):
        raise TimeoutError("Playwright warm-up timed out")
    if holder.get("error"):
        raise holder["error"]


def resolve_deeplink_via_browser(url: str, *, timeout_ms: int | None = None, **_kwargs) -> str:
    clean = (url or "").strip()
    if not clean:
        raise ValueError("Thiếu URL")
    _ensure_worker()
    assert _queue is not None
    wait_ms = timeout_ms if timeout_ms is not None else DEEPLINK_TIMEOUT_MS
    holder: dict[str, Any] = {"timeout_ms": wait_ms}
    event = threading.Event()
    _queue.put((clean, holder, event))
    if not event.wait(timeout=(wait_ms / 1000) + 10):
        raise TimeoutError(f"Playwright resolve timed out for {clean}")
    if holder.get("error"):
        raise holder["error"]
    result = holder.get("result")
    if not result:
        raise ValueError("empty")
    return str(result)


def try_resolve_deeplink_via_browser(url: str, **kwargs) -> Optional[str]:
    try:
        return resolve_deeplink_via_browser(url, **kwargs)
    except Exception:
        logger.warning("decode fail %s", url)
        return None


def _shutdown() -> None:
    global _playwright, _context, _page, _worker, _queue
    if _queue is not None:
        _queue.put(None)
    if _worker is not None:
        _worker.join(timeout=5)
        _worker = None
        _queue = None
    _page = None
    if _context is not None:
        try:
            _context.close()
        except Exception:
            pass
        _context = None
    if _playwright is not None:
        try:
            _playwright.stop()
        except Exception:
            pass
        _playwright = None


atexit.register(_shutdown)
