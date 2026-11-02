#!/usr/bin/env python3
"""Kiem tra profile VPS da duoc duyet device junb + thanhtai chua."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / "browser-data-vps"
OUT = ROOT / "data" / "vps-device-check"
SNSSDK = re.compile(r"snssdk1180://live\?room_id=(\d{15,22})")
JUNB = re.compile(r"https://i\.junb\.io\.vn/l/\?[^\s\"'<>]+", re.I)
TT = re.compile(r"https://thanhtai\.io/r/[0-9a-f]+", re.I)


def find_fresh_urls() -> dict[str, str]:
    found = {"junb": "", "thanhtai": ""}
    db = Path("/root/click-live/server/telegram_bot/data/queue.db")
    if not db.exists():
        return found
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    blobs: list[str] = []
    for table in tables:
        cols = [r[1] for r in con.execute(f"pragma table_info({table})")]
        for col in cols:
            try:
                rows = con.execute(f"select {col} from {table} order by rowid desc limit 60").fetchall()
            except Exception:
                continue
            for (val,) in rows:
                if isinstance(val, (bytes, bytearray)):
                    try:
                        val = val.decode("utf-8", "ignore")
                    except Exception:
                        continue
                if val:
                    blobs.append(str(val))
    con.close()
    for blob in blobs:
        if not found["junb"]:
            m = JUNB.search(blob)
            if m:
                found["junb"] = m.group(0)
        if not found["thanhtai"]:
            m = TT.search(blob)
            if m:
                found["thanhtai"] = m.group(0)
        if found["junb"] and found["thanhtai"]:
            break
    return found


def dump(page, name: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"{name}.png"
    try:
        page.screenshot(path=str(png), full_page=True)
    except Exception:
        png = None
    text = ""
    try:
        text = page.inner_text("body") or ""
    except Exception:
        text = ""
    return {"url": page.url, "text": text[:1500], "screenshot": str(png) if png else ""}


def capture_snssdk(page, url: str, click: bool, timeout_s: float = 12) -> str:
    got: list[str] = []

    def on_req(req) -> None:
        m = SNSSDK.search(req.url)
        if m and not got:
            got.append(f"snssdk1180://live?room_id={m.group(1)}")

    page.on("request", on_req)
    page.on("requestfailed", on_req)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
    except Exception:
        pass
    if click:
        try:
            page.wait_for_selector("#openLinkBtn", timeout=5000)
            page.click("#openLinkBtn")
        except Exception:
            pass
    deadline = time.monotonic() + timeout_s
    while not got and time.monotonic() < deadline:
        page.wait_for_timeout(200)
        m = SNSSDK.search(page.content() or "")
        if m:
            got.append(f"snssdk1180://live?room_id={m.group(1)}")
            break
    try:
        page.remove_listener("request", on_req)
        page.remove_listener("requestfailed", on_req)
    except Exception:
        pass
    return got[0] if got else ""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    urls = find_fresh_urls()
    result: dict = {"profile": str(PROFILE), "urls": urls}

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=True,
            viewport={"width": 1440, "height": 960},
            locale="vi-VN",
            timezone_id="Asia/Bangkok",
            ignore_default_args=["--enable-automation"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        verify: list[dict] = []

        def on_resp(resp) -> None:
            u = resp.url
            if "verify" in u.lower() or "/ld" in u.lower() or "device" in u.lower():
                body = ""
                try:
                    body = (resp.text() or "")[:180]
                except Exception:
                    body = ""
                verify.append({"status": resp.status, "url": u[:180], "body": body})

        page.on("response", on_resp)

        page.goto("https://thanhtai.io/device", wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(2000)
        result["thanhtai_device"] = dump(page, "thanhtai-device")
        cookies = {c["name"]: c["value"] for c in ctx.cookies() if c.get("name") == "device_id"}
        result["thanhtai_cookie"] = cookies

        if urls.get("thanhtai"):
            deeplink = capture_snssdk(page, urls["thanhtai"], click=False, timeout_s=8)
            result["thanhtai_decode"] = {
                "url": urls["thanhtai"],
                "deeplink": deeplink,
                **dump(page, "thanhtai-r"),
            }

        ls = {}
        page.goto("https://i.junb.io.vn/l/?sb=2#check", wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(1500)
        try:
            ls = page.evaluate("() => Object.fromEntries(Object.keys(localStorage).map(k => [k, localStorage.getItem(k)]))")
        except Exception:
            ls = {}
        result["junb_localStorage"] = ls
        result["junb_page"] = dump(page, "junb-check")

        if urls.get("junb"):
            deeplink = capture_snssdk(page, urls["junb"], click=True, timeout_s=12)
            result["junb_decode"] = {
                "url": urls["junb"],
                "deeplink": deeplink,
                **dump(page, "junb-l"),
            }

        result["verify"] = verify[-12:]
        ctx.close()

    (OUT / "check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
