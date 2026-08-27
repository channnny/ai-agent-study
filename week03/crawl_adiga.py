"""
어디가 입시결과 크롤러 (전형 결과 탭)
- 대학코드(unvCd)와 검색연도(searchSyr)를 받아 전형 결과 테이블을 추출
- 출력: output/<대학명>/<전형유형>_전형결과.xlsx  +  MariaDB 저장
- 병렬 처리(MAX_WORKERS)로 속도 개선

실행:
  python3 crawl_adiga.py          # 엑셀만
  python3 crawl_adiga.py --db     # 엑셀 + DB 저장
"""

import re
import sys
import time
from datetime import datetime
from typing import List, Tuple
import pandas as pd
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SAVE_TO_DB = "--db" in sys.argv

BASE_URL = "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do"
# 신규 연도(예: searchSyr=2027의 2026학년도 결과)부터 어디가는 '전형 결과' 표를
# accordion 펼침 시 비동기(AJAX)로 로드한다. 정적 HTML엔 빈 껍데기만 온다.
AJAX_RESULT_URL = "https://www.adiga.kr/uct/acd/ade/criteriaAndResultItemNewAjax.do"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
OUTPUT_DIR = Path(__file__).parent / "output"
INPUT_FILE = Path(__file__).parent / "input" / "target_universities.csv"
OUTPUT_DIR.mkdir(exist_ok=True)

MAX_WORKERS = 3   # 배치 내 동시 요청 수
BATCH_SIZE = 10   # 한 번에 처리할 대학 수
BATCH_DELAY = 2   # 배치 사이 대기 시간 (초)


# ── 크롤링 ──────────────────────────────────────────────────────────────────

def fetch_page(unv_cd: str, search_syr: str) -> BeautifulSoup:
    params = {
        "menuId": "PCUVTINF2000",
        "unvCd": unv_cd,
        "searchSyr": search_syr,
    }
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def get_university_name(soup: BeautifulSoup) -> str:
    tag = soup.find("h4", class_="tclr")
    if tag:
        return tag.get_text(strip=True)
    title = soup.find("title")
    return title.get_text(strip=True).split("|")[0].strip() if title else "대학명_미상"


def _table_to_grid(table) -> List[List[str]]:
    """rowspan/colspan을 펼쳐 2D 텍스트 grid로. 병합 셀은 점유 칸을 같은 값으로 채움."""
    occupied: dict = {}
    grid: dict = {}
    for ri, tr in enumerate(table.find_all("tr")):
        ci = 0
        for cell in tr.find_all(["th", "td"]):
            while (ri, ci) in occupied:
                ci += 1
            try:
                rs = int(cell.get("rowspan", 1) or 1)
                cs = int(cell.get("colspan", 1) or 1)
            except ValueError:
                rs = cs = 1
            txt = cell.get_text(" ", strip=True)
            for dr in range(rs):
                for dc in range(cs):
                    occupied[(ri + dr, ci + dc)] = True
                    grid[(ri + dr, ci + dc)] = txt
            ci += cs
    if not grid:
        return []
    maxr = max(r for r, _ in grid) + 1
    maxc = max(c for _, c in grid) + 1
    return [[grid.get((r, c), "") for c in range(maxc)] for r in range(maxr)]


