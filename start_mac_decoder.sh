#!/usr/bin/env bash
# Giải mã trên Mac (profile + IP nhà) rồi tunnel vào VPS :8793
# Giữ script này chạy. Đóng Chrome Playwright khác dùng cùng browser-data trước.
set -euo pipefail
cd "$(dirname "$0")"
SERVER_HOST="${SERVER_HOST:-160.30.19.215}"
SERVER_USER="${SERVER_USER:-root}"
SERVER_PASS="${SERVER_PASS:-}"
if [[ -f ../server/telegram_bot/.deploy_secret ]]; then
  # shellcheck disable=SC1091
  source ../server/telegram_bot/.deploy_secret
fi

echo "==> Đóng Chromium đang khóa profile thaihung-v3/browser-data"
pkill -f "thaihung-v3.*open_browser.py" 2>/dev/null || true
pkill -f "thaihung-v3.*open_junb_browser.py" 2>/dev/null || true
sleep 1

export FEED_HEADLESS=false
echo "==> API decode headed http://127.0.0.1:8793  profile=$(pwd)/browser-data"
.venv/bin/python decode_api.py &
API_PID=$!
sleep 3
if ! curl -sf --max-time 3 http://127.0.0.1:8793/health >/dev/null; then
  echo "API chưa lên — xem cửa sổ Chromium / log" >&2
fi

echo "==> SSH reverse tunnel VPS:8793 → Mac:8793"
sshpass -p "$SERVER_PASS" ssh -N \
  -o StrictHostKeyChecking=no \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -R 127.0.0.1:8793:127.0.0.1:8793 \
  "${SERVER_USER}@${SERVER_HOST}" &
TUN_PID=$!
echo "API pid=$API_PID  tunnel pid=$TUN_PID"
echo "Giữ terminal này. Ctrl+C dừng."
trap 'kill $API_PID $TUN_PID 2>/dev/null || true' EXIT
wait
