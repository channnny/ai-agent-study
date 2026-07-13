import re, html as _html
from bs4 import BeautifulSoup
import net

VIEW_URL = "https://www.adiga.kr/ucp/prc/uni/admssUnivView.do"
UNIV_AJAX_URL = "https://www.adiga.kr/ucp/prc/uni/admssUnivAjax.do"
LIST_URL = "https://www.adiga.kr/ucp/prc/uni/admssUnivDetailLstAjax.do"
PARAM_KEYS = ("unvCd", "comScsbjtCd", "slcnGroupCd", "rcmtMmntCd",
              "ruCd", "ruSn", "lclsfAftCd", "slcnTypeCd", "slcnCd")

def _form_fields(html: str) -> dict:
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
    """LstAjax 프래그먼트 → 전형 행 dict 목록."""
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

# ── 전형×모집단위 열거 (Playwright) ───────────────────────────
# requests로는 불가: admssUnivAjax/LstAjax가 페이지 JS가 만든 서버측 세션
# 상태를 요구함(동일 본문·CSRF·쿠키로도 빈 결과 — 2026-06-30 검증). 진짜
# 브라우저(Playwright headless)가 세션을 워밍하면 in-page fetch로 열거 가능.
#
# 모델(spike 확정): comScsbjtCd = 학과(모집단위) 코드. 대학 검색 →
#   admssUnivAjax 페이지네이션으로 학과(comScsbjtCd) 수집 →
#   학과별 LstAjax → 전형 sub-행(fnDetailPage 9인자) = (전형×모집단위).

# 페이지 내에서 실행: 학과 페이지네이션 수집 → 학과별 LstAjax → tuple 배열 반환
_HARVEST_JS = r"""
async (unvCd) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const csrf = (document.querySelector('meta[name=_csrf]') || {}).content || '';
  const frm = document.querySelector('#frm');
  const H = {'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8',
             'X-Requested-With':'XMLHttpRequest','X-CSRF-TOKEN':csrf};
  const post = async (url, ov) => {
    const b = new URLSearchParams(new FormData(frm));
    for (const k in ov) b.set(k, ov[k]);
    const r = await fetch(url, {method:'POST', headers:H, body:b.toString()});
    return await r.text();
  };
  const parse = h => new DOMParser().parseFromString(h, 'text/html');
  // 1) 학과(comScsbjtCd) 수집 — 페이지네이션.
  //   종단은 RAW 학과 유무 기준(캠퍼스는 앞쪽이 본교 페이지라 필터-매칭 기준이면 조기중단됨).
  //   서버가 범위 밖 페이지를 마지막으로 클램프하는 경우 대비: 신규 학과 3연속 없으면 종단.
  const deptMap = {};
  let prevSig = '', repeat = 0;
  for (let pg = 1; pg <= 300; pg++) {
    let doc = parse(await post('/ucp/prc/uni/admssUnivAjax.do', {'pagination.currentPage': String(pg)}));
    let raw = [...doc.querySelectorAll('li.opnfldClass[comscsbjtcd]')];
    if (!raw.length) {            // 진짜 끝: 페이지에 학과 자체가 없음 → 1회 재시도 후 중단
      await sleep(600);
      doc = parse(await post('/ucp/prc/uni/admssUnivAjax.do', {'pagination.currentPage': String(pg)}));
      raw = [...doc.querySelectorAll('li.opnfldClass[comscsbjtcd]')];
      if (!raw.length) break;
    }
    // 종단: 서버가 범위 밖 페이지를 마지막 페이지로 클램프(같은 내용 반복)하면 중단.
    //   본교 프리픽스 페이지는 시그니처가 매 페이지 달라지므로 정상 진행됨(캠퍼스는 뒷페이지).
    const sig = raw.map(li => li.getAttribute('comscsbjtcd')).join(',');
    if (sig === prevSig) { if (++repeat >= 2) break; } else repeat = 0;
    prevSig = sig;
    const lis = raw.filter(li => li.getAttribute('unvcd') === unvCd);   // 대상 대학코드만
    const byCom = {};
    lis.forEach(li => { const c = li.getAttribute('comscsbjtcd');
      (byCom[c] = byCom[c] || []).push((li.textContent || '').replace(/\s+/g,' ').trim()); });
    for (const c in byCom) if (!(c in deptMap)) {
      const dept = byCom[c].find(t => /\(주간\)|\(야간\)|학과|학부|전공|대학$/.test(t)
                                      && !/대학교\s*\[/.test(t)) || '';
      deptMap[c] = dept;
    }
    await sleep(250);
  }
  // 2) 학과별 LstAjax → 전형 sub-행(fnDetailPage 9인자)
  const out = [];
  for (const com in deptMap) {
    const doc = parse(await post('/ucp/prc/uni/admssUnivDetailLstAjax.do', {unvCd, comScsbjtCd: com}));
    doc.querySelectorAll('a.selectUnivComScsbjtCd').forEach(a => {
      const m = (a.getAttribute('onclick') || '').match(/fnDetailPage\(([^)]*)\)/);
      if (!m) return;
      const args = m[1].split(',').map(s => s.trim().replace(/^["']|["']$/g, ''));
      out.push({args, jh: (a.textContent || '').replace(/\s+/g,' ').trim(), dept: deptMap[com]});
    });
    await sleep(250);
  }
  return out;
}
"""


def fetch_units(unv_cd: str, unv_name: str, syr: str = "2027", headless: bool = True,
                retries: int = 3) -> list[dict]:
    """대학 → 모든 (전형×모집단위) 파라미터 tuple. Playwright headless로 세션 워밍.

    열거가 간헐적으로 0/부실할 수 있어(autocomplete·세션 타이밍) 0건이면 재시도한다.
    반환: [{**PARAM_KEYS, '전형명', '학과명'}, ...]
    """
    best = []
    for attempt in range(retries):
        got = _fetch_units_once(unv_cd, unv_name, syr, headless)
        if len(got) > len(best):
            best = got
        if best:            # 1건이라도 나오면 채택(부분 아님을 보장하진 않지만 0건 회피)
            break
    return best


def _fetch_units_once(unv_cd: str, unv_name: str, syr: str, headless: bool) -> list[dict]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(f"{VIEW_URL}?menuId=PCPRCINF2000", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        # 대학명 검색 → 세션에 대학 선택 등록 + 목록 로드 (실 브라우저 흐름 그대로)
        box = page.get_by_placeholder(re.compile("대학명"))
        box.click()
        box.fill(unv_name)              # 베이스명(캠퍼스 접미사 제거) → 본교+캠퍼스 모두 세션 워밍
        # 이 입력은 Enter가 막혀있음(onkeypress return false) → 검색 버튼 클릭으로 필터검색 실행
        page.click("a.searchTitleBtn")
        page.wait_for_timeout(3000)
        # 필터는 우리 CSV(어디가 공식) 대학코드로. autocomplete는 동명(서울대→남서울)·
        # 캠퍼스(고려대→본교)를 오해석하므로 신뢰하지 않는다. 세종/ERICA 등은 뒷페이지에 존재.
        code = unv_cd
        raw = page.evaluate(_HARVEST_JS, code)
        browser.close()

    units = []
    for r in raw:
        args = r["args"]
        if len(args) < len(PARAM_KEYS):
            continue
        rec = {k: args[i] for i, k in enumerate(PARAM_KEYS)}
        rec["전형명"] = r.get("jh", "")
        rec["학과명"] = r.get("dept", "")
        units.append(rec)
    return units
