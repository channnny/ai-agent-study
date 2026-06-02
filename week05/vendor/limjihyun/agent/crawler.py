"""Crawler: 어디가 대학 상세 페이지에서 평가기준·입시결과 영역의 표 raw JSON 추출."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

OUT_DIR = Path("/Users/vibeon/Documents/무제 폴더/out")
RAW_DIR = OUT_DIR / "raw"
SHOT_DIR = OUT_DIR / "screenshots"
DETAIL_URL = (
    "https://www.adiga.kr/ucp/uvt/uni/univDetail.do"
    "?searchSyr={year}&searchUnvCodeAllYn=true&unvCd={code}"
    "&sortNm=&sortOrder=true&unvLink=on"
)


_FLATTEN_JS = r"""
() => {
    const isNumeric = s => {
        const t = String(s || '').replace(/[,%\s]/g, '').trim();
        return /^-?\d+(\.\d+)?$/.test(t);
    };
    const numRatio = row => {
        const nonEmpty = row.filter(x => x && String(x).trim().length > 0);
        if (nonEmpty.length === 0) return 0;
        return nonEmpty.filter(isNumeric).length / nonEmpty.length;
    };

    const out = [];
    document.querySelectorAll('table').forEach((t, idx) => {
        const trs = Array.from(t.querySelectorAll('tr'));
        const grid = [];
        trs.forEach((tr, rIdx) => {
            if (!grid[rIdx]) grid[rIdx] = [];
            const cells = Array.from(tr.querySelectorAll('th, td'));
            let c = 0;
            cells.forEach(cell => {
                while (grid[rIdx][c] !== undefined) c++;
                const text = (cell.innerText || '').replace(/\s+/g, ' ').trim();
                const rs = parseInt(cell.getAttribute('rowspan') || '1');
                const cs = parseInt(cell.getAttribute('colspan') || '1');
                for (let dr = 0; dr < rs; dr++) {
                    for (let dc = 0; dc < cs; dc++) {
                        if (!grid[rIdx + dr]) grid[rIdx + dr] = [];
                        grid[rIdx + dr][c + dc] = text;
                    }
                }
                c += cs;
            });
        });

        const maxCols = Math.max(0, ...grid.map(r => r.length));
        grid.forEach(r => { while (r.length < maxCols) r.push(''); });

        let headerEnd = 0;
        for (let i = 0; i < Math.min(grid.length, 5); i++) {
            if (numRatio(grid[i]) < 0.10) headerEnd = i + 1;
            else break;
        }

        const headerRows = grid.slice(0, headerEnd);
        const dataRows = grid.slice(headerEnd);

        const flat_headers = [];
        for (let c = 0; c < maxCols; c++) {
            const parts = [];
            for (let r = 0; r < headerRows.length; r++) {
                const v = (headerRows[r][c] || '').trim();
                if (v && (parts.length === 0 || parts[parts.length - 1] !== v)) parts.push(v);
            }
            flat_headers.push(parts.join('.'));
        }

        let lastFirst = '';
        const filled_data = dataRows.map(row => {
            const r = [...row];
            if (!r[0] || r[0].trim() === '') r[0] = lastFirst;
            else lastFirst = r[0];
            return r;
        });

        const thead_label = (headerRows[0] && headerRows[0][1]) || '';

        out.push({
            idx,
            caption: (t.querySelector('caption') || {}).innerText || '',
            flat_headers,
            thead_label: thead_label.trim(),
            data_rows: filled_data,
            header_row_count: headerEnd,
            data_row_count: filled_data.length,
        });
    });
    return out;
}
"""


def _extract_tables(page: Page) -> list[dict]:
    """페이지의 모든 <table>을 평면화된 {flat_headers, data_rows} 구조로 변환."""
    return page.evaluate(_FLATTEN_JS)


def _resolve_univ_name(page: Page, unv_cd: str) -> str | None:
    """페이지 내부 univName 추출. 자동완성·인기검색 영역은 명시적으로 제외."""
    try:
        res = page.evaluate(
            """(unvCd) => {
                // 인기검색·자동완성·세션 팝업 영역은 명시적으로 배제
                const excludeSelectors = [
                    '#autoComplet', '.auto-complete', '[class*=popular]', '[id*=Popular]',
                    '[id*=popLogin]', '[class*=popup]', '#sample1', '[id*=Sample]',
                    '[id*=aiRcdPop]', '.lnb', '.header', '.gnb', '.top-search'
                ];
                const isExcluded = el => {
                    let cur = el;
                    while (cur) {
                        for (const sel of excludeSelectors) {
                            try { if (cur.matches && cur.matches(sel)) return true; } catch (e) {}
                        }
                        cur = cur.parentElement;
                    }
                    return false;
                };
                // 메인 컨텐츠 영역에서 대학명 패턴 찾기 (본교/분교 포함)
                const cands = Array.from(document.querySelectorAll('h1, h2, h3, strong, .univ-title, [class*=UnivName], [class*=schoolName], .content_top *'))
                    .filter(el => !isExcluded(el))
                    .map(el => (el.innerText || '').trim())
                    .filter(t => /(대학교|대학)(\\[본교\\]|\\[분교\\]|\\(.+\\))?$/.test(t) && t.length < 40 && !/자동로그아웃|로그인/.test(t));
                return cands[0] || null;
            }""",
            unv_cd,
        )
        if res:
            return res
    except Exception:
        pass
    return None


def _close_popups(page: Page) -> None:
    """공지·동의·세션 등 부수 팝업 닫기 (있을 때만)."""
    for selector_or_text in [
        "button:has-text('닫기')",
        "button:has-text('거부')",
        "[onclick*='closePopup']",
    ]:
        try:
            locs = page.locator(selector_or_text)
            for i in range(min(locs.count(), 5)):
                el = locs.nth(i)
                if el.is_visible():
                    el.click(timeout=1000)
                    page.wait_for_timeout(200)
        except Exception:
            pass


UNV_NAME_FALLBACK = {
    "0000069": "고려대학교[본교]",
    "0000070": "고려대학교(세종)[분교]",
}


def crawl(unv_cd: str, year: int = 2027, headless: bool = True, univ_name_hint: str | None = None) -> dict:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(viewport={"width": 1400, "height": 1500})
        page = ctx.new_page()

        url = DETAIL_URL.format(year=year, code=unv_cd)
        page.goto(url, wait_until="networkidle", timeout=30000)
        _close_popups(page)

        univ_name = _resolve_univ_name(page, unv_cd) or univ_name_hint or UNV_NAME_FALLBACK.get(unv_cd, "")

        page.locator("a:has-text('평가기준 및 입시결과')").first.click()
        page.wait_for_load_state("networkidle", timeout=15000)
        page.wait_for_timeout(1500)
        _close_popups(page)

        shot_path = SHOT_DIR / f"{unv_cd}_selection.png"
        page.screenshot(path=str(shot_path), full_page=True)

        tables = _extract_tables(page)

        result = {
            "unvCd": unv_cd,
            "univName": univ_name,
            "year": year,
            "source_url": page.url,
            "crawled_at": datetime.now().isoformat(timespec="seconds"),
            "screenshot": str(shot_path),
            "table_count": len(tables),
            "tables": tables,
        }

        raw_path = RAW_DIR / f"{unv_cd}.json"
        raw_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        browser.close()
        return result


if __name__ == "__main__":
    import sys
    cd = sys.argv[1] if len(sys.argv) > 1 else "0000069"
    res = crawl(cd)
    print(f"[OK] {res['univName']} ({cd}): {res['table_count']} tables → out/raw/{cd}.json")
