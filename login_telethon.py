#!/usr/bin/env python3
"""Login Telethon session (server hoặc local).

SSH không TTY (Cursor terminal): chạy 2 bước:
  1) .venv/bin/python login_telethon.py send-code
  2) .venv/bin/python login_telethon.py --code 12345
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def _session_path() -> Path:
    session = os.environ.get("TELEGRAM_CLIENT_SESSION", "data/feed.session")
    path = Path(session)
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _phone() -> str:
    phone = os.environ.get("TELEGRAM_PHONE", "").strip()
    if phone:
        return phone
    if sys.stdin.isatty():
        return input("SĐT (+84867493667): ").strip()
    print("Thiếu TELEGRAM_PHONE trong .env", file=sys.stderr)
    sys.exit(1)


def _prompt(label: str) -> str:
    print(label, flush=True)
    if not sys.stdin.isatty():
        print(
            "(Terminal không tương tác — truyền mã qua: --code hoặc TELEGRAM_CODE=...)",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(2)
    return input().strip()


async def _run(*, send_only: bool, code: str | None, password: str | None) -> None:
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    path = _session_path()
    phone = _phone()

    client = TelegramClient(str(path), api_id, api_hash)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Đã login sẵn: {me.phone} (@{me.username})")
        print(f"Session: {path}")
        await client.disconnect()
        return

    if send_only:
        await client.send_code_request(phone)
        print(f"Đã gửi OTP tới {phone} (Telegram app / SMS).")
        print(f"Chạy: .venv/bin/python login_telethon.py --code MÃ_OTP")
        await client.disconnect()
        return

    if not code:
        await client.send_code_request(phone)
        print(f"Đã gửi OTP tới {phone}.", flush=True)
        if sys.stdin.isatty():
            code = os.environ.get("TELEGRAM_CODE", "").strip() or _prompt("Nhập mã OTP: ")
        else:
            print("SSH không TTY — dùng: login_telethon.py send-code rồi --code MÃ")
            await client.disconnect()
            return

    assert code
    try:
        await client.sign_in(phone=phone, code=code.strip())
    except SessionPasswordNeededError:
        pwd = password or os.environ.get("TELEGRAM_2FA", "").strip()
        if not pwd:
            pwd = _prompt("Tai khoan bat 2FA — nhap mat khau: ")
        await client.sign_in(password=pwd)

    me = await client.get_me()
    print(f"Login OK: {me.phone} (@{me.username})")
    print(f"Session: {path}")
    await client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Login Telethon cho thaihung feed")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("send-code",),
        help="Chỉ gửi OTP (dùng khi SSH không nhập được mã)",
    )
    parser.add_argument("--code", help="Mã OTP từ Telegram")
    parser.add_argument("--password", help="Mật khẩu 2FA nếu có")
    args = parser.parse_args()

    code = args.code or os.environ.get("TELEGRAM_CODE", "").strip() or None
    send_only = args.command == "send-code"

    asyncio.run(
        _run(send_only=send_only, code=code, password=args.password),
    )


if __name__ == "__main__":
    main()
