"""대학명 리스트 → univInfo.do API로 unvCd 조회."""
from __future__ import annotations
import json, sys
from playwright.sync_api import sync_playwright


def resolve(names: list[str]) -> dict[str, list[dict]]:
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context().new_page()
        page.goto("https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000",
                  wait_until="networkidle", timeout=30000)
        for name in names:
            try:
                res = page.evaluate(
                    """async (nm) => {
                        const u = `/man/sch/univInfo.do?offset=0&limit=100&search=${encodeURIComponent(nm)}&sort=$relevance&sortType=desc&sortYear=&checkMiss=1`;
                        const r = await fetch(u, {credentials:'include'});
                        if (!r.ok) return [];
                        const d = await r.json();
                        return (d?.result?.rows || []).map(row => ({
                            name: row.fields.UNIV_NM, code: row.fields.UNIV_CD,
                            area: row.fields.AREA, fond: row.fields.FOND_SE
                        }));
                    }""", name)
                out[name] = res
            except Exception as e:
                out[name] = [{"error": str(e)}]
        browser.close()
    return out


if __name__ == "__main__":
    names = sys.argv[1:] or [
        "건국대학교", "경기대학교", "동국대학교", "가천대학교",
        "영남대학교", "동덕여자대학교", "가톨릭관동대학교",
    ]
    result = resolve(names)
    for nm, rows in result.items():
        print(f"\n[{nm}]")
        for r in rows[:5]:
            print(f"  {r.get('code','?')} | {r.get('name','?')} | {r.get('area','')} | {r.get('fond','')}")
