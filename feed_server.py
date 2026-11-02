"""HTTP + WebSocket: trang HTML giống Telegram, nhận tin đã giải mã deeplink."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Set

from aiohttp import web

from feed_auth import check_password, create_jwt, require_jwt
from settings import (
    DEVICE_ID,
    FEED_AUTH_USER,
    FEED_BROWSER_FALLBACK,
    FEED_DECODE_WORKERS,
    FEED_HISTORY_MAX,
    FEED_HOST,
    FEED_HTTP_DECODE,
    FEED_JWT_TTL,
    FEED_PORT,
    FEED_WS_SEND_HISTORY,
    JUNB_DEVICE_IDS,
    MAC_DECODE_URL,
    PROFILE_DIR,
)
from telethon_feed import run_telethon_feed

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


class FeedHub:
    def __init__(self) -> None:
        self.clients: Set[web.WebSocketResponse] = set()
        self.history: List[Dict[str, Any]] = []

    async def add_client(
        self,
        ws: web.WebSocketResponse,
        *,
        telethon_status: Dict[str, Any] | None = None,
    ) -> None:
        self.clients.add(ws)
        if telethon_status:
            await ws.send_str(
                json.dumps(
                    {**telethon_status, "type": "telethon_status"},
                    ensure_ascii=False,
                )
            )
        if FEED_WS_SEND_HISTORY and self.history:
            await ws.send_str(
                json.dumps({"type": "history", "items": self.history}, ensure_ascii=False)
            )

    def remove_client(self, ws: web.WebSocketResponse) -> None:
        self.clients.discard(ws)

    def has_clients(self) -> bool:
        live = {ws for ws in self.clients if not ws.closed}
        if live != self.clients:
            self.clients = live
        return bool(self.clients)

    async def broadcast_json(self, payload: Dict[str, Any]) -> None:
        if not self.has_clients():
            return
        dead: List[web.WebSocketResponse] = []
        body = json.dumps(payload, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_str(body)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remove_client(ws)

    async def publish(self, item: Dict[str, Any]) -> None:
        if not self.has_clients():
            return
        item = {**item, "type": "message"}
        msg_id = item.get("id")
        replaced = False
        if msg_id:
            for i, old in enumerate(self.history):
                if old.get("id") == msg_id:
                    self.history[i] = item
                    replaced = True
                    break
        if not replaced:
            self.history.append(item)
            if len(self.history) > FEED_HISTORY_MAX:
                self.history = self.history[-FEED_HISTORY_MAX:]

        await self.broadcast_json(item)


_INDEX_HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8")


async def index_handler(_request: web.Request) -> web.Response:
    return web.Response(
        text=_INDEX_HTML,
        content_type="text/html",
        charset="utf-8",
        headers={"Cache-Control": "no-store"},
    )


def _unauthorized() -> web.Response:
    return web.json_response({"ok": False, "error": "unauthorized"}, status=401)


async def login_handler(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        body = {}
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    if not check_password(username, password):
        return web.json_response({"ok": False, "error": "Sai tài khoản hoặc mật khẩu"}, status=401)
    token = create_jwt(username)
    return web.json_response(
        {"ok": True, "token": token, "username": username, "expires_in": FEED_JWT_TTL}
    )


async def websocket_handler(request: web.Request) -> web.StreamResponse:
    if not require_jwt(request):
        return _unauthorized()
    hub: FeedHub = request.app["hub"]
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    status = request.app.get("telethon_status")
    await hub.add_client(ws, telethon_status=status)
    try:
        async for _msg in ws:
            pass
    finally:
        hub.remove_client(ws)
    return ws


async def status_handler(request: web.Request) -> web.Response:
    if not require_jwt(request):
        return _unauthorized()
    status: Dict[str, Any] = request.app.get("telethon_status") or {
        "phase": "starting",
        "message": "Đang khởi động…",
    }
    status = {
        **status,
        "ws_clients": request.app["hub"].has_clients(),
    }
    return web.json_response(status)


async def on_startup(app: web.Application) -> None:
    hub: FeedHub = app["hub"]
    stop = asyncio.Event()
    app["telethon_stop"] = stop
    app["telethon_status"] = {"phase": "starting", "message": "Đang khởi động Telethon…"}

    async def set_status(payload: Dict[str, Any]) -> None:
        app["telethon_status"] = {k: v for k, v in payload.items() if k != "type"}
        asyncio.create_task(hub.broadcast_json(payload))

    async def _runner() -> None:
        delay = 5.0
        while not stop.is_set():
            try:
                await run_telethon_feed(
                    hub.publish,
                    stop=stop,
                    set_status=set_status,
                    has_clients=hub.has_clients,
                )
                break
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Telethon feed stopped; retry in %.0fs", delay)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=delay)
                    break
                except asyncio.TimeoutError:
                    delay = min(delay * 1.5, 120.0)

    app["telethon_task"] = asyncio.create_task(_runner())
    app["hub"].history.clear()

    if MAC_DECODE_URL:
        logger.info("Decode via Mac: %s (không mở Chromium trên VPS)", MAC_DECODE_URL)
    elif FEED_HTTP_DECODE and not FEED_BROWSER_FALLBACK:
        logger.info(
            "Decode HTTP trực tiếp (workers=%s, junb devices=%s, thanhtai device=%s) — không mở Chromium",
            FEED_DECODE_WORKERS,
            [d[:8] for d in JUNB_DEVICE_IDS] or "(thiếu)",
            DEVICE_ID or "(thiếu)",
        )
    else:
        def _warm() -> None:
            try:
                from deeplink_browser import warm_browser

                warm_browser()
                logger.info("Playwright profile warmed (%s)", PROFILE_DIR)
            except Exception:
                logger.exception("Playwright warm-up failed")

        threading.Thread(target=_warm, name="pw-warm", daemon=True).start()
    logger.info(
        "Telethon feed task started user=%s (chỉ gửi/decode khi có 1 WebSocket)",
        FEED_AUTH_USER,
    )


async def on_cleanup(app: web.Application) -> None:
    stop: asyncio.Event | None = app.get("telethon_stop")
    task: asyncio.Task | None = app.get("telethon_task")
    if stop is not None:
        stop.set()
    if task is not None:
        try:
            await asyncio.wait_for(task, timeout=15)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            task.cancel()


def create_app() -> web.Application:
    app = web.Application()
    app["hub"] = FeedHub()
    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/api/status", status_handler)
    app.router.add_post("/api/auth/login", login_handler)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    app = create_app()
    web.run_app(app, host=FEED_HOST, port=FEED_PORT)


if __name__ == "__main__":
    main()
