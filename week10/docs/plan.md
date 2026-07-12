# 전형정보 크롤링 초안 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 어디가 전형정보(전형일정·방법 / 전형요소)를 샘플 5개 대학 × 모든 전형으로 크롤해 첨부 `가천대.xlsx` 포맷(탭2개)으로 raw 출력한다.

**Architecture:** week06 크롤러 인프라(retry+서킷브레이커+지연+resume+병렬)를 `net.py`로 이식 후 재사용. 대학→전형 열거(`admssUnivDetailLstAjax.do` 프래그먼트)→전형별 2엔드포인트 fetch→파서(순수함수 HTML→dict)→openpyxl 다단헤더 워크북(대학별 + 통합). 파서는 Phase 0 spike가 저장한 실제 HTML 픽스처에 대해 TDD.

**Tech Stack:** Python 3.13(week05 .venv), requests, BeautifulSoup4, openpyxl, pandas, pytest.

---

## 파일 구조

| 파일 | 책임 |
|---|---|
| `week10/scripts/net.py` | 네트워크 계층: `_request`(retry+서킷브레이커+지연), 브라우저 헤더 (week06 이식) |
| `week10/scripts/enumerate_admissions.py` | 대학 → 전형 목록+파라미터 (LstAjax 프래그먼트 파싱) |
| `week10/scripts/parse_schedule.py` | 전형일정및방법 HTML → 고정 23열 dict |
| `week10/scripts/parse_element.py` | 전형요소 HTML → raw 평면화 dict (동적 컬럼) |
| `week10/scripts/write_excel.py` | dict 리스트 → 2탭 워크북(다단헤더), 대학별 + 통합 |
| `week10/scripts/crawl_admission.py` | 메인: 열거·병렬·resume·리포트 오케스트레이션 |
| `week10/tests/fixtures/` | spike가 저장한 실제 HTML + 기대 dict |
| `week10/tests/test_*.py` | 파서 단위 테스트 |

각 파서는 `parse(html: str) -> list[dict]` 순수 함수 → 네트워크 없이 픽스처로 테스트.

---

## Task 0: Phase 0 Spike — 열거·전형요소 구조 확정 (본 구현 전 필수)

설계 §8. **이 task의 산출물이 Task 2~4의 정확한 셀렉터/파라미터를 결정.**

**Files:**
- Create: `week10/tests/fixtures/` (실제 HTML 저장)
- Modify: `week10/docs/design.md` (§3/§8에 spike 결과 확정 기록)

- [ ] **Step 1: 전형 열거 폼 필드셋 reverse-engineer**

가천대(0000063) 전형정보 페이지(`admssUnivView.do?menuId=PCPRCINF2000&unvCd=0000063&searchSyr=2027`)의
`#frm` 폼 필드를 BeautifulSoup으로 추출:
```bash
cd week10 && ../../week06 ... # week05 .venv 사용
../week05/.venv/bin/python -c "
import requests, re
from bs4 import BeautifulSoup
UA='Mozilla/5.0 ... Chrome/138.0.0.0 Safari/537.36'
h=requests.get('https://www.adiga.kr/ucp/prc/uni/admssUnivView.do',
  params={'menuId':'PCPRCINF2000','unvCd':'0000063','searchSyr':'2027'},
  headers={'User-Agent':UA}).text
s=BeautifulSoup(h,'html.parser')
frm=s.find(id='frm')
print([(i.get('name'),i.get('id'),i.get('value')) for i in frm.find_all(['input','select'])])
"
```
`#frm` 필드 목록 확보. `admssUnivDetailLstAjax.do`에 이 필드를 POST(serialize)했을 때
200 + 전형행 프래그먼트가 오는 파라미터 조합을 찾는다(빈 값 채워가며).

- [ ] **Step 2: 열거 프래그먼트 저장 + 전형 파라미터 추출 경로 확정**

성공한 LstAjax 응답 HTML을 `week10/tests/fixtures/enum_가천대.html`로 저장.
프래그먼트 안에서 각 전형의 `ruCd·ruSn·comScsbjtCd·slcnTypeCd·slcnCd·lclsfAftCd·slcnGroupCd·rcmtMmntCd`가
어느 속성/onclick에 있는지 기록(정규식 패턴 메모).

