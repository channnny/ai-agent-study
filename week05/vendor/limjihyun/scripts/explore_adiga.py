"""adiga.kr 사이트 구조 탐색: 대학 검색 페이지 위치 및 univCode 패턴 확인."""
from playwright.sync_api import sync_playwright
import json

OUT = "/Users/vibeon/Documents/무제 폴더/out/explore"
import os
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()

    page.goto("https://www.adiga.kr/", wait_until="networkidle", timeout=30000)
    page.screenshot(path=f"{OUT}/01_home.png", full_page=True)
    print("HOME title:", page.title())

    nav_links = page.evaluate(
        """() => Array.from(document.querySelectorAll('a')).slice(0, 200).map(a => ({
            text: (a.innerText || '').trim().slice(0, 40),
            href: a.getAttribute('href') || '',
        })).filter(x => x.text && x.href)"""
    )
    uni_links = [l for l in nav_links if "대학" in l["text"] or "uvt" in l["href"] or "univ" in l["href"].lower()]
    print(f"\n대학 관련 링크 ({len(uni_links)}건):")
    for l in uni_links[:30]:
        print(f"  {l['text']:40s} -> {l['href']}")

    candidate_urls = [
        "https://www.adiga.kr/ucp/uvt/uni/univList.do?menuId=PCUVTINF2000",
        "https://www.adiga.kr/PageLink.do?link=/ucp/uvt/uni/univList.do",
    ]
    for url in candidate_urls:
        try:
            page.goto(url, wait_until="networkidle", timeout=20000)
            print(f"\n[OK] {url}")
            print("  title:", page.title())
            page.screenshot(path=f"{OUT}/02_list_{candidate_urls.index(url)}.png", full_page=False)
            sample = page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href*=univCode]')).slice(0, 10).map(a => ({
                    text: (a.innerText || '').trim().slice(0, 30),
                    href: a.getAttribute('href') || '',
                }))"""
            )
            if sample:
                print("  univCode 링크 샘플:")
                for s in sample:
                    print(f"    {s['text']:30s} -> {s['href']}")
                break
        except Exception as e:
            print(f"[FAIL] {url}: {e}")

    browser.close()
