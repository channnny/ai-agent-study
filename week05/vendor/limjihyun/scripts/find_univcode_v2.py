"""자동완성 XHR 응답을 가로채서 univCode 추출."""
from playwright.sync_api import sync_playwright
import json

TARGET = "고려대학교"
OUT = "/Users/vibeon/Documents/무제 폴더/out/explore"

xhr_records = []

def on_response(resp):
    url = resp.url
    if any(kw in url.lower() for kw in ["autocomplet", "search", "univ", "list"]) and resp.request.method in ("GET", "POST"):
        try:
            ctype = resp.headers.get("content-type", "")
            if "json" in ctype or "javascript" in ctype:
                body = resp.text()
                xhr_records.append({"url": url, "status": resp.status, "body": body[:2000]})
        except Exception:
            pass

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    page.on("response", on_response)

    page.goto("https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000", wait_until="networkidle", timeout=30000)
    page.locator("#autoComplet").click()
    page.locator("#autoComplet").type(TARGET, delay=80)
    page.wait_for_timeout(2000)

    page.screenshot(path=f"{OUT}/20_autocomplete.png", full_page=False)

    dropdown = page.evaluate(
        """() => Array.from(document.querySelectorAll('ul li, .autocomplete li, [class*=autocomplete] *, [id*=autoComplet] ~ * *'))
            .slice(0, 50)
            .map(el => ({
                text: (el.innerText || '').trim().slice(0, 60),
                onclick: (el.getAttribute('onclick') || '').slice(0, 300),
                data: Array.from(el.attributes).filter(a => a.name.startsWith('data-')).map(a => `${a.name}=${a.value}`).join('; '),
            }))
            .filter(x => x.text && x.text.includes('대') && x.text.length < 50)"""
    )
    print("자동완성 드롭다운 후보:")
    for d in dropdown[:20]:
        print(f"  {d}")

    print(f"\nXHR 캡처 ({len(xhr_records)}건):")
    for r in xhr_records[-10:]:
        print(f"\n[{r['status']}] {r['url']}")
        print(f"  body: {r['body'][:500]}")

    print("\n--- 자동완성 첫 항목 클릭 시도 ---")
    try:
        first = page.locator("#autoComplet ~ * li, .ui-autocomplete li, [class*=autocomplete-list] li").first
        if first.count() > 0:
            print("first item text:", first.inner_text()[:60])
            first.click()
            page.wait_for_load_state("networkidle", timeout=10000)
            page.screenshot(path=f"{OUT}/21_after_click.png", full_page=False)
            print("URL after click:", page.url)
            unv = page.locator("#unvCd").input_value()
            print("unvCd hidden field:", unv)
    except Exception as e:
        print("click 실패:", e)

    browser.close()
