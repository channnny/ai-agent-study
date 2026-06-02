"""adiga 페이지 크롤러 — T1 단계

사용법:
    python crawl.py --unvcd 0000063 0000019 --year 2027
    python crawl.py --csv input/universities.csv --year 2027 --workers 3
    python crawl.py --csv input/universities.csv --year 2027 --force

출력:
    output/raw_html/{unvCd}.html
    output/run_state.json  (갱신)
    output/logs/error_log.json  (실패 시)
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

BASE_URL = "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)
MIN_HTML_BYTES = 10_240  # 10KB


def load_universities_csv(csv_path: str) -> dict[str, str]:
    result = {}
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("unvCd"):
                result[row["unvCd"].strip()] = row.get("대학명", row["unvCd"]).strip()
    return result


def load_state(state_path: Path) -> dict:
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return {}


def save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def append_error(errors_path: Path, entry: dict) -> None:
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    errors: list = []
    if errors_path.exists():
        try:
            errors = json.loads(errors_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    errors.append(entry)
    errors_path.write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_page(unvcd: str, year: int, max_retries: int = 3) -> Optional[str]:
    params = {"menuId": "PCUVTINF2000", "unvCd": unvcd, "searchSyr": year}
    headers = {"User-Agent": USER_AGENT}

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(BASE_URL, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            if attempt == max_retries:
                raise
            delay = 2 ** attempt
            print(f"  [{unvcd}] 재시도 {attempt}/{max_retries} ({delay}s 대기): {exc}")
            time.sleep(delay)
    return None


def validate_html(html: str, unvcd: str) -> tuple[bool, str]:
    if len(html.encode("utf-8")) < MIN_HTML_BYTES:
        return False, f"HTML 크기 부족 ({len(html.encode())} bytes < {MIN_HTML_BYTES})"
    if "대입정보포털" not in html:
        return False, "title에 '대입정보포털' 미포함 (빈 페이지 또는 차단)"
    return True, "ok"


def crawl_one(
    unvcd: str,
    univ_name: str,
    year: int,
    output_dir: Path,
    state: dict,
    state_path: Path,
    errors_path: Path,
    force: bool,
) -> bool:
    if not force and state.get(unvcd, {}).get("status") == "done":
        print(f"  [{unvcd}] {univ_name}: 이미 완료 (스킵)")
        return True

    state.setdefault(unvcd, {})["status"] = "fetching"
    state[unvcd]["last_updated"] = datetime.now().isoformat(timespec="seconds")
    save_state(state_path, state)

    print(f"[{unvcd}] {univ_name}: 크롤링 시작 (year={year})")
    try:
        html = fetch_page(unvcd, year)
        if html is None:
            raise RuntimeError("fetch_page returned None")

        ok, reason = validate_html(html, unvcd)
        if not ok:
            raise ValueError(reason)

        out_file = output_dir / f"{unvcd}.html"
        out_file.write_text(html, encoding="utf-8")
        print(f"  [{unvcd}] {univ_name}: 완료 ({len(html.encode()):,} bytes)")

        state[unvcd]["status"] = "fetched"
        state[unvcd]["university"] = univ_name
        state[unvcd]["last_updated"] = datetime.now().isoformat(timespec="seconds")
        save_state(state_path, state)
        return True

    except Exception as exc:
        msg = str(exc)
        print(f"  [{unvcd}] {univ_name}: 실패 — {msg}")
        state[unvcd]["status"] = "error_fetch"
        state[unvcd]["last_updated"] = datetime.now().isoformat(timespec="seconds")
        save_state(state_path, state)
        append_error(
            errors_path,
            {
                "unvCd": unvcd,
                "university": univ_name,
                "stage": "T1",
                "error": msg,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            },
        )
        return False


def main():
    ap = argparse.ArgumentParser(description="adiga 페이지 크롤러")
    ap.add_argument("--unvcd", nargs="*", default=None, help="대학 코드 리스트")
    ap.add_argument("--csv", default=None, help="universities.csv 경로")
    ap.add_argument("--year", type=int, default=2027)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--output", default="output/raw_html")
    ap.add_argument("--state", default="output/run_state.json")
    ap.add_argument("--errors", default="output/logs/error_log.json")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    # 대학 리스트 결정
    if args.csv:
        universities = load_universities_csv(args.csv)
        if args.unvcd:
            universities = {k: v for k, v in universities.items() if k in args.unvcd}
    elif args.unvcd:
        universities = {u: u for u in args.unvcd}
    else:
        ap.error("--csv 또는 --unvcd 중 하나는 필수")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = Path(args.state)
    errors_path = Path(args.errors)

    state = load_state(state_path)

    print(f"[T1 크롤링] 시작: {len(universities)}개 대학, year={args.year}, workers={args.workers}")

    success = 0
    fail = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                crawl_one,
                unvcd, univ_name, args.year,
                output_dir, state, state_path, errors_path, args.force,
            ): (unvcd, univ_name)
            for unvcd, univ_name in universities.items()
        }
        for future in as_completed(futures):
            unvcd, univ_name = futures[future]
            try:
                ok = future.result()
                if ok:
                    success += 1
                else:
                    fail += 1
            except Exception as exc:
                fail += 1
                print(f"  [{unvcd}] 예외: {exc}")

    print(f"\n[T1 크롤링] 완료: 성공 {success}개, 실패 {fail}개")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
