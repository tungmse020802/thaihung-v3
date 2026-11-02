#!/usr/bin/env bash
# Login Telethon TRÊN VPS (session gắn IP server — không dùng session login từ Mac).
# Chạy từ Terminal Mac (cần nhập OTP):
#   cd thaihung-v3 && bash login_on_server.sh
set -euo pipefail

cd "$(dirname "$0")"
SERVER_HOST="${SERVER_HOST:-160.30.19.215}"
SERVER_USER="${SERVER_USER:-root}"
SERVER_PASS="${SERVER_PASS:-}"
REMOTE_DIR="${REMOTE_DIR:-/root/click-live/thaihung-v3}"

if [[ -f ../server/telegram_bot/.deploy_secret ]]; then
  # shellcheck disable=SC1091
  source ../server/telegram_bot/.deploy_secret
fi
if [[ -z "$SERVER_PASS" && -f .deploy_secret ]]; then
  # shellcheck disable=SC1091
  source .deploy_secret
fi

if ! command -v sshpass >/dev/null 2>&1; then
  echo "Cần sshpass (brew install sshpass hoặc ssh -t thủ công)" >&2
  exit 1
fi
if [[ -z "$SERVER_PASS" ]]; then
  read -r -s -p "SSH password VPS: " SERVER_PASS
  echo
fi

echo "==> Đồng bộ login_telethon.py lên VPS"
sshpass -p "$SERVER_PASS" rsync -az -e "ssh -o StrictHostKeyChecking=no" \
  login_telethon.py "${SERVER_USER}@${SERVER_HOST}:${REMOTE_DIR}/"

echo "==> Mở SSH có TTY — nhập OTP trên acc +84867493667"
echo "    (Telegram gắn session theo IP VPS — login tại server là đúng)"
echo

# -t: bắt buộc để nhập mã OTP
sshpass -p "$SERVER_PASS" ssh -tt -o StrictHostKeyChecking=no \
  "${SERVER_USER}@${SERVER_HOST}" bash -s <<REMOTE
set -euo pipefail
cd "${REMOTE_DIR}"
systemctl stop click-live-thaihung-feed 2>/dev/null || true
pkill -f "thaihung-v3.*feed_server" 2>/dev/null || true
sleep 1

if [[ "\${RESET_SESSION:-0}" == "1" ]]; then
  rm -f data/feed.session data/feed.session-journal
  echo "Đã xóa session cũ."
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

mkdir -p data
.venv/bin/python login_telethon.py

echo ""
echo "==> Khởi động lại feed"
systemctl start click-live-thaihung-feed
sleep 2
systemctl is-active click-live-thaihung-feed || true
curl -s http://127.0.0.1:8796/api/status || true
echo ""
echo "UI: http://${SERVER_HOST}:8796/"
REMOTE
