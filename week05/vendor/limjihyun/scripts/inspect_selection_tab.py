"""평가기준 및 입시결과 탭 진입 → 학생부종합·학생부교과 표 구조 확인."""
from playwright.sync_api import sync_playwright
import json

UNV_CD = "0000069"
URL = f"https://www.adiga.kr/ucp/uvt/uni/univDetail.do?searchSyr=2027&searchUnvCodeAllYn=true&unvCd={UNV_CD}&sortNm=&sortOrder=true&unvLink=on"
OUT = "/Users/vibeon/Documents/무제 폴더/out/explore"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1400, "height": 1500})
    page = ctx.new_page()
    page.goto(URL, wait_until="networkidle", timeout=30000)

    print("--- '평가기준 및 입시결과' 클릭 ---")
    page.locator("a:has-text('평가기준 및 입시결과')").first.click()
    page.wait_for_timeout(3000)
    page.screenshot(path=f"{OUT}/60_after_selection.png", full_page=True)
    print("URL:", page.url)

    table_count = page.evaluate("() => document.querySelectorAll('table').length")
    print(f"\ntables: {table_count}")

    print("\n--- 표 caption / headers 미리보기 ---")
    tables_info = page.evaluate(
        """() => {
            const out = [];
            document.querySelectorAll('table').forEach((t, i) => {
                const cap = t.querySelector('caption');
                const ths = Array.from(t.querySelectorAll('thead th, tr:nth-child(1) th, tr:nth-child(1) td')).slice(0, 20).map(th => (th.innerText || '').trim());
                const firstRow = Array.from(t.querySelectorAll('tbody tr:first-child td, tr:nth-child(2) td')).slice(0, 20).map(td => (td.innerText || '').trim());
                out.push({
                    idx: i,
                    caption: cap ? cap.innerText.trim().slice(0, 80) : '',
                    rows: t.querySelectorAll('tr').length,
                    headers: ths,
                    firstRow: firstRow,
                });
            });
            return out;
        }"""
    )
    for t in tables_info:
        print(f"\n  [Table {t['idx']}] rows={t['rows']} caption={t['caption']!r}")
        print(f"    headers ({len(t['headers'])}): {t['headers'][:10]}")
        if t['firstRow']:
            print(f"    firstRow:  {t['firstRow'][:10]}")

    print("\n--- 학생부종합/학생부교과 탭 후보 ---")
    sub_tabs = page.evaluate(
        """() => Array.from(document.querySelectorAll('a, button, li')).filter(el => {
            const t = (el.innerText || '').trim();
            return t.match(/학생부.*(종합|교과)/) || t.match(/^종합$|^교과$/);
        }).slice(0, 20).map(el => ({
            tag: el.tagName, text: (el.innerText || '').trim().slice(0, 30),
            onclick: (el.getAttribute('onclick') || '').slice(0, 150),
            cls: (el.className || '').slice(0, 80),
        }))"""
    )
    for s in sub_tabs:
        print(f"  {s['tag']:6s} {s['text']:30s} oc={s['onclick']} cls={s['cls'][:40]}")

    browser.close()
