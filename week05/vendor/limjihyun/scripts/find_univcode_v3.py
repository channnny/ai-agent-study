"""검색 흐름: 입력 → 검색 버튼 클릭 → 결과 카드 → 상세 진입 → URL/unvCd 추출."""
from playwright.sync_api import sync_playwright
import re

TARGET = "고려대학교"
OUT = "/Users/vibeon/Documents/무제 폴더/out/explore"

navigation_urls = []

def on_request(req):
    if "univ" in req.url.lower() or "unv" in req.url.lower():
        navigation_urls.append(f"{req.method} {req.url}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    page.on("request", on_request)

    page.goto("https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000",
              wait_until="networkidle", timeout=30000)

    page.fill("#autoComplet", TARGET)
    page.screenshot(path=f"{OUT}/30_filled.png")

    print("--- 검색 트리거: Enter ---")
    page.locator("#autoComplet").press("Enter")
    page.wait_for_timeout(3000)
    page.screenshot(path=f"{OUT}/31_after_enter.png", full_page=True)
    print("URL after enter:", page.url)

    cards = page.evaluate(
        """() => {
            const out = [];
            document.querySelectorAll('[onclick], [data-unv-cd], [data-unvCd], [data-cd]').forEach(el => {
                const txt = (el.innerText || '').trim().slice(0, 80);
                const oc = el.getAttribute('onclick') || '';
                if (txt && (oc.match(/unv|univ/i) || el.outerHTML.match(/unvCd|univCode/))) {
                    out.push({ tag: el.tagName, text: txt, onclick: oc.slice(0, 200),
                               attrs: Array.from(el.attributes).map(a => `${a.name}=${a.value}`).join('|').slice(0, 200) });
                }
            });
            return out.slice(0, 30);
        }"""
    )
    print(f"\nunv 관련 클릭 요소 {len(cards)}건:")
    for c in cards[:20]:
        print(f"  {c['tag']} text={c['text'][:40]!r} onclick={c['onclick']}")

    print(f"\n--- unv 관련 요청 ({len(navigation_urls)}건) ---")
    for u in navigation_urls[-15:]:
        print(" ", u)

    print("\n--- 페이지 텍스트에 고려대 매치 ---")
    matched = page.evaluate(
        """(target) => {
            const out = [];
            document.querySelectorAll('*').forEach(el => {
                const txt = (el.innerText || el.textContent || '').trim();
                if (txt === target && el.children.length < 5) {
                    let chain = [];
                    let cur = el;
                    for (let i = 0; i < 5 && cur; i++) {
                        const oc = cur.getAttribute && cur.getAttribute('onclick');
                        if (oc) chain.push(`<${cur.tagName}> onclick=${oc.slice(0, 200)}`);
                        cur = cur.parentElement;
                    }
                    out.push({ text: txt, chain: chain.join(' > ') });
                }
            });
            return out.slice(0, 5);
        }""",
        TARGET,
    )
    for m in matched:
        print(" ", m)

    browser.close()
