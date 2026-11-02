import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# Chromium persistent profile (Telegram Web login + cookies junb/thanhtai nếu có)
_profile = os.environ.get("FEED_PROFILE_DIR", "").strip()
PROFILE_DIR = Path(_profile).expanduser() if _profile else ROOT / "browser-data"
if not PROFILE_DIR.is_absolute():
    PROFILE_DIR = (ROOT / PROFILE_DIR).resolve()

TELEGRAM_WEB_URL = os.environ.get("TELEGRAM_WEB_URL", "https://web.telegram.org/k/").strip()

# Tuỳ chọn: device thanhtai.io (cần khi giải mã link junb/thanhtai qua browser)
DEVICE_ID = os.environ.get("THANHTAI_DEVICE_ID", "").strip()
# Device hex junb đã được whitelist (tham số d= của l.junb.io.vn/verify)
# Nhiều device: JUNB_DEVICE_IDS=hex1,hex2,hex3 (chia tải tránh 429)
JUNB_DEVICE_ID = os.environ.get("JUNB_DEVICE_ID", "").strip()
_junb_extra = os.environ.get("JUNB_DEVICE_IDS", "").strip()
JUNB_DEVICE_IDS: list[str] = []
for _part in (JUNB_DEVICE_ID, *_junb_extra.replace(";", ",").split(",")):
    _tok = _part.strip()
    if _tok and _tok not in JUNB_DEVICE_IDS:
        JUNB_DEVICE_IDS.append(_tok)
# Giải mã trực tiếp qua HTTP (nhanh, song song); Playwright chỉ là dự phòng
FEED_HTTP_DECODE = os.environ.get("FEED_HTTP_DECODE", "true").lower() in ("1", "true", "yes")
FEED_BROWSER_FALLBACK = os.environ.get("FEED_BROWSER_FALLBACK", "false").lower() in (
    "1",
    "true",
    "yes",
)
FEED_DECODE_WORKERS = int(os.environ.get("FEED_DECODE_WORKERS", "48"))
# junb verify bị giới hạn theo device + IP → 1 hàng chung, gọi thưa
JUNB_MIN_GAP_S = float(os.environ.get("JUNB_MIN_GAP_S", "6.0"))
JUNB_MAX_WAIT_S = float(os.environ.get("JUNB_MAX_WAIT_S", "30"))
# Chỉ giữ vài link mới nhất chờ gọi; link cũ hơn bị bỏ
JUNB_QUEUE_MAX = int(os.environ.get("JUNB_QUEUE_MAX", "2"))
# Link còn hạn ít hơn ngần này thì không tốn request junb
JUNB_MIN_REMAIN_S = float(os.environ.get("JUNB_MIN_REMAIN_S", "20"))

VIEWPORT = {"width": 1440, "height": 960}
LOCALE = "vi-VN"
TIMEZONE_ID = "Asia/Bangkok"

DEEPLINK_TIMEOUT_MS = int(os.environ.get("DEEPLINK_TIMEOUT_MS", "25000"))

# Telethon — peer id (web hash -3431776950 → -1003431776950)
TELEGRAM_CHAT_HASH = os.environ.get("TELEGRAM_CHAT_HASH", "-3431776950").strip()
# moon_2, Tung_Lam + 4 nhóm web.telegram.org/k/#-…
TELEGRAM_CHAT_IDS = os.environ.get(
    "TELEGRAM_CHAT_IDS",
    ",".join(
        [
            "-1003431776950",  # Moon_2  #-3431776950
            "-1004298855488",  # Tung_Lam #-4298855488
            "-1003891336100",  # #-3891336100
            "-1003981109443",  # #-3981109443
            "-1003792359700",  # #-3792359700
            "-1003893832981",  # #-3893832981
        ]
    ),
).strip()

# Session Telethon (trên server thường dùng chung app1 — chỉ 1 process/session)
_default_session = os.environ.get(
    "TELEGRAM_CLIENT_SESSION",
    str(ROOT / "data" / "telegram_client.session"),
)
TELEGRAM_SESSION_PATH = Path(_default_session).expanduser()
if not TELEGRAM_SESSION_PATH.is_absolute():
    TELEGRAM_SESSION_PATH = (ROOT / TELEGRAM_SESSION_PATH).resolve()

TELEGRAM_WEB_URL = os.environ.get(
    "TELEGRAM_WEB_URL",
    f"https://web.telegram.org/k/#{TELEGRAM_CHAT_HASH}",
).strip()

FEED_HOST = os.environ.get("FEED_HOST", "127.0.0.1").strip()
FEED_PORT = int(os.environ.get("FEED_PORT", "8796"))
FEED_POLL_SECONDS = float(os.environ.get("FEED_POLL_SECONDS", "1.0"))
FEED_MESSAGE_LIMIT = int(os.environ.get("FEED_MESSAGE_LIMIT", "40"))
FEED_SKIP_EXISTING_ON_START = os.environ.get("FEED_SKIP_EXISTING_ON_START", "true").lower() in (
    "1",
    "true",
    "yes",
)
FEED_HEADLESS = os.environ.get("FEED_HEADLESS", "true").lower() in ("1", "true", "yes")
FEED_HISTORY_MAX = int(os.environ.get("FEED_HISTORY_MAX", "200"))

# Chỉ gọi API/Playwright giải mã link trong tin mới (junb /l/ hết hạn rất nhanh)
FEED_DECODE_MAX_AGE_SECONDS = float(os.environ.get("FEED_DECODE_MAX_AGE_SECONDS", "120"))
# WebSocket: không dump history khi mở trang (tránh payload lớn + treo UI)
FEED_WS_SEND_HISTORY = os.environ.get("FEED_WS_SEND_HISTORY", "false").lower() in (
    "1",
    "true",
    "yes",
)

# API giải mã trên VPS (fallback nhanh hơn Playwright local)
DEEPLINK_API_BASE_URL = os.environ.get("DEEPLINK_API_BASE_URL", "http://160.30.19.215:8792").strip()
# Decode trên Mac (profile + IP nhà) — VPS tunnel: ssh -R 8793:127.0.0.1:8793
MAC_DECODE_URL = os.environ.get("MAC_DECODE_URL", "").strip().rstrip("/")

# Đăng nhập JWT cho feed UI / WebSocket
FEED_AUTH_USER = os.environ.get("FEED_AUTH_USER", "admin").strip() or "admin"
FEED_AUTH_PASSWORD = os.environ.get("FEED_AUTH_PASSWORD", "").strip()
FEED_JWT_SECRET = os.environ.get("FEED_JWT_SECRET", "").strip()
FEED_JWT_TTL = int(os.environ.get("FEED_JWT_TTL", str(7 * 24 * 3600)))