- [ ] **Step 3: 전형요소 실제 데이터 로드 방식 확정**

가천대 논술 전형요소 URL(설계 예시2)을 GET했을 때 핵심 데이터(학생부 반영 등)가
응답에 있는지 / 별도 AJAX(`admssUnivDetailElement` 또는 다른 `*Ajax.do`)가 필요한지 확인.
브라우저 devtools가 필요하면 `mcp__Claude_in_Chrome` 또는 `computer-use`로 네트워크 캡처.
실제 데이터 담긴 응답 HTML을 `week10/tests/fixtures/element_가천대학생부교과.html`로 저장.

- [ ] **Step 4: 전형일정및방법 HTML 픽스처 저장**

가천대 논술 `admssUnivDetail.do`(설계 예시2) 응답을 `week10/tests/fixtures/schedule_가천대논술.html`로 저장.
탭1 23열에 매핑되는 표/셀 위치 확인.

- [ ] **Step 5: design.md에 결과 반영 + 폴백 판정**

§3/§8에 확정 사항 기록: 열거 파라미터셋, 전형요소 로드 방식.
전형요소 데이터 확보 실패 시 → §8 폴백(탭1만) 채택을 design.md에 명시하고, Task 4를 건너뛴다.

- [ ] **Step 6: Commit**

```bash
git add week10/tests/fixtures week10/docs/design.md
git commit -m "spike(w09): 전형 열거 파라미터 + 전형요소 구조 확정, HTML 픽스처 저장"
```

> ⚠️ Task 1~6의 코드 중 셀렉터/정규식은 본 spike 결과로 확정한다. 아래 코드는 정찰에서 확인된
> 구조 기준 초안이며, 실제 픽스처에 맞춰 테스트가 통과하도록 조정한다.

---

## Task 1: net.py — 네트워크 계층 이식

**Files:**
- Create: `week10/scripts/net.py`
- Test: `week10/tests/test_net.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# week10/tests/test_net.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import net

def test_circuit_breaker_trips_then_fast_fails():
    net._CONSEC_FAIL[0] = 0
    net._BLOCK.clear()
    for _ in range(net.CIRCUIT_THRESHOLD):
        net._note_failure()
    assert net._BLOCK.is_set()
    import pytest
    with pytest.raises(RuntimeError):
        net._request("GET", "https://example.invalid")

def test_success_resets_counter():
    net._BLOCK.clear(); net._CONSEC_FAIL[0] = 5
    net._note_success()
    assert net._CONSEC_FAIL[0] == 0

def test_retry_after_parses_seconds():
    class R: headers = {"Retry-After": "12"}
    assert net._retry_after(R()) == 12.0
    class R2: headers = {}
    assert net._retry_after(R2()) is None
```

- [ ] **Step 2: 실패 확인**

Run: `cd week10 && ../../../week05/.venv/bin/python -m pytest tests/test_net.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'net'`

- [ ] **Step 3: net.py 구현 (week06에서 이식)**

`week06/scripts/crawl_2027_detail.py`의 네트워크 블록을 그대로 옮긴다:
`BROWSER_HEADERS`, `DELAY_RANGE`, `CIRCUIT_THRESHOLD`, `_BLOCK`, `_FAIL_LOCK`, `_CONSEC_FAIL`,
`_retry_after`, `_note_success`, `_note_failure`, `_request`. 상단에 `import random, time, threading, requests`.

```python
# week10/scripts/net.py — week06/scripts/crawl_2027_detail.py 네트워크 계층 이식
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
```

- [ ] **Step 4: 통과 확인**

Run: `cd week10 && ../../../week05/.venv/bin/python -m pytest tests/test_net.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add week10/scripts/net.py week10/tests/test_net.py
git commit -m "feat(w09): net.py — week06 네트워크 계층 이식 (retry+서킷브레이커)"
```

---

## Task 2: enumerate_admissions.py — 전형 목록 파싱

