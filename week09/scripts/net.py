# week09/scripts/net.py — week06/scripts/crawl_2027_detail.py 네트워크 계층 이식
import random, threading, time
import requests

DELAY_RANGE = (0.3, 0.8)
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
}
CIRCUIT_THRESHOLD = 8
_BLOCK = threading.Event()
_FAIL_LOCK = threading.Lock()
_CONSEC_FAIL = [0]

def _retry_after(r):
    v = r.headers.get("Retry-After")
    try:
        return float(v) if v else None
    except ValueError:
        return None

def _note_success():
    with _FAIL_LOCK:
        _CONSEC_FAIL[0] = 0

def _note_failure():
    with _FAIL_LOCK:
        _CONSEC_FAIL[0] += 1
        if _CONSEC_FAIL[0] >= CIRCUIT_THRESHOLD and not _BLOCK.is_set():
            _BLOCK.set()
            print(f"\n🛑 연속 실패 {_CONSEC_FAIL[0]}회 — 차단 의심. 신규 요청 중단(서킷브레이커).", flush=True)

def _request(method, url, **kw):
    if _BLOCK.is_set():
        raise RuntimeError("서킷브레이커 작동 중 — 크롤 중단(차단 의심)")
    kw.setdefault("headers", {})
    kw["headers"] = {**BROWSER_HEADERS, "Connection": "close", **kw["headers"]}
    kw.setdefault("timeout", (5, 15))
    last = None
    for attempt in range(3):
        try:
            time.sleep(random.uniform(*DELAY_RANGE))
            r = requests.request(method, url, **kw)
            if r.status_code == 429:
                time.sleep(min(_retry_after(r) or 5.0 * (attempt + 1), 60))
                last = requests.HTTPError("429 Too Many Requests"); continue
            r.raise_for_status()
            _note_success(); return r
        except requests.RequestException as e:
            last = e; time.sleep(1.5 * (attempt + 1))
    _note_failure(); raise last
