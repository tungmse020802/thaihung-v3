#!/usr/bin/env python3
"""Giữ Chromium mở — Telegram Web + tự do mở link giải mã tay."""

from playwright.sync_api import sync_playwright

from browser import launch_context
from settings import TELEGRAM_WEB_URL


def main() -> None:
    with sync_playwright() as playwright:
        context = launch_context(playwright, headless=False, inject_device=True)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(TELEGRAM_WEB_URL, wait_until="domcontentloaded")
        print("Browser đang mở. Đóng cửa sổ để thoát.")
        try:
            context.wait_for_event("close", timeout=0)
        except Exception:
            pass


if __name__ == "__main__":
    main()
