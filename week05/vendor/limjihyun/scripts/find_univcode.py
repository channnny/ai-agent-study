"""대학정보 페이지 진입 → 대학 1개 검색 → univCode 추출."""
from playwright.sync_api import sync_playwright

TARGET = "고려대학교"
OUT = "/Users/vibeon/Documents/무제 폴더/out/explore"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()

    page.goto("https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000", wait_until="networkidle", timeout=30000)
    page.screenshot(path=f"{OUT}/10_univView_base.png", full_page=True)
    print("base URL title:", page.title())
    print("base URL:", page.url)

    inputs = page.evaluate(
        """() => Array.from(document.querySelectorAll('input')).slice(0, 30).map(el => ({
            id: el.id, name: el.name, type: el.type,
            placeholder: el.placeholder, value: el.value,
        }))"""
    )
    print("\nINPUTS:")
    for i in inputs:
        print(f"  {i}")

    buttons = page.evaluate(
        """() => Array.from(document.querySelectorAll('button, a.btn, input[type=button], input[type=submit]')).slice(0, 30).map(el => ({
            tag: el.tagName, text: (el.innerText || el.value || '').trim().slice(0, 30),
            onclick: (el.getAttribute('onclick') || '').slice(0, 80),
        }))"""
    )
    print("\nBUTTONS:")
    for b in buttons:
        if b["text"]:
            print(f"  {b}")

    print(f"\n--- 검색 시도: {TARGET} ---")
    candidates = ["input[name=schUnivNm]", "input[id*=univ]", "input[placeholder*=대학]"]
    found_input = None
    for sel in candidates:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                found_input = sel
                print(f"검색 input found: {sel}")
                break
        except:
            pass

    if found_input:
        page.fill(found_input, TARGET)
        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle", timeout=15000)
        page.screenshot(path=f"{OUT}/11_search_result.png", full_page=True)
        print("after search URL:", page.url)

        univ_links = page.evaluate(
            """() => Array.from(document.querySelectorAll('a, button, div[onclick]')).map(el => ({
                text: (el.innerText || '').trim().slice(0, 40),
                onclick: (el.getAttribute('onclick') || '').slice(0, 200),
                href: el.getAttribute('href') || '',
            })).filter(x => (x.onclick + x.href).match(/univCode|univCd/i))"""
        )
        print(f"\n검색 결과 내 univCode 단서 ({len(univ_links)}건):")
        for l in univ_links[:10]:
            print(f"  {l}")

    browser.close()
