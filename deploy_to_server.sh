#!/usr/bin/env bash
# Deploy thaihung-v3 (Telethon feed + WS UI) lên VPS.
# Usage: SERVER_PASS='...' bash deploy_to_server.sh
set -euo pipefail

cd "$(dirname "$0")"
ROOT_DIR="$(pwd)"
REMOTE_DIR="${REMOTE_DIR:-/root/click-live/thaihung-v3}"
SERVER_HOST="${SERVER_HOST:-160.30.19.215}"
SERVER_USER="${SERVER_USER:-root}"
SERVER_PASS="${SERVER_PASS:-}"
BOT_ENV="/root/click-live/server/telegram_bot/.env"

if [[ -f .deploy_secret ]]; then
  # shellcheck disable=SC1091
  source .deploy_secret 2>/dev/null || true
fi
if [[ -z "$SERVER_PASS" && -f ../server/telegram_bot/.deploy_secret ]]; then
  # shellcheck disable=SC1091
  source ../server/telegram_bot/.deploy_secret
fi

if ! command -v sshpass >/dev/null 2>&1; then
  echo "Cần sshpass" >&2
  exit 1
fi
if [[ -z "$SERVER_PASS" ]]; then
  read -r -s -p "SSH password: " SERVER_PASS
  echo
fi

SSH_OPTS=(-o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no)
SSH=(sshpass -p "$SERVER_PASS" ssh "${SSH_OPTS[@]}" "${SERVER_USER}@${SERVER_HOST}")
RSYNC_SSH="sshpass -p ${SERVER_PASS} ssh ${SSH_OPTS[*]}"

echo "==> Dọn app cũ / docker rác trên server"
"${SSH[@]}" bash -s <<'CLEAN'
set -euo pipefail
systemctl stop click-live-telegram-reader-app2.service 2>/dev/null || true
systemctl disable click-live-telegram-reader-app2.service 2>/dev/null || true
pkill -f telegram_web_reader.py 2>/dev/null || true
pkill -f "python3 queue_ui.py" 2>/dev/null || true
# Giữ click-live-telegram-reader (queue chính) — feed dùng session riêng data/feed.session
rm -rf /var/lib/docker /var/lib/containerd 2>/dev/null || true
command -v docker >/dev/null && echo "WARN: docker vẫn còn" || echo "Docker: OK removed"
CLEAN

# Session Telethon gắn IP — login trên VPS (login_on_server.sh), không copy session Mac → server
if [[ "${SKIP_LOCAL_SESSION:-0}" == "1" ]]; then
  PUSH_LOCAL_SESSION=0
elif [[ "${PUSH_LOCAL_SESSION:-0}" == "1" && -f data/feed.session ]]; then
  echo "==> PUSH_LOCAL_SESSION=1: đẩy data/feed.session (cảnh báo: IP khác server có thể revoke)"
  PUSH_LOCAL_SESSION=1
elif [[ -f data/feed.session ]]; then
  echo "==> Bỏ qua session Mac (login trên server: bash login_on_server.sh)"
  PUSH_LOCAL_SESSION=0
else
  PUSH_LOCAL_SESSION=0
fi

echo "==> Rsync thaihung-v3"
rsync -az --delete \
  --exclude '.venv/' \
  --exclude 'browser-data/' \
  --exclude '__pycache__/' \
  --exclude '.env' \
  --exclude 'data/*.session*' \
  -e "$RSYNC_SSH" \
  "$ROOT_DIR/" "${SERVER_USER}@${SERVER_HOST}:${REMOTE_DIR}/"

if [[ "$PUSH_LOCAL_SESSION" == "1" ]]; then
  rsync -az -e "$RSYNC_SSH" \
    "$ROOT_DIR/data/feed.session" \
    "${SERVER_USER}@${SERVER_HOST}:${REMOTE_DIR}/data/feed.session"
fi

echo "==> Setup venv + .env + session feed riêng"
"${SSH[@]}" bash -s <<REMOTE
set -euo pipefail
REMOTE_DIR="$REMOTE_DIR"
BOT_ENV="$BOT_ENV"
PUSH_LOCAL_SESSION="$PUSH_LOCAL_SESSION"
cd "\$REMOTE_DIR"
mkdir -p data

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -r requirements.txt

if [[ ! -f .env && -f "\$BOT_ENV" ]]; then
  grep -E '^(TELEGRAM_API_ID|TELEGRAM_API_HASH|TELEGRAM_PHONE)=' "\$BOT_ENV" > .env || true
  cat >> .env <<'EOF'
TELEGRAM_PHONE=+84867493667
TELEGRAM_CLIENT_SESSION=data/feed.session
TELEGRAM_CHAT_HASH=-3431776950
TELEGRAM_CHAT_IDS=-1003431776950,-1004298855488
FEED_HOST=0.0.0.0
FEED_PORT=8796
DEEPLINK_API_BASE_URL=http://127.0.0.1:8792
EOF
fi

# Luôn cập nhật SĐT + nhóm feed (acc moon_2)
if [[ -f .env ]]; then
  grep -q '^TELEGRAM_PHONE=' .env && sed -i 's/^TELEGRAM_PHONE=.*/TELEGRAM_PHONE=+84867493667/' .env || echo 'TELEGRAM_PHONE=+84867493667' >> .env
  grep -q '^TELEGRAM_CHAT_IDS=' .env && sed -i 's/^TELEGRAM_CHAT_IDS=.*/TELEGRAM_CHAT_IDS=-1003431776950,-1004298855488/' .env || echo 'TELEGRAM_CHAT_IDS=-1003431776950,-1004298855488' >> .env
  grep -q '^TELEGRAM_CLIENT_SESSION=' .env || echo 'TELEGRAM_CLIENT_SESSION=data/feed.session' >> .env
  grep -q '^FEED_AUTH_USER=' .env || echo 'FEED_AUTH_USER=admin' >> .env
  grep -q '^FEED_AUTH_PASSWORD=' .env || echo "FEED_AUTH_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')" >> .env
  grep -q '^FEED_JWT_SECRET=' .env || echo "FEED_JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> .env
  grep -q '^FEED_JWT_TTL=' .env || echo 'FEED_JWT_TTL=604800' >> .env
fi

# Session feed: file riêng (login_telethon.py) — KHÔNG copy app1 (trùng auth → Telegram revoke)
if [[ "\${PUSH_LOCAL_SESSION}" == "1" ]]; then
  echo "Dùng feed.session từ máy dev (rsync)"
elif [[ ! -f data/feed.session ]]; then
  echo "WARN: chưa có data/feed.session — chạy login_telethon trên server sau deploy"
fi

install -m 644 systemd/click-live-thaihung-feed.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable click-live-thaihung-feed.service
systemctl restart click-live-thaihung-feed.service
sleep 2
systemctl is-active click-live-thaihung-feed.service || true
ss -lntp | grep 8796 || true
REMOTE

echo "Done. UI: http://${SERVER_HOST}:8796/"
echo "Nếu session lỗi: ssh server 'cd ${REMOTE_DIR} && set -a && source .env && set +a && .venv/bin/python login_telethon.py'"
