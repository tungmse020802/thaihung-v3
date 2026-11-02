#!/usr/bin/env bash
# Login Telethon trên MÁY BẠN (chỉ dev/test). Production: bash login_on_server.sh (session theo IP VPS).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data

if [[ ! -f .env ]]; then
  if [[ -f ../server/telegram_bot/.env ]]; then
    grep -E '^(TELEGRAM_API_ID|TELEGRAM_API_HASH)=' ../server/telegram_bot/.env > .env
  else
    echo "Thiếu .env — copy từ .env.example và điền API_ID/HASH" >&2
    exit 1
  fi
  cat >> .env <<'EOF'
TELEGRAM_PHONE=+84867493667
TELEGRAM_CLIENT_SESSION=data/feed.session
TELEGRAM_CHAT_IDS=-1003431776950
TELEGRAM_CHAT_HASH=-3431776950
EOF
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -U pip telethon python-dotenv

if [[ "${RESET_SESSION:-0}" == "1" ]]; then
  rm -f data/feed.session data/feed.session-journal
  echo "Đã xóa session cũ."
fi

echo "Login Telethon → data/feed.session (OTP gửi về Telegram acc +84867493667)"
set -a
# shellcheck disable=SC1091
source .env
set +a
.venv/bin/python login_telethon.py
echo "Production VPS: bash login_on_server.sh  (không đẩy session Mac lên server)"
