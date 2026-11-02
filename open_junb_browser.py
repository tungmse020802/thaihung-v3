#!/usr/bin/env python3
"""Bật Chromium (profile thaihung-v3) — Telegram Web + tab junb."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO / "profile_playwright"))

from junb_playwright import open_junb_browser_visible  # noqa: E402

if __name__ == "__main__":
    open_junb_browser_visible()
    try:
        import time

        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
