#!/usr/bin/env python3
"""Mở Chromium với profile persistent — đăng nhập Telegram Web một lần."""

from playwright.sync_api import sync_playwright

from browser import launch_context
from settings import PROFILE_DIR, TELEGRAM_WEB_URL


def main() -> None:
    print(f"Profile: {PROFILE_DIR}")
    print(f"Mở: {TELEGRAM_WEB_URL}")
    print()
    print("1. Đăng nhập Telegram (QR hoặc SĐT).")
    print("2. Kiểm tra vào được danh sách chat.")
    print("3. (Tuỳ chọn) Mở link junb/thanhtai trong tab khác nếu cần cookie device.")
    print("4. Đóng cửa sổ Chromium (Cmd+Q) để lưu session vào browser-data/.")
    print()

    with sync_playwright() as playwright:
        context = launch_context(playwright, headless=False, inject_device=True)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(TELEGRAM_WEB_URL, wait_until="domcontentloaded")

        try:
            context.wait_for_event("close", timeout=0)
        except Exception:
            pass


if __name__ == "__main__":
    main()