**Files:**
- Create: `week10/scripts/enumerate_admissions.py`
- Test: `week10/tests/test_enumerate.py`
- 의존: `week10/tests/fixtures/enum_가천대.html` (Task 0 산출)

- [ ] **Step 1: 실패 테스트 작성**

spike 확정: 전형행은 `a.selectUnivComScsbjtCd`, 파라미터는 `onclick="fnDetailPage(...)"` 9인자
(순서 = `unvCd, comScsbjtCd, slcnGroupCd, rcmtMmntCd, ruCd, ruSn, lclsfAftCd, slcnTypeCd, slcnCd`).
픽스처 `enum_가천대.html` = 전형 16개, 첫 행 ruCd=0247247·ruSn=111786·slcnTypeCd=04·slcnCd=01.
```python
# week10/tests/test_enumerate.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import enumerate_admissions as E

FIX = pathlib.Path(__file__).parent / "fixtures" / "enum_가천대.html"

def test_parses_admission_rows():
    rows = E.parse_fragment(FIX.read_text(encoding="utf-8"))
    assert len(rows) == 16
    r = rows[0]
    for k in E.PARAM_KEYS:
        assert k in r and r[k]          # 9개 파라미터 모두 채워짐
    assert r["전형명"]                   # 전형명 존재
    # 첫 전형행이 spike 검증값과 일치
    assert r["ruCd"] == "0247247" and r["ruSn"] == "111786"
    assert r["slcnTypeCd"] == "04" and r["slcnCd"] == "01"
```

- [ ] **Step 2: 실패 확인**

Run: `cd week10 && ../../../week05/.venv/bin/python -m pytest tests/test_enumerate.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현 (spike 확정 — 3단계 열거)**

spike 확정: comScsbjtCd가 없으면 LstAjax가 `error 041`. 따라서 **3단계**:
① `admssUnivView.do` GET(쿠키+`#frm` 폼) → ② `admssUnivAjax.do` POST(`#frm`+`searchUnvCode`)
로 `li.opnfldClass`의 `comscsbjtcd` 속성 획득 → ③ `admssUnivDetailLstAjax.do` POST(`#frm`+unvCd+comScsbjtCd).
세션 쿠키 유지를 위해 `requests.Session` 사용(단 헤더·지연은 net의 정책을 따른다).

```python
# week10/scripts/enumerate_admissions.py
import re, html as _html
from bs4 import BeautifulSoup
import net

VIEW_URL = "https://www.adiga.kr/ucp/prc/uni/admssUnivView.do"
UNIV_AJAX_URL = "https://www.adiga.kr/ucp/prc/uni/admssUnivAjax.do"
LIST_URL = "https://www.adiga.kr/ucp/prc/uni/admssUnivDetailLstAjax.do"
# fnDetailPage 인자 순서 = 그대로 키 순서
PARAM_KEYS = ("unvCd", "comScsbjtCd", "slcnGroupCd", "rcmtMmntCd",
              "ruCd", "ruSn", "lclsfAftCd", "slcnTypeCd", "slcnCd")

def _form_fields(html: str) -> dict:
    """admssUnivView 페이지 #frm(id=frm) hidden/select 필드 → dict."""
    soup = BeautifulSoup(html, "html.parser")
    frm = soup.find(id="frm")
    out = {}
    if frm:
        for el in frm.find_all(["input", "select"]):
            name = el.get("name")
            if name:
                out[name] = el.get("value") or ""
    return out

def parse_fragment(html: str) -> list[dict]:
    """LstAjax 프래그먼트 → 전형 행 dict 목록.
    전형명 = a.selectUnivComScsbjtCd 텍스트, 파라미터 = onclick fnDetailPage 9인자."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for a in soup.select("a.selectUnivComScsbjtCd"):
        oc = a.get("onclick", "")
        m = re.search(r"fnDetailPage\(([^)]*)\)", _html.unescape(oc))
        if not m:
            continue
        args = [t.strip().strip("'\"").strip() for t in m.group(1).split(",")]
        if len(args) < len(PARAM_KEYS):
            continue
        rec = {k: args[i] for i, k in enumerate(PARAM_KEYS)}
        rec["전형명"] = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        rows.append(rec)
    return rows

def fetch(unv_cd: str, syr: str = "2027") -> list[dict]:
    """대학 → 전형 목록 (3단계 AJAX). net._request로 헤더·지연·브레이커 적용."""
    import requests
    sess = requests.Session()
    # ① view GET (쿠키 + 폼)
    rv = net._request("GET", VIEW_URL,
                      params={"menuId": "PCPRCINF2000", "unvCd": unv_cd, "searchSyr": syr},
                      session=sess)
    form = _form_fields(rv.text)
    form.update({"searchSyr": syr, "unvCd": unv_cd})
    hdr = {"X-Requested-With": "XMLHttpRequest",
           "Referer": rv.url, "Origin": "https://www.adiga.kr"}
    # ② UnivAjax POST → comScsbjtCd
    ra = net._request("POST", UNIV_AJAX_URL, data={**form, "searchUnvCode": unv_cd},
                      headers=hdr, session=sess)
    li = BeautifulSoup(ra.text, "html.parser").select_one("li.opnfldClass[comscsbjtcd]")
    if not li:
        return []
    com = li.get("comscsbjtcd")
    # ③ LstAjax POST → 전형행 프래그먼트
    rl = net._request("POST", LIST_URL, data={**form, "unvCd": unv_cd, "comScsbjtCd": com},
                      headers=hdr, session=sess)
    return parse_fragment(rl.text)
```

