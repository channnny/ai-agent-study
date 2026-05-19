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


def extract_result_tables(soup: BeautifulSoup) -> List[dict]:
    tab_btns = soup.find_all("button", class_="btnTab")
    ul = tab_btns[0].find_parent("ul")
    tab_panels = ul.find_next_siblings("div", class_="tabCon")

    results = []
    for btn, panel in zip(tab_btns, tab_panels):
        tab_name = btn.get_text(strip=True)

        result_btn = None
        for acc_btn in panel.find_all("button", class_="accordionBtn"):
            span = acc_btn.find("span", class_="qType")
            if span and "전형 결과" in span.get_text():
                result_btn = acc_btn
                break

        if not result_btn:
            continue

        acc_con = result_btn.find_next_sibling("div", class_="accordionCon")
        inner_soup = BeautifulSoup(acc_con.decode_contents(), "html.parser")

        tables = []
        for table in inner_soup.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cells = [td.get_text(separator=" ", strip=True) for td in tr.find_all(["td", "th"])]
                if any(cells):
                    rows.append(cells)
            if not rows:
                continue
            max_cols = max(len(r) for r in rows)
            padded = [r + [""] * (max_cols - len(r)) for r in rows]
            df = pd.DataFrame(padded[1:], columns=padded[0])
            tables.append(df)

        if tables:
            results.append({"tab": tab_name, "tables": tables})

    return results


# ── 저장 ────────────────────────────────────────────────────────────────────

def save_to_excel(univ_name: str, tab_name: str, tables: list) -> Path:
    safe_tab = re.sub(r"[^\w가-힣]", "", tab_name)
    safe_univ = re.sub(r"[^\w가-힣]", "", univ_name)
    univ_dir = OUTPUT_DIR / safe_univ
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

    # 엑셀 저장
    saved = []
    for item in results:
        path = save_to_excel(univ_name, item["tab"], item["tables"])
        total_rows = sum(len(df) for df in item["tables"])
        saved.append({"tab": item["tab"], "tables": len(item["tables"]), "rows": total_rows, "file": path.name})

    elapsed = time.perf_counter() - t0
    return {"unv_cd": unv_cd, "univ_name": univ_name, "saved": saved, "elapsed": elapsed}


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
                if not r["saved"]:
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
