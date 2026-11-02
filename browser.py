import time

from playwright.sync_api import BrowserContext, Page, Playwright

from settings import DEVICE_ID, LOCALE, PROFILE_DIR, TIMEZONE_ID, VIEWPORT


def launch_context(
    playwright: Playwright,
    *,
    headless: bool = False,
    inject_device: bool = True,
) -> BrowserContext:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        viewport=VIEWPORT,
        locale=LOCALE,
        timezone_id=TIMEZONE_ID,
        ignore_default_args=["--enable-automation"],
        args=["--disable-blink-features=AutomationControlled"],
    )

    if inject_device and DEVICE_ID:
        ensure_device_cookie(context)

    return context


def ensure_device_cookie(context: BrowserContext, page: Page | None = None) -> None:
    """Inject device_id cho thanhtai.io (nếu THANHTAI_DEVICE_ID được set)."""
    if not DEVICE_ID:
        return

    if page is None:
        page = context.pages[0] if context.pages else context.new_page()

    device_cookie = {
        "name": "device_id",
        "value": DEVICE_ID,
        "domain": "thanhtai.io",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "sameSite": "Lax",
        "expires": int(time.time()) + 365 * 24 * 3600,
    }
    context.add_cookies([device_cookie])

    client = context.new_cdp_session(page)
    client.send("Network.enable")
    client.send("Network.setCookie", device_cookie)

