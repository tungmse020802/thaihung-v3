#!/usr/bin/env python3
"""CLI: giải mã deeplink TikTok từ URL (junb / thanhtai / countdown) bằng profile Chrome."""

import argparse
import sys

from deeplink_browser import resolve_deeplink_via_browser


def main() -> None:
    parser = argparse.ArgumentParser(description="Giải mã TikTok live deeplink qua Playwright profile")
    parser.add_argument("url", help="Link đầy đủ (junb.io.vn, thanhtai.io, ...)")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Hiện cửa sổ Chrome (debug); mặc định headless",
    )
    parser.add_argument("--timeout-ms", type=int, default=None, help="Timeout ms")
    args = parser.parse_args()

    try:
        deeplink = resolve_deeplink_via_browser(
            args.url,
            headless=not args.headed,
            timeout_ms=args.timeout_ms,
        )
    except Exception as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        sys.exit(1)

    print(deeplink)


if __name__ == "__main__":
    main()