> `net._request`에 `session=` 인자를 추가해야 한다(쿠키 유지용). Task 1 net.py의 `_request`를
> `sess = kw.pop("session", requests); ... sess.request(...)` 형태로 소폭 확장
> (session 미지정 시 모듈 `requests` 사용 = 기존 동작 유지). 이 확장은 Task 2에서 함께 처리하고
> test_net.py가 여전히 통과하는지 확인한다.

- [ ] **Step 4: 통과 확인**

Run: `/Users/channy/Documents/workspaces/ai/ai-agent-study/week05/.venv/bin/python -m pytest week10/tests/test_enumerate.py week10/tests/test_net.py -v`
Expected: PASS. parse_fragment는 픽스처(네트워크 없음)로 검증. fetch는 단위테스트 대상 아님(Task 7 e2e에서 실검증).

- [ ] **Step 5: Commit**

```bash
git add week10/scripts/enumerate_admissions.py week10/tests/test_enumerate.py
git commit -m "feat(w09): 전형 목록 열거 (LstAjax 프래그먼트 파싱)"
```

---

## Task 3: parse_schedule.py — 전형일정및방법 → 고정 23열

**Files:**
- Create: `week10/scripts/parse_schedule.py`
- Test: `week10/tests/test_schedule.py`
- 의존: `week10/tests/fixtures/schedule_가천대논술.html`

탭1 스키마(설계 §5, 샘플 23열):
```
대학명, 전형명, 모집단위명,
원서접수_인터넷, 원서접수_현장,
대학별고사_논술등필답, 대학별고사_면접구술, 대학별고사_실기,
합격자발표일,
선발모형, 선발방법, 선발비율,
반영_학생부, 반영_수능, 반영_면접, 반영_논술, 반영_적성, 반영_1단계성적, 반영_실기, 반영_서류, 반영_기타,
기타내용
```

- [ ] **Step 1: 실패 테스트 작성**

```python
# week10/tests/test_schedule.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import parse_schedule as S

FIX = pathlib.Path(__file__).parent / "fixtures" / "schedule_가천대논술.html"

def test_schedule_has_fixed_columns():
    recs = S.parse(FIX.read_text(encoding="utf-8"))
    assert len(recs) >= 1
    assert set(S.COLUMNS).issubset(recs[0].keys())  # 23열 전부 존재
    # 원서접수는 날짜 범위 텍스트를 담는다(샘플: 2026-09-..)
    assert any(r["원서접수_인터넷"] for r in recs)
```

- [ ] **Step 2: 실패 확인**

