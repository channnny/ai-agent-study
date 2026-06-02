"""고려대학교 상세 페이지에 진입해 평가기준·입시결과 탭 구조 확인."""
from playwright.sync_api import sync_playwright
import json

UNV_CD = "0000069"
URL = f"https://www.adiga.kr/ucp/uvt/uni/univDetail.do?searchSyr=2027&searchUnvCodeAllYn=true&unvCd={UNV_CD}&sortNm=&sortOrder=true&unvLink=on"
OUT = "/Users/vibeon/Documents/무제 폴더/out/explore"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1400, "height": 1200})
    page = ctx.new_page()

    page.goto(URL, wait_until="networkidle", timeout=30000)
    print("title:", page.title())
    print("URL:", page.url)
    page.screenshot(path=f"{OUT}/50_detail_initial.png", full_page=True)

    print("\n--- 좌측 메뉴 / 탭 후보 ---")
    menus = page.evaluate(
        """() => Array.from(document.querySelectorAll('a, button, li, div'))
            .filter(el => {
                const t = (el.innerText || '').trim();
                return t && t.length < 30 && (
                    t.match(/평가기준|입시결과|입결|학생부|수시|정시|교과|종합|논술|실기/) ||
                    t.match(/모집요강|전형/)
                ) && el.children.length < 5;
            })
            .slice(0, 40)
            .map(el => ({
                tag: el.tagName, text: (el.innerText || '').trim().slice(0, 40),
                onclick: (el.getAttribute('onclick') || '').slice(0, 200),
                href: el.getAttribute('href') || '',
                id: el.id,
                cls: (el.className || '').slice(0, 80),
            }))"""
    )
    seen = set()
    for m in menus:
        key = (m["text"], m["onclick"][:80])
        if key in seen: continue
        seen.add(key)
        print(f"  {m['tag']:6s} {m['text']:30s} oc={m['onclick'][:80]} cls={m['cls'][:40]}")

    print("\n--- 페이지 내 표(table) 개수 ---")
    table_count = page.evaluate("() => document.querySelectorAll('table').length")
    print(f"tables: {table_count}")

    browser.close()
