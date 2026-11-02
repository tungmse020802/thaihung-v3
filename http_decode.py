"""Giải mã junb /l/ và thanhtai /r/ bằng HTTP trực tiếp (device đã whitelist).

junb:     GET l.junb.io.vn/verify?t=<hash>&d=<device hex>&s=open_link_l → {"room_id": ...}
thanhtai: GET thanhtai.io/r/<id> với cookie device_id → HTML chứa snssdk1180://live?room_id=
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from concurrent.futures import Future, TimeoutError as FutureTimeout
from typing import Optional

from settings import (
    DEVICE_ID,
    JUNB_DEVICE_IDS,
    JUNB_MAX_WAIT_S,
    JUNB_MIN_GAP_S,
    JUNB_MIN_REMAIN_S,
    JUNB_QUEUE_MAX,
)

logger = logging.getLogger(__name__)

DEEPLINK_PREFIX = "snssdk1180://live?room_id="
ROOM_ID_RE = re.compile(r"room_id=(\d{15,22})(?:\D|$)")
JSON_ROOM_RE = re.compile(r"^\d{15,22}$")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
TIMEOUT_S = 8.0
CACHE_TTL_S = 30 * 60
CACHE_MAX = 5000
# junb giới hạn theo device + IP: burst → 429 kéo dài, nên backoff tăng dần
JUNB_BACKOFF_START_S = 60.0
JUNB_BACKOFF_MAX_S = 900.0

_cache: "OrderedDict[str, tuple[float, str]]" = OrderedDict()
_cache_lock = threading.Lock()


class DecodeDenied(Exception):
    """Server từ chối device (chưa whitelist) — không nên thử lại bằng browser."""


class JunbRateLimited(Exception):
    pass


def _cache_get(url: str) -> Optional[str]:
    with _cache_lock:
        hit = _cache.get(url)
        if not hit:
            return None
        ts, value = hit
        if time.monotonic() - ts > CACHE_TTL_S:
            _cache.pop(url, None)
            return None
        _cache.move_to_end(url)
        return value


def _cache_put(url: str, value: str) -> None:
    with _cache_lock:
        _cache[url] = (time.monotonic(), value)
        _cache.move_to_end(url)
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)


def _get(url: str, headers: dict[str, str]) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **headers})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return resp.status, resp.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read(2000).decode("utf-8", "replace")
        except Exception:
            pass
        return exc.code, body


def _junb_hash(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return (parsed.fragment or "").strip()


def _verify_junb(url: str, device_id: str) -> str:
    token = _junb_hash(url)
    if not token:
        raise ValueError(f"junb thiếu hash: {url}")
    q = urllib.parse.urlencode({"t": token, "d": device_id, "s": "open_link_l"})
    status, body = _get(
        f"https://l.junb.io.vn/verify?{q}",
        {"Origin": "https://i.junb.io.vn", "Referer": "https://i.junb.io.vn/", "Accept": "application/json"},
    )
    if status == 429:
        raise JunbRateLimited(f"junb verify 429 body={body[:80]}")
    if status in (401, 403):
        raise DecodeDenied(f"junb verify {status} {body[:120]}")
    if status != 200:
        raise ValueError(f"junb verify {status} {body[:120]}")
    try:
        room_id = str(json.loads(body).get("room_id") or "")
    except Exception as exc:
        raise ValueError(f"junb verify JSON lỗi: {body[:120]}") from exc
    if not JSON_ROOM_RE.match(room_id):
        raise ValueError(f"junb room_id không hợp lệ: {body[:120]}")
    return f"{DEEPLINK_PREFIX}{room_id}"


def _settle(fut: Future, *, result: Optional[str] = None, exc: Optional[BaseException] = None) -> None:
    try:
        if exc is not None:
            fut.set_exception(exc)
        else:
            fut.set_result(result)
    except Exception:
        pass


class JunbSkipped(Exception):
    """Không gọi junb (hạn chế tần suất / link sắp hết hạn) — không phải lỗi."""


class _JunbLane:
    """Một hàng duy nhất cho cả IP: 1 verify / JUNB_MIN_GAP_S, xoay vòng device.

    Hàng chỉ giữ JUNB_QUEUE_MAX link mới nhất; link còn hạn < JUNB_MIN_REMAIN_S bị bỏ.
    """

    def __init__(self, device_ids: list[str]) -> None:
        self.device_ids = device_ids
        self._rr = 0
        self._cv = threading.Condition()
        # (deadline epoch | None, url, future)
        self._stack: list[tuple[Optional[float], str, Future]] = []
        self._pending: dict[str, Future] = {}
        self._next_at = 0.0
        self._backoff = 0.0
        self.stats = {"sent": 0, "ok": 0, "429": 0, "skip_expire": 0, "skip_full": 0, "skip_pause": 0}
        threading.Thread(target=self._run, name="junb-lane", daemon=True).start()

    @staticmethod
    def _too_late(deadline: Optional[float], now_epoch: float) -> bool:
        return deadline is not None and deadline - now_epoch < JUNB_MIN_REMAIN_S

    def submit(self, url: str, deadline: Optional[float]) -> Future:
        with self._cv:
            fut = self._pending.get(url)
            if fut is not None:
                return fut
            fut = Future()
            paused = self._next_at - time.monotonic()
            if self._backoff and paused > 0:
                self.stats["skip_pause"] += 1
                _settle(fut, exc=JunbSkipped(f"junb tạm dừng sau 429 — còn {paused:.0f}s"))
                return fut
            if self._too_late(deadline, time.time()):
                self.stats["skip_expire"] += 1
                _settle(fut, exc=JunbSkipped("link sắp hết hạn — không gọi junb"))
                return fut
            self._pending[url] = fut
            self._stack.append((deadline, url, fut))
            while len(self._stack) > JUNB_QUEUE_MAX:
                _d, old_url, old_fut = self._stack.pop(0)
                self._pending.pop(old_url, None)
                self.stats["skip_full"] += 1
                _settle(old_fut, exc=JunbSkipped("junb hạn chế tần suất — bỏ link cũ hơn"))
            self._cv.notify()
            return fut

    def _drop_dead(self) -> None:
        now_epoch = time.time()
        keep = []
        for item in self._stack:
            deadline, url, fut = item
            if fut.done():
                self._pending.pop(url, None)
            elif self._too_late(deadline, now_epoch):
                self._pending.pop(url, None)
                self.stats["skip_expire"] += 1
                _settle(fut, exc=JunbSkipped("link sắp hết hạn — không gọi junb"))
            else:
                keep.append(item)
        self._stack = keep

    def _pop(self) -> tuple[str, Future]:
        with self._cv:
            while True:
                self._drop_dead()
                wait = self._next_at - time.monotonic()
                if self._stack and wait <= 0:
                    _d, url, fut = self._stack.pop()
                    return url, fut
                self._cv.wait(timeout=min(max(wait, 0.05), 1.0) if self._stack else 1.0)

    def _run(self) -> None:
        while True:
            url, fut = self._pop()
            device_id = self.device_ids[self._rr % len(self.device_ids)]
            self._rr += 1
            self.stats["sent"] += 1
            try:
                result = _verify_junb(url, device_id)
                self._backoff = 0.0
                self._next_at = time.monotonic() + JUNB_MIN_GAP_S
                self.stats["ok"] += 1
                _settle(fut, result=result)
            except JunbRateLimited as exc:
                self.stats["429"] += 1
                self._backoff = min(max(self._backoff * 2, JUNB_BACKOFF_START_S), JUNB_BACKOFF_MAX_S)
                self._next_at = time.monotonic() + self._backoff
                logger.warning("junb 429 — tạm dừng %.0fs, bỏ hàng đợi (%s)", self._backoff, exc)
                _settle(fut, exc=exc)
                with self._cv:
                    for _d, u, f in self._stack:
                        self._pending.pop(u, None)
                        _settle(f, exc=JunbSkipped("junb tạm dừng sau 429"))
                    self._stack = []
            except Exception as exc:
                self._next_at = time.monotonic() + JUNB_MIN_GAP_S
                _settle(fut, exc=exc)
            finally:
                with self._cv:
                    self._pending.pop(url, None)
            if self.stats["sent"] % 20 == 0:
                logger.info("junb stats %s", self.stats)


_junb_lane: Optional[_JunbLane] = None
_junb_lane_lock = threading.Lock()


def _decode_junb(url: str, deadline: Optional[float]) -> str:
    global _junb_lane
    if not JUNB_DEVICE_IDS:
        raise DecodeDenied("thiếu JUNB_DEVICE_ID / JUNB_DEVICE_IDS")
    with _junb_lane_lock:
        if _junb_lane is None:
            _junb_lane = _JunbLane(JUNB_DEVICE_IDS)
            logger.info(
                "junb lane: gap=%.1fs queue_max=%s min_remain=%.0fs devices=%s",
                JUNB_MIN_GAP_S, JUNB_QUEUE_MAX, JUNB_MIN_REMAIN_S, [d[:8] for d in JUNB_DEVICE_IDS],
            )
    fut = _junb_lane.submit(url, deadline)
    try:
        return fut.result(timeout=JUNB_MAX_WAIT_S + TIMEOUT_S + 2)
    except FutureTimeout:
        fut.cancel()
        raise JunbSkipped("junb chờ quá lâu")


def _decode_thanhtai(url: str) -> str:
    if not DEVICE_ID:
        raise DecodeDenied("thiếu THANHTAI_DEVICE_ID")
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            status, body = _get(
                url, {"Cookie": f"device_id={DEVICE_ID}", "Referer": "https://thanhtai.io/"}
            )
        except Exception as exc:
            last_err = exc
            time.sleep(0.4 * (attempt + 1))
            continue
        match = ROOM_ID_RE.search(body)
        if status == 200 and match:
            return f"{DEEPLINK_PREFIX}{match.group(1)}"
        if "<title>Denied</title>" in body or status in (401, 403):
            raise DecodeDenied(f"thanhtai denied ({status})")
        last_err = ValueError(f"thanhtai {status} không có room_id")
        time.sleep(0.3)
    raise last_err or ValueError("thanhtai fail")


def supports(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if "junb.io.vn" in host and "/l/" in path:
        return True
    return "thanhtai.io" in host and "/r/" in path


def decode(url: str, deadline: Optional[float] = None) -> str:
    """Trả về snssdk1180://live?room_id=… hoặc raise. `deadline` = epoch link hết hạn."""
    cached = _cache_get(url)
    if cached:
        return cached
    host = (urllib.parse.urlparse(url).netloc or "").lower()
    started = time.monotonic()
    result = _decode_junb(url, deadline) if "junb.io.vn" in host else _decode_thanhtai(url)
    logger.info("http decode %.2fs %s → %s", time.monotonic() - started, url[:70], result)
    _cache_put(url, result)
    return result