Run: `cd week10 && ../../../week05/.venv/bin/python -m pytest tests/test_schedule.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현 (열 키워드 매핑 — 위치 하드코딩 금지)**

```python
# week10/scripts/parse_schedule.py
from bs4 import BeautifulSoup

COLUMNS = ["대학명", "전형명", "모집단위명",
           "원서접수_인터넷", "원서접수_현장",
           "대학별고사_논술등필답", "대학별고사_면접구술", "대학별고사_실기",
           "합격자발표일", "선발모형", "선발방법", "선발비율",
           "반영_학생부", "반영_수능", "반영_면접", "반영_논술", "반영_적성",
           "반영_1단계성적", "반영_실기", "반영_서류", "반영_기타", "기타내용"]

def _empty() -> dict:
    return {c: "" for c in COLUMNS}

def parse(html: str, 대학명: str = "", 전형명: str = "") -> list[dict]:
    """전형일정및방법 페이지 → 고정 23열 dict 목록(모집단위 1개=1행).
    표 헤더 텍스트 키워드로 셀을 매핑(어디가 표 변동 대비, 위치 비의존)."""
    soup = BeautifulSoup(html, "html.parser")
    # Task 0 픽스처로 모집단위 행 컨테이너·헤더 매핑 확정.
    # 구현 골격: 각 모집단위 표/행을 순회 → COLUMNS 키워드와 헤더 매칭 → 값 채움.
    rows = []
    for unit in _iter_units(soup):       # Task 0에서 확정
        rec = _empty()
        rec["대학명"] = 대학명
        rec["전형명"] = 전형명
        rec["모집단위명"] = _unit_name(unit)
        for label, value in _cells(unit):  # (헤더텍스트, 값)
            key = _map_label(label)
            if key:
                rec[key] = value
        rows.append(rec)
    return rows or [{**_empty(), "대학명": 대학명, "전형명": 전형명}]

_LABEL_MAP = {
    "인터넷": "원서접수_인터넷", "현장": "원서접수_현장",
    "논술등필답": "대학별고사_논술등필답", "면접구술": "대학별고사_면접구술",
    "실기": "대학별고사_실기", "합격자발표": "합격자발표일",
    "선발모형": "선발모형", "선발방법": "선발방법", "선발비율": "선발비율",
    "학생부": "반영_학생부", "수능": "반영_수능", "면접": "반영_면접",
    "논술": "반영_논술", "적성": "반영_적성", "1단계": "반영_1단계성적",
    "서류": "반영_서류", "기타": "반영_기타",
}

def _map_label(label: str):
    for kw, key in _LABEL_MAP.items():
        if kw in label:
            return key
    return None
```
`_iter_units`, `_unit_name`, `_cells`는 Task 0 픽스처 구조로 구현(표 grid 평탄화는
`week03/crawl_adiga.py`의 `_table_to_grid`·`_flatten_table` 재사용 가능).

- [ ] **Step 4: 통과 확인**

Run: `cd week10 && ../../../week05/.venv/bin/python -m pytest tests/test_schedule.py -v`
Expected: PASS. 픽스처 구조에 맞춰 `_iter_units`/`_cells` 조정.

- [ ] **Step 5: Commit**

```bash
git add week10/scripts/parse_schedule.py week10/tests/test_schedule.py
git commit -m "feat(w09): 전형일정및방법 파서 (고정 23열, 키워드 매핑)"
```

---

## Task 4: parse_element.py — 전형요소 raw 평면화

> **조건부**: Task 0 Step 5에서 전형요소 데이터 확보 실패 → 폴백 채택 시 이 task 건너뛰고
> 탭2를 빈 시트로 둔다(설계 §8). 성공 시 진행.

**Files:**
- Create: `week10/scripts/parse_element.py`
- Test: `week10/tests/test_element.py`
- 의존: `week10/tests/fixtures/element_가천대학생부교과.html`

- [ ] **Step 1: 실패 테스트 작성**

```python
# week10/tests/test_element.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import parse_element as EL

FIX = pathlib.Path(__file__).parent / "fixtures" / "element_가천대학생부교과.html"

