#!/usr/bin/env python3
"""Tạo profile Chromium mới trên VPS và lấy mã đăng ký thiết bị junb + thanhtai."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PROFILE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "browser-data-vps"
OUT = ROOT / "data" / "vps-device-register"
JUNB_URLS = [
    "https://i.junb.io.vn/",
    "https://i.junb.io.vn/device",
    "https://l.junb.io.vn/device",
    "https://i.junb.io.vn/l/?sb=2#vps-register",
]
THANHTAI_URLS = [
    "https://thanhtai.io/device",
    "https://thanhtai.io/r/525ddbd53026",
]


def _dump_page(page, label: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    shot = OUT / f"{label}.png"
    html = OUT / f"{label}.html"
    try:
        page.screenshot(path=str(shot), full_page=True)
    except Exception:
        shot = None
    try:
        html.write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    text = ""
    try:
        text = page.inner_text("body") or ""
    except Exception:
        text = ""
    storage = {}
    try:
        storage = page.evaluate(
            """() => {
              const out = {localStorage: {}, sessionStorage: {}};
              try {
                for (let i = 0; i < localStorage.length; i++) {
                  const k = localStorage.key(i);
                  out.localStorage[k] = localStorage.getItem(k);
                }
              } catch (e) {}
              try {
                for (let i = 0; i < sessionStorage.length; i++) {
                  const k = sessionStorage.key(i);
                  out.sessionStorage[k] = sessionStorage.getItem(k);
                }
              } catch (e) {}
              return out;
            }"""
        )
    except Exception:
        storage = {}
    return {
        "url": page.url,
        "text": text,
        "storage": storage,
        "screenshot": str(shot) if shot else "",
    }


def _codes_from(info: dict, cookies: list[dict]) -> list[str]:
    found: list[str] = []
    blob = info.get("text") or ""
    for m in re.findall(r"device_[a-f0-9-]{8,}", blob, re.I):
        found.append(m)
    for m in re.findall(r"\b[a-f0-9]{32}\b", blob):
        found.append(m)
    for cookie in cookies:
        if cookie.get("name") in ("device_id", "device", "did", "d"):
            found.append(f"{cookie.get('domain')}:{cookie.get('name')}={cookie.get('value')}")
    storage = ((info.get("storage") or {}).get("localStorage") or {})
    for key, val in storage.items():
        if re.search(r"device|did|fingerprint|uid", key, re.I) or (
            isinstance(val, str) and re.search(r"device_|[a-f0-9]{32}", val)
        ):
            found.append(f"localStorage.{key}={val}")
    # unique preserve order
    out = []
    for item in found:
        if item not in out:
            out.append(item)
    return out


def main() -> None:
    PROFILE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    result = {"profile": str(PROFILE), "thanhtai": [], "junb": []}

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

        for i, url in enumerate(THANHTAI_URLS):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
            except Exception as exc:
                result["thanhtai"].append({"url": url, "error": str(exc)})
                continue
            page.wait_for_timeout(2500)
            info = _dump_page(page, f"thanhtai-{i}")
            info["codes"] = _codes_from(info, ctx.cookies())
            result["thanhtai"].append(info)

        for i, url in enumerate(JUNB_URLS):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
            except Exception as exc:
                result["junb"].append({"url": url, "error": str(exc)})
                continue
            page.wait_for_timeout(2500)
            try:
                page.click("#openLinkBtn", timeout=2000)
                page.wait_for_timeout(1500)
            except Exception:
                pass
            info = _dump_page(page, f"junb-{i}")
            info["codes"] = _codes_from(info, ctx.cookies())
            result["junb"].append(info)

        result["cookies"] = [
            {
                "name": c.get("name"),
                "domain": c.get("domain"),
                "value": c.get("value"),
            }
            for c in ctx.cookies()
            if any(k in (c.get("name") or "").lower() for k in ("device", "did", "uid"))
            or "junb" in (c.get("domain") or "")
            or "thanhtai" in (c.get("domain") or "")
        ]
        ctx.close()

    out_json = OUT / "result.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
