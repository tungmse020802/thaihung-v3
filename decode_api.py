#!/usr/bin/env python3
"""API giải mã trên Mac — Chromium headed + profile thaihung-v3/browser-data.

VPS gọi qua SSH reverse tunnel: 127.0.0.1:8793
"""

from __future__ import annotations

import asyncio
import logging
import os

os.environ["FEED_HEADLESS"] = os.environ.get("FEED_HEADLESS", "false")

from aiohttp import web

from deeplink_browser import resolve_deeplink_via_browser, warm_browser
from link_resolve import _ok_deeplink
from settings import PROFILE_DIR

HOST = os.environ.get("MAC_DECODE_HOST", "127.0.0.1")
PORT = int(os.environ.get("MAC_DECODE_PORT", "8793"))


async def decode_handler(request: web.Request) -> web.Response:
    url = (request.query.get("url") or "").strip()
    if not url:
        body = await request.json() if request.body_exists else {}
        url = str(body.get("url") or "").strip()
    if not url:
        return web.json_response({"ok": False, "error": "missing url"}, status=400)
    loop = asyncio.get_running_loop()
    try:
        raw = await loop.run_in_executor(None, resolve_deeplink_via_browser, url)
        deeplink = _ok_deeplink(raw)
        if not deeplink:
            return web.json_response({"ok": False, "url": url, "deeplink": ""})
        return web.json_response({"ok": True, "url": url, "deeplink": deeplink})
    except Exception as exc:
        return web.json_response({"ok": False, "url": url, "error": str(exc), "deeplink": ""})


async def health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "profile": str(PROFILE_DIR)})


async def on_startup(_app: web.Application) -> None:
    warm_browser()
    logging.getLogger(__name__).info("Mac decode API ready profile=%s", PROFILE_DIR)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = web.Application()
    app.router.add_get("/decode", decode_handler)
    app.router.add_post("/decode", decode_handler)
    app.router.add_get("/health", health)
    app.on_startup.append(on_startup)
    print(f"Mac decode API http://{HOST}:{PORT}/decode")
    print(f"Profile: {PROFILE_DIR}  (headed Chromium — giống lúc bạn mở tay)")
    web.run_app(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