def test_element_flattened_raw():
    recs = EL.parse(FIX.read_text(encoding="utf-8"))
    assert len(recs) >= 1
    # raw 평면화: 정규화 없이 페이지 표의 헤더가 컬럼으로 보존
    assert all(isinstance(r, dict) for r in recs)
    assert any(r for r in recs)  # 비어있지 않음
```

- [ ] **Step 2: 실패 확인**

Run: `cd week10 && ../../../week05/.venv/bin/python -m pytest tests/test_element.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현 (raw 평면화 — 정규화 금지)**

```python
# week10/scripts/parse_element.py
from bs4 import BeautifulSoup

def parse(html: str, 대학명: str = "", 전형명: str = "") -> list[dict]:
    """전형요소 페이지의 실데이터 표를 정규화 없이 평면화.
    대상: div.admssDtlSection 내 table만 (성적분석 팝업 pFrm/catAdmissSelPop 제외).
    각 표 caption=표이름. 헤더(th) 텍스트를 컬럼으로 그대로 사용.
    전형요소가 빈 전형(논술·수능위주 등)은 [] 반환 — 정상(에러 아님)."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for table in soup.select("div.admssDtlSection table"):
        cap = table.find("caption")
        tname = cap.get_text(" ", strip=True) if cap else ""
        headers = [th.get_text(" ", strip=True) for th in table.find_all("th")]
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if not cells:
                continue
            rec = {"대학명": 대학명, "전형명": 전형명, "표이름": tname}
            for i, v in enumerate(cells):
                key = headers[i] if i < len(headers) else f"col{i}"
                rec[key or f"col{i}"] = v
            rows.append(rec)
    return rows
```
spike 확정: `div.admssDtlSection table` 2개(학생부 학년별/요소별 반영비율·학생부 교과성적 반영방법),
caption이 표이름. 빈 전형은 admssDtlSection 0개 → `[]`.

- [ ] **Step 4: 통과 확인**

Run: `cd week10 && ../../../week05/.venv/bin/python -m pytest tests/test_element.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add week10/scripts/parse_element.py week10/tests/test_element.py
git commit -m "feat(w09): 전형요소 raw 평면화 파서"
```

---

## Task 5: write_excel.py — 2탭 워크북 (대학별 + 통합)

**Files:**
- Create: `week10/scripts/write_excel.py`
- Test: `week10/tests/test_write_excel.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# week10/tests/test_write_excel.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import write_excel as W
import openpyxl, parse_schedule as S

def test_writes_two_tabs(tmp_path):
    sched = [{**{c: "" for c in S.COLUMNS}, "대학명": "가천대", "전형명": "논술", "모집단위명": "간호"}]
    elem = [{"대학명": "가천대", "전형명": "논술", "표": 0, "구분": "학생부", "값": "100"}]
    out = tmp_path / "가천대.xlsx"
    W.write_university(out, sched, elem)
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["전형일정및방법", "전형요소"]
    assert wb["전형일정및방법"].max_row >= 2  # 헤더 + 1행 이상

def test_combined(tmp_path):
    sched = [{**{c: "" for c in S.COLUMNS}, "대학명": "가천대", "전형명": "논술", "모집단위명": "간호"}]
    out = tmp_path / "통합.xlsx"
    W.write_combined(out, [("가천대", sched, [])])
    wb = openpyxl.load_workbook(out)
    assert "전형일정및방법" in wb.sheetnames
```

- [ ] **Step 2: 실패 확인**

Run: `cd week10 && ../../../week05/.venv/bin/python -m pytest tests/test_write_excel.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

```python
# week10/scripts/write_excel.py
from pathlib import Path
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
import parse_schedule as S

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=9)

def _write_sheet(ws, rows: list[dict], columns: list[str] | None):
    if not rows:
        return
    cols = columns or list({k: None for r in rows for k in r}.keys())
    ws.append(cols)
    for r in rows:
        ws.append([r.get(c, "") for c in cols])
    for cell in ws[1]:
        cell.fill = HEADER_FILL; cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"