def _is_number(s) -> bool:
    s = str(s).replace(",", "").replace("%", "").strip()
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def _flatten_table(grid: List[List[str]], n_header_hint=None):
    """grid → (전형명, 평면 헤더 리스트, 데이터 행 리스트).

    어디가 입결 표는 다단 헤더(rowspan/colspan)다. 헤더 행을 식별해 세로로
    결합하고("학생부등급"+"70% cut" → "학생부등급 70% cut"), 전체 colspan을
    덮는 전형명 행은 별도로 분리한다. n_header_hint가 주어지면(예: <thead> 행 수)
    숫자비율 휴리스틱 대신 그 값을 헤더 행 수로 쓴다(다단 헤더에 '50%/70%'처럼
    숫자형 서브헤더가 있어도 정확히 분리).
    """
    ncol = max(len(r) for r in grid)

    if n_header_hint is not None:
        n_header = max(1, min(n_header_hint, len(grid) - 1))
    else:
        # 헤더 행 수 판정: 첫 컬럼 제외, 숫자 비율이 40% 이상이면 데이터 행
        n_header = 0
        for row in grid:
            vals = row[1:] if len(row) > 1 else row
            nums = sum(1 for v in vals if _is_number(v))
            ratio = nums / len(vals) if vals else 0
            if ratio >= 0.4:
                break
            n_header += 1
        n_header = max(1, min(n_header, len(grid) - 1))

    headers, data = grid[:n_header], grid[n_header:]

    # 전형명 행: col1~끝이 모두 같은 값(colspan 전체) = 전형 제목
    jeonghyeong = None
    title_rows = set()
    for hi, hrow in enumerate(headers):
        rest = [hrow[c] for c in range(1, ncol) if c < len(hrow) and hrow[c]]
        if len(rest) >= 2 and len(set(rest)) == 1:
            jeonghyeong = rest[0]
            title_rows.add(hi)

    # 평면 헤더: 전형명 행 제외, col별 위→아래 텍스트 결합(연속 중복 제거)
    flat = []
    for c in range(ncol):
        parts = []
        for hi, hrow in enumerate(headers):
            if hi in title_rows:
                continue
            v = hrow[c] if c < len(hrow) else ""
            if v and (not parts or parts[-1] != v):
                parts.append(v)
        flat.append(" ".join(parts) if parts else f"col{c}")

    return jeonghyeong, flat, data


