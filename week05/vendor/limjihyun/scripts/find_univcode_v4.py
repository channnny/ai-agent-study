"""검색 결과 API 응답에서 unvCd 추출."""
from playwright.sync_api import sync_playwright
import json
import re

TARGET = "고려대학교"
OUT = "/Users/vibeon/Documents/무제 폴더/out/explore"

captured = {}

def on_response(resp):
    if "univInfo.do" in resp.url:
        try:
            body = resp.text()
            captured[resp.url] = body
        except Exception:
            pass

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    page.on("response", on_response)

    page.goto("https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000",
              wait_until="networkidle", timeout=30000)
    page.fill("#autoComplet", TARGET)
    page.locator("#autoComplet").press("Enter")
    page.wait_for_timeout(4000)

    print(f"captured univInfo.do 응답 {len(captured)}건")
    for url, body in captured.items():
        print(f"\n[URL] {url}")
        try:
            data = json.loads(body)
            print(f"  keys: {list(data.keys())[:10]}")
            print(f"  preview: {json.dumps(data, ensure_ascii=False)[:1500]}")
        except json.JSONDecodeError:
            codes = re.findall(r'(?:unvCd|univCode|UNV_CD)["\':\s]+([\'"]?)([0-9]{4,10})\1', body)
            print(f"  not JSON, regex matches: {codes[:10]}")

    print("\n--- 결과 카드 내 fnGoUniv 등 함수 호출 추출 ---")
    page.screenshot(path=f"{OUT}/40_search_result.png", full_page=True)
    fns = page.evaluate(
        """(target) => {
            const out = [];
            document.querySelectorAll('*[onclick]').forEach(el => {
                const oc = el.getAttribute('onclick') || '';
                const tx = (el.innerText || '').trim().slice(0, 80);
                if (oc.match(/Univ|univ|Unv|unv/) && (tx.includes(target) || oc.match(/[0-9]{4,}/))) {
                    out.push({ tag: el.tagName, text: tx, onclick: oc.slice(0, 300) });
                }
            });
            return out.slice(0, 30);
        }""",
        TARGET,
    )
    for f in fns:
        print(f"  {f['tag']} text={f['text']!r} oc={f['onclick']}")

    browser.close()