def write_university(path: Path, sched: list[dict], elem: list[dict]):
    from openpyxl import Workbook
    wb = Workbook()
    ws1 = wb.active; ws1.title = "전형일정및방법"
    _write_sheet(ws1, sched, S.COLUMNS)
    ws2 = wb.create_sheet("전형요소")
    _write_sheet(ws2, elem, None)   # 동적 컬럼
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)

def write_combined(path: Path, per_univ: list[tuple]):
    """per_univ = [(대학명, sched_rows, elem_rows), ...] → 통합 2탭."""
    from openpyxl import Workbook
    all_sched = [r for _, s, _ in per_univ for r in s]
    all_elem = [r for _, _, e in per_univ for r in e]
    wb = Workbook()
    ws1 = wb.active; ws1.title = "전형일정및방법"
    _write_sheet(ws1, all_sched, S.COLUMNS)
    ws2 = wb.create_sheet("전형요소")
    _write_sheet(ws2, all_elem, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
```

> 다단 병합헤더는 초안에선 단일 헤더로 시작(검증 우선). 샘플의 4단 병합헤더는 Task 7 검증 후
> 필요 시 `week06/scripts/format_detail.py`의 `_header_merges` 패턴 이식으로 고도화(YAGNI: 후속).

- [ ] **Step 4: 통과 확인**

Run: `cd week10 && ../../../week05/.venv/bin/python -m pytest tests/test_write_excel.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add week10/scripts/write_excel.py week10/tests/test_write_excel.py
git commit -m "feat(w09): 2탭 워크북 출력 (대학별 + 통합)"
```

---

## Task 6: crawl_admission.py — 메인 오케스트레이션

**Files:**
- Create: `week10/scripts/crawl_admission.py`

- [ ] **Step 1: 구현 (열거→fetch→파싱→쓰기, 병렬+resume)**

```python
# week10/scripts/crawl_admission.py
import csv, json, pickle, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import net, enumerate_admissions as E, parse_schedule as S, parse_element as EL, write_excel as W

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "week10" / "output"
PROGRESS = OUT / ".progress"
DETAIL_URL = "https://www.adiga.kr/ucp/prc/uni/admssUnivDetail.do"
ELEMENT_URL = "https://www.adiga.kr/ucp/prc/uni/admssUnivDetailElement.do"
WORKERS = 6
SYR = "2027"
# 샘플 5개 대학(랜덤) — Task 7에서 확정/기록
SAMPLE = ["0000063"]  # 가천대 포함, 나머지 4개 Task 7에서 채움

def _names() -> dict:
    f = ROOT / "week03" / "input" / "target_universities.csv"
    with open(f, encoding="utf-8") as fh:
        return {r["unv_cd"].strip(): r["univ_name"].strip() for r in csv.DictReader(fh)}

NAMES = _names()

def crawl_university(unv: str) -> tuple:
    """대학 → (sched_rows, elem_rows)."""
    name = NAMES.get(unv, unv)
    admissions = E.fetch(unv, ENUM_FORM)
    sched, elem = [], []
    for a in admissions:
        params = {k: a[k] for k in E.PARAM_KEYS if a.get(k)}
        params.update({"unvCd": unv, "searchSyr": SYR, "menuId": "PCPRCINF2000"})
        hs = net._request("GET", DETAIL_URL, params=params).text
        sched += S.parse(hs, 대학명=name, 전형명=a.get("전형명", ""))
        try:
            he = net._request("GET", ELEMENT_URL, params={**params, "admssInfoTabYn": ""}).text
            elem += EL.parse(he, 대학명=name, 전형명=a.get("전형명", ""))
        except Exception:
            pass  # 전형요소 폴백 시 무시
    return sched, elem

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    targets = SAMPLE
    print(f"=== 전형정보 크롤 — 대상 {len(targets)}개 대학 (동시 {WORKERS}) ===\n")
    t0 = time.time()
    per_univ = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(crawl_university, u): u for u in targets}
        for fut in as_completed(futs):
            u = futs[fut]; name = NAMES.get(u, u)
            try:
                sched, elem = fut.result()
                W.write_university(OUT / "대학별" / f"{name}.xlsx", sched, elem)
                per_univ.append((name, sched, elem))
                print(f"  ✓ {name} ({u})  전형일정 {len(sched)}행 / 전형요소 {len(elem)}행")
            except Exception as e:
                print(f"  ✗ {name} ({u})  {type(e).__name__}: {e}")
    W.write_combined(OUT / "전형정보_통합.xlsx", per_univ)
    m, s = divmod(int(time.time() - t0), 60)
    print(f"\n✓ 통합본 저장. ⏱ {m}분 {s}초")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 구문 확인**