def _fetch_result_ajax(onclick: str) -> BeautifulSoup:
    """동적 로딩(신규 연도) 전형결과를 AJAX로 받아 fragment soup 반환.

    버튼 onclick="fnItemSearchInclude(this, event, syr, unvCd, upCd, compUnvCd)"
    에서 인자를 뽑아 criteriaAndResultItemNewAjax.do로 POST한다.
    """
    m = re.search(
        r'fnItemSearchInclude\([^,]+,[^,]+,\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)"',
        onclick or "")
    if not m:
        return None
    syr, unv_cd, up_cd, comp = m.groups()
    headers = {**HEADERS, "X-Requested-With": "XMLHttpRequest", "Referer": BASE_URL}
    resp = requests.post(
        AJAX_RESULT_URL,
        data={"searchSyr": syr, "unvCd": unv_cd,
              "tsrdCmphSlcnArtclUpCd": up_cd, "compUnvCd": comp},
        headers=headers, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _tables_from_soup(container: BeautifulSoup, tab_name: str) -> List[pd.DataFrame]:
    """fragment/accordion 내부 soup → 전형결과 DataFrame 리스트."""
    tables = []
    for table in container.find_all("table"):
        grid = _table_to_grid(table)
        if not grid or len(grid) < 2:
            continue
        # <thead>가 있으면 헤더 행 수를 정확히 알 수 있어 다단 헤더를 깔끔히 분리.
        thead = table.find("thead")
        n_hint = len(thead.find_all("tr")) if thead else None
        jeonghyeong, flat_hdr, data = _flatten_table(grid, n_hint)
        if not data:
            continue
        ncol = len(flat_hdr)
        data = [r + [""] * (ncol - len(r)) for r in data]  # 길이 보정
        df = pd.DataFrame(data, columns=flat_hdr)
        if "전형" not in df.columns:
            df.insert(0, "전형", jeonghyeong or tab_name)
        tables.append(df)
    return tables


def extract_result_tables(soup: BeautifulSoup) -> List[dict]:
    tab_btns = soup.find_all("button", class_="btnTab")
    if not tab_btns:
        return []   # 전형 탭이 없는 대학(미게시/구조상이) → 빈 결과
    ul = tab_btns[0].find_parent("ul")
    tab_panels = ul.find_next_siblings("div", class_="tabCon")

    results = []
    for btn, panel in zip(tab_btns, tab_panels):
        tab_name = btn.get_text(strip=True)

        # '전형 결과' 아코디언 검출 — 버튼 '텍스트' 기준(연도별 마크업 차이 흡수).
        # 구버전은 제목이 span.qType, 신규(2027~)는 span.h4라 클래스 의존 불가.
        result_btn = None
        for acc_btn in panel.find_all("button", class_="accordionBtn"):
            if "전형 결과" in acc_btn.get_text():
                result_btn = acc_btn
                break
        if not result_btn:
            continue

        acc_con = result_btn.find_next_sibling("div", class_="accordionCon")
        inner_soup = BeautifulSoup(acc_con.decode_contents(), "html.parser") if acc_con else None

        # 정적 표가 비어 있으면(신규 연도 = 동적 로딩) AJAX로 가져온다.
        if inner_soup is None or not inner_soup.find("table"):
            frag = _fetch_result_ajax(result_btn.get("onclick", ""))
            if frag is not None:
                inner_soup = frag

        tables = _tables_from_soup(inner_soup, tab_name) if inner_soup else []

        if tables:
            results.append({"tab": tab_name, "tables": tables})
        elif inner_soup:
            # 표가 없으면 이미지로 전형결과를 올린 대학(예: 가톨릭꽃동네대).
            imgs = [im.get("src", "") for im in inner_soup.find_all("img")
                    if "astFileHandler" in (im.get("src", "") or "")]
            if imgs:
                results.append({"tab": tab_name, "tables": [], "images": imgs})

    return results


# ── 저장 ────────────────────────────────────────────────────────────────────

def save_to_excel(unv_cd: str, univ_name: str, tab_name: str, tables: list) -> Path:
    # 폴더명을 unvCd 기반으로 → 캠퍼스 분리 대학(같은 univ_name)의 덮어쓰기 방지 +
    # 평가 단계에서 골든셋 unvCd와 정확히 매칭 가능.
    safe_tab = re.sub(r"[^\w가-힣]", "", tab_name)
    safe_univ = re.sub(r"[^\w가-힣]", "", univ_name)
    univ_dir = OUTPUT_DIR / f"{unv_cd}_{safe_univ}"
    univ_dir.mkdir(exist_ok=True)
    path = univ_dir / f"{safe_tab}_전형결과.xlsx"

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for i, df in enumerate(tables):
            df.to_excel(writer, sheet_name=f"표{i+1}"[:31], index=False)

    return path


# ── 단일 대학 처리 ───────────────────────────────────────────────────────────

def crawl(unv_cd: str, search_syr: str) -> dict:
    """한 대학을 크롤링하고 결과 요약 dict를 반환한다."""
    t0 = time.perf_counter()
    crawled_at = datetime.now()

    soup = fetch_page(unv_cd, search_syr)
    univ_name = get_university_name(soup)
    results = extract_result_tables(soup)

    # DB 저장
    if SAVE_TO_DB:
        from db.db import get_conn, upsert_university, insert_results
        with get_conn() as conn:
            upsert_university(conn, unv_cd, univ_name, crawled_at)
            for item in results:
                for df in item["tables"]:
                    rows = df.to_dict(orient="records")
                    insert_results(conn, unv_cd, search_syr, item["tab"], rows, crawled_at)

    # 엑셀 저장 + 이미지 케이스 다운로드
    saved = []
    n_images = 0
    for item in results:
        if item["tables"]:
            path = save_to_excel(unv_cd, univ_name, item["tab"], item["tables"])
            total_rows = sum(len(df) for df in item["tables"])
            saved.append({"tab": item["tab"], "tables": len(item["tables"]), "rows": total_rows, "file": path.name})
        elif item.get("images"):
            # 전형결과가 이미지인 대학 → 이미지 다운로드 + OCR 필요 표시.
            # (표 크롤링으로는 추출 불가. 비전 모델/OCR로 후처리 → 캐노니컬화)
            n_images += _save_images(unv_cd, univ_name, item["tab"], item["images"])

    elapsed = time.perf_counter() - t0
    return {"unv_cd": unv_cd, "univ_name": univ_name, "saved": saved,
            "n_images": n_images, "elapsed": elapsed}


def _save_images(unv_cd: str, univ_name: str, tab_name: str, image_urls: list) -> int:
    """전형결과 이미지 다운로드 + OCR_REQUIRED 마커. 반환: 저장 이미지 수."""
    safe_univ = re.sub(r"[^\w가-힣]", "", univ_name)
    safe_tab = re.sub(r"[^\w가-힣]", "", tab_name)
    img_dir = OUTPUT_DIR / f"{unv_cd}_{safe_univ}" / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    cnt = 0
    for i, url in enumerate(image_urls, 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            (img_dir / f"{safe_tab}_{i}.png").write_bytes(r.content)
            cnt += 1
        except Exception:
            pass
    # OCR 필요 마커 (비전 모델 후처리 대상)
    (img_dir / "OCR_REQUIRED.txt").write_text(
        f"{univ_name}({unv_cd}) {tab_name}: 전형결과가 이미지 {cnt}장.\n"
        "표 크롤링 불가 → 비전 모델/OCR로 캐노니컬화 필요.\n",
        encoding="utf-8")
    return cnt


# ── 입력 로드 ────────────────────────────────────────────────────────────────

def load_targets(path: Path) -> List[Tuple[str, str]]:
    df = pd.read_csv(path, dtype=str).fillna("")
    return [(row["unv_cd"].strip(), row["search_syr"].strip()) for _, row in df.iterrows()]


# ── 메인 ────────────────────────────────────────────────────────────────────

def run_batch(batch: List[Tuple[str, str]], batch_no: int, total_batches: int) -> Tuple[list, list]:
    success, failed = [], []
    print(f"\n── 배치 {batch_no}/{total_batches} ({len(batch)}건) ──")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(crawl, unv_cd, syr): (unv_cd, syr) for unv_cd, syr in batch}
        for future in as_completed(futures):
            unv_cd, _ = futures[future]
            try:
                r = future.result()
                success.append(r)
                print(f"  [{r['elapsed']:.1f}s] {r['univ_name']} (unvCd={r['unv_cd']})")
                for s in r["saved"]:
                    print(f"    [{s['tab']}] 테이블 {s['tables']}개, 행 {s['rows']}개 → {s['file']}")
                if r.get("n_images"):
                    print(f"    이미지 {r['n_images']}장 다운로드 (OCR 필요 — 비전 모델 후처리)")
                if not r["saved"] and not r.get("n_images"):
                    print("    전형 결과 데이터 없음")
            except Exception as e:
                failed.append(unv_cd)
                print(f"  [오류] unvCd={unv_cd}: {e}")

    return success, failed


if __name__ == "__main__":
    targets = load_targets(INPUT_FILE)
    batches = [targets[i:i + BATCH_SIZE] for i in range(0, len(targets), BATCH_SIZE)]

    print(f"입력 파일 : {INPUT_FILE.name} ({len(targets)}건)")
    print(f"배치 구성 : {len(batches)}배치 × {BATCH_SIZE}건, 동시 요청 {MAX_WORKERS}개")

    total_start = time.perf_counter()
    all_success, all_failed = [], []

    for i, batch in enumerate(batches, 1):
        s, f = run_batch(batch, i, len(batches))
        all_success.extend(s)
        all_failed.extend(f)
        if i < len(batches):
            print(f"  → {BATCH_DELAY}초 대기 후 다음 배치...")
            time.sleep(BATCH_DELAY)

    total_elapsed = time.perf_counter() - total_start

    print(f"\n{'='*50}")
    print(f"총 소요 시간  : {total_elapsed:.1f}s")
    print(f"성공          : {len(all_success)}건")
    if all_success:
        times = [r["elapsed"] for r in all_success]
        print(f"대학별 평균   : {sum(times)/len(times):.1f}s  (최소 {min(times):.1f}s / 최대 {max(times):.1f}s)")
    if all_failed:
        print(f"실패          : {len(all_failed)}건 → {all_failed}")
    print(f"{'='*50}")
