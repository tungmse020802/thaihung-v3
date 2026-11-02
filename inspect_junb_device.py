#!/usr/bin/env python3
"""Mở link junb /l/ thật trên profile VPS, bấm MỞ LINK, chụp trang đăng ký."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / "browser-data-vps"
OUT = ROOT / "data" / "vps-device-register"
URL = sys.argv[1] if len(sys.argv) > 1 else ""


def snap(page, name: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"{name}.png"
    html = OUT / f"{name}.html"
    try:
        page.screenshot(path=str(png), full_page=True)
    except Exception:
        png = None
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
              const ls = {};
              try {
                for (let i = 0; i < localStorage.length; i++) {
                  const k = localStorage.key(i);
                  ls[k] = localStorage.getItem(k);
                }
              } catch (e) {}
              return {href: location.href, hash: location.hash, ls};
            }"""
        )
    except Exception:
        storage = {}
    return {
        "url": page.url,
        "text": text[:2000],
        "storage": storage,
        "screenshot": str(png) if png else "",
    }


def main() -> None:
    if not URL:
        raise SystemExit("missing url")
    reqs: list[str] = []
    steps: list[dict] = []
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
        page.on("request", lambda r: reqs.append(r.url) if len(reqs) < 80 else None)
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=25000)
        except Exception as exc:
            steps.append({"step": "goto", "error": str(exc)})
        page.wait_for_timeout(2000)
        steps.append({"step": "after_goto", **snap(page, "junb-real-1")})

        clicked = False
        for sel in ("#openLinkBtn", "button", "a"):
            try:
                loc = page.locator(sel).first
                if loc.count() == 0:
                    continue
                loc.click(timeout=2500)
                clicked = True
                break
            except Exception:
                continue
        page.wait_for_timeout(3500)
        steps.append({"step": "after_click", "clicked": clicked, **snap(page, "junb-real-2")})

        # click any "đăng ký / copy / xác minh" extra
        for label in ("đăng ký", "Duyệt", "Copy", "copy", "Xác minh"):
            try:
                page.get_by_text(label, exact=False).first.click(timeout=1200)
                page.wait_for_timeout(1500)
                steps.append({"step": f"click_{label}", **snap(page, f"junb-real-{label}")})
            except Exception:
                pass

        cookies = [
            {"name": c.get("name"), "domain": c.get("domain"), "value": c.get("value")}
            for c in ctx.cookies()
            if "junb" in (c.get("domain") or "")
        ]
        ctx.close()

    interesting = [
        u for u in reqs if any(k in u.lower() for k in ("verify", "device", "ld?", "register", "auth"))
    ]
    out = {"url": URL, "steps": steps, "interesting": interesting, "cookies": cookies}
    (OUT / "junb-real.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
