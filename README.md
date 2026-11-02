# thaihung-v3

Profile **Chromium (Playwright)** persistent để:

1. **Đăng nhập Telegram Web** — session lưu trong `browser-data/`
2. **Giải mã deeplink TikTok** (`snssdk1180://live?room_id=...`) từ link junb / thanhtai qua trình duyệt (bắt request sau khi mở trang + bấm **MỞ LINK**)

## Cài đặt

Cần **Python 3.11** (Playwright 1.46 không build trên 3.14).

```bash
cd thaihung-v3
bash setup.sh
source .venv/bin/activate
```

## Bước 1 — Login Telegram (một lần)

```bash
python login_telegram.py
```

- Đăng nhập QR / SĐT trên https://web.telegram.org/k/
- **Cmd+Q** đóng Chromium → cookie/session lưu vào `browser-data/`

## Bước 2 — Giải mã deeplink

```bash
python decode_deeplink.py 'https://i.junb.io.vn/i/?b7YVmORSncRD4'
# hoặc
python decode_deeplink.py 'https://thanhtai.io/r/xxxx' --headed
```

In ra dòng dạng: `snssdk1180://live?room_id=7123456789012345678`

## Device thanhtai (nếu trang báo chưa cấp quyền)

Set cookie device trước khi giải mã (cùng profile hoặc env):

```bash
export THANHTAI_DEVICE_ID='device_xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'
python decode_deeplink.py 'https://thanhtai.io/r/...'
```

Hoặc mở https://thanhtai.io/device trong `login_telegram.py` / `open_browser.py` và đăng ký device trong cùng profile.

## Script khác

| Lệnh | Mục đích |
|------|----------|
| `python open_browser.py` | Mở Telegram Web, dùng tay |
| `python decode_deeplink.py URL` | Headless giải mã |
| `python decode_deeplink.py URL --headed` | Xem Chrome giải mã |

## Feed WebSocket + UI (đọc nhóm Telegram Web)

Đọc nhóm mặc định `#-3431776950`, giải mã link junb → deeplink TikTok, đẩy qua WebSocket.

```bash
source .venv/bin/activate
pip install -q aiohttp   # nếu chưa cài sau setup.sh
python feed_server.py
```

Mở trình duyệt: **http://127.0.0.1:8796/**

Biến môi trường:

```bash
export TELEGRAM_CHAT_URL='https://web.telegram.org/k/#-3431776950'
export FEED_HEADLESS=false   # debug Playwright
python feed_server.py
```

Cần đã login profile (`login_telegram.py`) trước.

## Lưu ý

- **Không commit** thư mục `browser-data/` (chứa session Telegram).
- Giải mã browser **chậm hơn** API offline trong `profile_playwright` / VPS — dùng khi cần flow đầy đủ qua trang xác minh.
- Profile này **tách** với `profile_playwright/browser-data` (repo chính).
