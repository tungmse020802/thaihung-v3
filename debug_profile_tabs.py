#!/usr/bin/env python3
"""Mở Telegram Web trên profile VPS — mỗi nhóm một tab — chụp màn để debug."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser import launch_context
from settings import PROFILE_DIR, TELEGRAM_CHAT_IDS
from telethon_feed import _parse_chat_ids, web_hash_from_chat_id

OUT = Path(__file__).resolve().parent / "data" / "debug-tabs"
HASHES = [web_hash_from_chat_id(cid) for cid in _parse_chat_ids(TELEGRAM_CHAT_IDS)]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    extra = [a for a in sys.argv[1:] if a.startswith("-")]
    hashes = extra or HASHES
    print(f"profile={PROFILE_DIR}")
    print(f"tabs={hashes}")
    with sync_playwright() as pw:
        context = launch_context(pw, headless=True, inject_device=True)
        pages = []
        for i, h in enumerate(hashes):
            page = context.pages[0] if i == 0 and context.pages else context.new_page()
            url = f"https://web.telegram.org/k/#{h}"
            print(f"open {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(4000)
            except Exception as exc:
                print(f"  goto fail: {exc}")
            shot = OUT / f"{h.lstrip('-')}.png"
            try:
                page.screenshot(path=str(shot), full_page=False)
            except Exception as exc:
                print(f"  shot fail: {exc}")
                shot = None
            title = ""
            try:
                title = page.title()
            except Exception:
                pass
            body = ""
            try:
                body = page.inner_text("body")[:240].replace("\n", " | ")
            except Exception:
                pass
            print(f"  title={title!r} shot={shot} text={body!r}")
            pages.append(page)
        print(f"open_pages={len(pages)} (mỗi nhóm 1 tab trong profile {PROFILE_DIR})")
        context.close()


if __name__ == "__main__":
    main()
