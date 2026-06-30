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
  // 1) 학과(comScsbjtCd) 수집 — 페이지네이션
  const deptMap = {};
  for (let pg = 1; pg <= 80; pg++) {
    const doc = parse(await post('/ucp/prc/uni/admssUnivAjax.do', {'pagination.currentPage': String(pg)}));
    const lis = [...doc.querySelectorAll('li.opnfldClass[comscsbjtcd]')]
                  .filter(li => li.getAttribute('unvcd') === unvCd);
    if (!lis.length) break;
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


def fetch_units(unv_cd: str, unv_name: str, syr: str = "2027", headless: bool = True) -> list[dict]:
    """대학 → 모든 (전형×모집단위) 파라미터 tuple. Playwright headless로 세션 워밍.

    반환: [{**PARAM_KEYS, '전형명', '학과명'}, ...]
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(f"{VIEW_URL}?menuId=PCPRCINF2000", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        # 대학명 검색 → 세션에 대학 선택 등록 + 목록 로드 (실 브라우저 흐름 그대로)
        box = page.get_by_placeholder(re.compile("대학명"))
        box.click()
        box.fill(unv_name)
        box.press("Enter")
        page.wait_for_timeout(3000)
        raw = page.evaluate(_HARVEST_JS, unv_cd)
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
