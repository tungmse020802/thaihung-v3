#!/usr/bin/env bash
# Chỉ đẩy code + restart (KHÔNG rsync session từ Mac — tránh lệch IP Telegram).
# Login session: bash login_on_server.sh
set -euo pipefail
export SKIP_LOCAL_SESSION=1
cd "$(dirname "$0")"
exec bash deploy_to_server.sh
