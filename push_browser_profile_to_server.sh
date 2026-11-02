#!/usr/bin/env bash
# Đồng bộ Chromium profile Mac → VPS (junb xác minh /l/ #...).
#
# Mặc định: thaihung-v3/browser-data (Chrome bạn login Telegram + mở junb).
# Usage:
#   cd thaihung-v3 && bash push_browser_profile_to_server.sh
#   PROFILE_SRC=../profile_playwright/browser-data bash push_browser_profile_to_server.sh
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
SERVER_HOST="${SERVER_HOST:-160.30.19.215}"
SERVER_USER="${SERVER_USER:-root}"
SERVER_PASS="${SERVER_PASS:-}"
REMOTE_PW="${REMOTE_PW:-/root/click-live/profile_playwright}"

PROFILE_SRC="${PROFILE_SRC:-$(pwd)/browser-data}"
if [[ ! -d "$PROFILE_SRC" ]]; then
  echo "Không thấy profile: $PROFILE_SRC" >&2
  echo "Set PROFILE_SRC= đường dẫn thư mục browser-data trên Mac." >&2
  exit 1
fi

if [[ -f ../server/telegram_bot/.deploy_secret ]]; then
  # shellcheck disable=SC1091
  source ../server/telegram_bot/.deploy_secret
fi
if [[ -z "$SERVER_PASS" && -f .deploy_secret ]]; then
  # shellcheck disable=SC1091
  source .deploy_secret
fi
if ! command -v sshpass >/dev/null 2>&1; then
  echo "Cần sshpass" >&2
  exit 1
fi
if [[ -z "$SERVER_PASS" ]]; then
  read -r -s -p "SSH password VPS: " SERVER_PASS
  echo
fi

SSH=(sshpass -p "$SERVER_PASS" ssh -o StrictHostKeyChecking=no "${SERVER_USER}@${SERVER_HOST}")
RSYNC_SSH="sshpass -p ${SERVER_PASS} ssh -o StrictHostKeyChecking=no"

RSYNC_EX=(
  --exclude 'SingletonLock'
  --exclude 'SingletonSocket'
  --exclude 'SingletonCookie'
  --exclude 'RunningChromeVersion'
  --exclude 'DevToolsActivePort'
  --exclude 'Crashpad/**'
  --exclude 'ShaderCache/**'
  --exclude 'GrShaderCache/**'
  --exclude 'GraphiteDawnCache/**'
  --exclude 'BrowserMetrics-*'
  --exclude '*.pma'
  --exclude 'Default/IndexedDB/https_web.telegram.org_*'
  --exclude 'Default/Service Worker/**'
)

echo "==> Dừng deeplink API + feed (tránh khóa profile)"
"${SSH[@]}" 'systemctl stop click-live-deeplink-api click-live-thaihung-feed 2>/dev/null || true; sleep 3'

echo "==> Rsync profile Mac → thaihung-v3 (decode) + profile_playwright"
echo "    Nguồn: $PROFILE_SRC"
REMOTE_THAI="${REMOTE_THAI:-/root/click-live/thaihung-v3/browser-data}"
"${SSH[@]}" "mkdir -p ${REMOTE_THAI}"
rsync -az --delete "${RSYNC_EX[@]}" \
  -e "$RSYNC_SSH" \
  "${PROFILE_SRC}/" "${SERVER_USER}@${SERVER_HOST}:${REMOTE_THAI}/"
echo "    OK → ${REMOTE_THAI}/"
for dest in browser-data browser-data-junb; do
  "${SSH[@]}" "mkdir -p ${REMOTE_PW}/${dest}"
  rsync -az --delete "${RSYNC_EX[@]}" \
    -e "$RSYNC_SSH" \
    "${PROFILE_SRC}/" "${SERVER_USER}@${SERVER_HOST}:${REMOTE_PW}/${dest}/"
  echo "    OK → ${REMOTE_PW}/${dest}/"
done

echo "==> Bật lại services"
"${SSH[@]}" 'systemctl start click-live-deeplink-api click-live-thaihung-feed; sleep 3; systemctl is-active click-live-deeplink-api click-live-thaihung-feed'

echo ""
echo "Xong. Test link /l/ (đợi ~60s):"
echo "  curl --max-time 90 'http://${SERVER_HOST}:8792/api/deeplink?url='\"$(python3 -c 'import urllib.parse; print(urllib.parse.quote(\"https://i.junb.io.vn/l/?sb=2#TEST\", safe=\"\"))' 2>/dev/null || echo 'URL_ENCODED')\""
echo "Feed: http://${SERVER_HOST}:8796/"