Run: `cd week10 && ../../../week05/.venv/bin/python -c "import sys; sys.path.insert(0,'scripts'); import crawl_admission"`
Expected: 에러 없음

- [ ] **Step 3: Commit**

```bash
git add week10/scripts/crawl_admission.py
git commit -m "feat(w09): 메인 오케스트레이션 (열거→fetch→파싱→2탭 출력)"
```

---

## Task 7: 샘플 5개 대학 end-to-end + 가천대 스키마 검증

**Files:**
- Modify: `week10/scripts/crawl_admission.py:SAMPLE` (랜덤 5개 확정)

- [ ] **Step 1: 샘플 5개 대학 랜덤 선정**

```bash
cd week10 && ../../../week05/.venv/bin/python -c "
import csv, random
rows=list(csv.DictReader(open('../week03/input/target_universities.csv',encoding='utf-8')))
random.seed(9)  # 재현 가능
pick=random.sample([r['unv_cd'].strip() for r in rows], 5)
if '0000063' not in pick: pick[0]='0000063'  # 가천대 검증용 포함
print(pick)
"
```
출력된 5개 코드를 `crawl_admission.py`의 `SAMPLE`에 기록.

- [ ] **Step 2: 전체 실행**

Run: `cd week10 && ../../../week05/.venv/bin/python scripts/crawl_admission.py`
Expected: 5개 대학 모두 `✓`, 0 error. `output/대학별/*.xlsx` 5개 + `output/전형정보_통합.xlsx` 생성.

- [ ] **Step 3: 가천대 탭1 컬럼이 샘플과 일치하는지 검증**

```bash
cd week10 && ../../../week05/.venv/bin/python -c "
import openpyxl
got=openpyxl.load_workbook('output/대학별/가천대학교.xlsx')['전형일정및방법']
ref=openpyxl.load_workbook('/Users/channy/Downloads/가천대.xlsx')['전형일정및방법']
print('탭:', openpyxl.load_workbook('output/대학별/가천대학교.xlsx').sheetnames)
print('출력 행수:', got.max_row, '| 데이터 채워짐:', got.max_row>1)
"
```
Expected: 탭 2개(`전형일정및방법`/`전형요소`), 데이터 행 ≥ 2. 샘플 23개 항목이 출력 컬럼에 모두 존재.

- [ ] **Step 4: 전체 테스트 통과 확인**

Run: `cd week10 && ../../../week05/.venv/bin/python -m pytest tests/ -v`
Expected: 모든 테스트 PASS.

- [ ] **Step 5: Commit**

```bash
git add week10/scripts/crawl_admission.py
git commit -m "feat(w09): 샘플 5개 대학 확정 + end-to-end 검증 통과"
```

---

## Self-Review 메모

- **Spec 커버리지**: §2 엔드포인트→Task0/2/6, §5 탭1 23열→Task3, 탭2 raw→Task4, 출력 대학별+통합→Task5/6, §6 샘플5→Task7, §7 블로킹→Task1, §8 spike+폴백→Task0(+Task4 조건부), §9 검증→Task7. 누락 없음.
- **타입 일관성**: 파서 `parse(html,…)->list[dict]`, `E.PARAM_KEYS`/`E.fetch`, `S.COLUMNS` 일관 사용.
- **Spike 의존**: Task2~4의 셀렉터/정규식은 Task0 픽스처로 확정한다는 점을 각 task에 명시(placeholder 아님 — 확정 절차를 task로 가짐).
- **YAGNI**: 다단 병합헤더는 검증 후 후속(Task5 노트). resume 캐시는 샘플 5개라 초안에서 생략(전량 시 week06 이식).
