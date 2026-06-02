"""adiga 입시 데이터 수집 에이전트 — 메인 실행 스크립트 (T0~T7)

사용법:
    python run.py --year 2027 --mode full
    python run.py --year 2027 --mode partial --unvcd 0000063 0000019
    python run.py --year 2027 --mode full --force
    python run.py --year 2027 --mode full --skip-llm   # T4 건너뜀 (결정론적만)

이 스크립트는 T0(준비)~T3(룰 매핑), T5(엑셀빌드)~T7(리포트)를 실행한다.
T4(LLM 정규화)는 CLAUDE.md의 서브에이전트 지침에 따라 Claude Code가 처리한다.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

# ─────────────────────────────────────────────
# 경로 상수
# ─────────────────────────────────────────────
ROOT = Path(__file__).parent
INPUT_DIR    = ROOT / "input"
OUTPUT_DIR   = ROOT / "output"
SKILLS_DIR   = ROOT / ".claude" / "skills"

SCHEMA_PATH   = INPUT_DIR / "schema_v3.yaml"
GOLDEN_PATH   = INPUT_DIR / "2025_어디가입결_통합본.xlsx"
UNIV_CSV_PATH = INPUT_DIR / "universities.csv"
STATE_PATH    = OUTPUT_DIR / "run_state.json"
ERRORS_PATH   = OUTPUT_DIR / "logs" / "error_log.json"
NEW_COLS_PATH = OUTPUT_DIR / "logs" / "new_columns_proposals.json"


def run_cmd(cmd: list[str], desc: str) -> int:
    print(f"\n{'─'*60}")
    print(f"[실행] {desc}")
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, check=False)
    return result.returncode


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_universities(mode: str, unvcd_filter: list[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    if UNIV_CSV_PATH.exists():
        with open(UNIV_CSV_PATH, encoding="utf-8") as f:
            # 주석 행(#으로 시작) 및 빈 줄 건너뛰기
            lines = [l for l in f if not l.lstrip().startswith("#") and l.strip()]
        import io
        for row in csv.DictReader(io.StringIO("".join(lines))):
            code = row.get("unvCd", "").strip()
            name = row.get("대학명", code).strip()
            if code:
                    result[code] = name
    else:
        # CSV 없으면 8개 기본 대학
        result = {
            "0000063": "가천대학교",
            "0000019": "서울대학교",
            "0000027": "제주대학교",
            "0000149": "연세대학교",
            "0000069": "고려대학교",
            "0000014": "부산대학교",
            "0000005": "경북대학교",
            "0000245": "남서울대학교",
        }

    if mode == "partial" and unvcd_filter:
        result = {k: v for k, v in result.items() if k in unvcd_filter}

    return result


def t0_prepare(args) -> dict[str, str]:
    """T0: 검증 + 디렉토리 생성 + 대학 리스트 결정."""
    print("\n" + "="*60)
    print("[T0 준비] 시작")

    # 필수 파일 존재 확인
    if not SCHEMA_PATH.exists():
        print(f"[오류] 스키마 파일 없음: {SCHEMA_PATH}")
        sys.exit(1)

    # 스키마 파싱 검증
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    sheets = schema.get("sheets", {})
    if len(sheets) < 4:
        print(f"[오류] 스키마에 4시트 정의 없음: {list(sheets.keys())}")
        sys.exit(1)

    # 골든셋 확인
    if not GOLDEN_PATH.exists():
        print(f"[경고] 골든셋 파일 없음: {GOLDEN_PATH} (T6 평가 불가)")

    # 디렉토리 생성
    for d in [
        OUTPUT_DIR / "raw_html",
        OUTPUT_DIR / "parsed",
        OUTPUT_DIR / "mapped",
        OUTPUT_DIR / "normalized",
        OUTPUT_DIR / "per_university",
        OUTPUT_DIR / "logs",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # 대학 리스트 결정
    universities = load_universities(args.mode, args.unvcd)
    if not universities:
        print("[오류] 대학 리스트가 비어있음")
        sys.exit(1)

    print(f"[T0 준비] 완료 — 대학 {len(universities)}개, year={args.year}, mode={args.mode}")
    return universities


def t1_crawl(universities: dict[str, str], args) -> None:
    """T1: 크롤링."""
    crawl_script = SKILLS_DIR / "adiga-crawler" / "scripts" / "crawl.py"
    unvcds = list(universities.keys())
    cmd = [
        sys.executable, str(crawl_script),
        "--unvcd", *unvcds,
        "--year", str(args.year),
        "--workers", str(args.workers),
        "--output", str(OUTPUT_DIR / "raw_html"),
        "--state", str(STATE_PATH),
        "--errors", str(ERRORS_PATH),
    ]
    if args.force:
        cmd.append("--force")
    rc = run_cmd(cmd, f"T1 크롤링 ({len(unvcds)}개 대학)")
    if rc != 0:
        print("[경고] 일부 대학 크롤링 실패 (error_log.json 참조)")


def t2_parse(universities: dict[str, str], args) -> None:
    """T2: HTML 파싱."""
    parse_script = SKILLS_DIR / "html-parser" / "scripts" / "parse.py"
    state = load_state()

    for unvcd, univ_name in universities.items():
        html_path = OUTPUT_DIR / "raw_html" / f"{unvcd}.html"
        if not html_path.exists():
            print(f"  [{unvcd}] HTML 파일 없음 (크롤링 실패), 스킵")
            continue

        if not args.force and state.get(unvcd, {}).get("status") == "parsed":
            print(f"  [{unvcd}] 이미 파싱됨 (스킵)")
            continue

        cmd = [
            sys.executable, str(parse_script),
            "--unvcd", unvcd,
            "--univ", univ_name,
            "--html", str(html_path),
            "--output", str(OUTPUT_DIR / "parsed" / f"{unvcd}.json"),
            "--errors", str(ERRORS_PATH),
        ]
        rc = run_cmd(cmd, f"T2 파싱 [{unvcd}] {univ_name}")

        state.setdefault(unvcd, {})
        if rc == 0:
            state[unvcd]["status"] = "parsed"
        else:
            state[unvcd]["status"] = "error_parse"
        state[unvcd]["last_updated"] = datetime.now().isoformat(timespec="seconds")
        save_state(state)


def t3_map(universities: dict[str, str], args) -> None:
    """T3: 룰 기반 매핑."""
    map_script = SKILLS_DIR / "rule-mapper" / "scripts" / "map_columns.py"
    state = load_state()

    for unvcd in universities:
        parsed_path = OUTPUT_DIR / "parsed" / f"{unvcd}.json"
        if not parsed_path.exists():
            print(f"  [{unvcd}] parsed 파일 없음, 스킵")
            continue

        if not args.force and state.get(unvcd, {}).get("status") == "mapped":
            print(f"  [{unvcd}] 이미 매핑됨 (스킵)")
            continue

        cmd = [
            sys.executable, str(map_script),
            "--unvcd", unvcd,
            "--parsed", str(parsed_path),
            "--schema", str(SCHEMA_PATH),
            "--output", str(OUTPUT_DIR / "mapped" / f"{unvcd}.json"),
        ]
        rc = run_cmd(cmd, f"T3 룰매핑 [{unvcd}]")

        state.setdefault(unvcd, {})
        state[unvcd]["status"] = "mapped" if rc == 0 else "error_map"
        state[unvcd]["last_updated"] = datetime.now().isoformat(timespec="seconds")
        save_state(state)


def t4_note() -> None:
    """T4: LLM 정규화는 Claude Code 서브에이전트가 처리."""
    print("\n" + "="*60)
    print("[T4 LLM 정규화] 안내")
    print("  이 단계는 Claude Code 에이전트가 직접 처리합니다.")
    print("  CLAUDE.md §4 지침에 따라:")
    print("  - normalizer-result 서브에이전트: susi_result/jeongsi_result unmapped 셀 분류")
    print("  - normalizer-eval 서브에이전트: susi_eval/jeongsi_eval raw_text 정규화")
    print("")
    print("  --skip-llm 옵션을 사용하면 T4를 건너뛰고 mapped를 normalized로 복사합니다.")


def t4_skip_copy(universities: dict[str, str], force: bool = False) -> None:
    """T4 스킵: mapped → normalized 복사."""
    print("\n[T4 스킵] mapped 파일을 normalized로 복사합니다.")
    for unvcd in universities:
        mapped_path = OUTPUT_DIR / "mapped" / f"{unvcd}.json"
        norm_path   = OUTPUT_DIR / "normalized" / f"{unvcd}.json"
        if not mapped_path.exists():
            continue
        if norm_path.exists() and not force:
            continue
        mapped = json.loads(mapped_path.read_text(encoding="utf-8"))
        # mapped 구조 → normalized 구조 변환
        normalized: dict[str, list] = {}
        for sheet_name, sheet_data in mapped.items():
            if isinstance(sheet_data, dict):
                normalized[sheet_name] = sheet_data.get("mapped", [])
            else:
                normalized[sheet_name] = sheet_data
        norm_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [{unvcd}] 복사 완료")


def t5_build(args) -> int:
    """T5: 엑셀 빌드."""
    build_script = SKILLS_DIR / "xlsx-builder" / "scripts" / "build.py"
    out_xlsx = OUTPUT_DIR / f"adiga_{args.year}.xlsx"
    cmd = [
        sys.executable, str(build_script),
        "--year", str(args.year),
        "--normalized-dir", str(OUTPUT_DIR / "normalized"),
        "--per-univ-dir", str(OUTPUT_DIR / "per_university"),
        "--output", str(out_xlsx),
        "--schema", str(SCHEMA_PATH),
        "--errors", str(ERRORS_PATH),
        "--new-columns", str(NEW_COLS_PATH),
    ]
    rc = run_cmd(cmd, "T5 엑셀빌드")
    if rc != 0:
        print("[오류] T5 엑셀빌드 실패 — 종료")
        sys.exit(1)
    return rc


def t6_evaluate(args) -> None:
    """T6: 골든셋 평가."""
    if not GOLDEN_PATH.exists():
        print("\n[T6 평가] 골든셋 없음 → 스킵")
        return
    eval_script = SKILLS_DIR / "evaluator" / "scripts" / "evaluate.py"
    out_xlsx    = OUTPUT_DIR / f"adiga_{args.year}.xlsx"
    cmd = [
        sys.executable, str(eval_script),
        "--golden",    str(GOLDEN_PATH),
        "--predicted", str(out_xlsx),
        "--out",       str(OUTPUT_DIR / "evaluation_report.xlsx"),
    ]
    rc = run_cmd(cmd, "T6 평가")
    if rc != 0:
        print("[경고] T6 평가 실패 → 스킵")


def t7_report(args) -> None:
    """T7: 리포트 생성."""
    report_script = SKILLS_DIR / "reporter" / "scripts" / "report.py"
    cmd = [
        sys.executable, str(report_script),
        "--normalized-dir", str(OUTPUT_DIR / "normalized"),
        "--schema",         str(SCHEMA_PATH),
        "--eval-report",    str(OUTPUT_DIR / "evaluation_report.xlsx"),
        "--errors",         str(ERRORS_PATH),
        "--new-columns",    str(NEW_COLS_PATH),
        "--out",            str(OUTPUT_DIR / "validation_report.md"),
    ]
    rc = run_cmd(cmd, "T7 리포트")
    if rc != 0:
        print("[경고] T7 리포트 실패 → 스킵")


def main():
    ap = argparse.ArgumentParser(description="adiga 입시 데이터 수집 에이전트")
    ap.add_argument("--year",    type=int, default=2027, help="searchSyr 값")
    ap.add_argument("--mode",   choices=["full", "partial"], default="full")
    ap.add_argument("--unvcd",  nargs="*", default=None, help="partial 모드 대학 코드")
    ap.add_argument("--force",  action="store_true", help="완료 상태 무시하고 재실행")
    ap.add_argument("--workers", type=int, default=3, help="동시 크롤링 워커 수")
    ap.add_argument("--skip-llm", action="store_true",
                    help="T4 LLM 정규화 건너뜀 (mapped → normalized 복사)")
    ap.add_argument("--skip-eval", action="store_true", help="T6 평가 건너뜀")
    ap.add_argument("--start-from", choices=["t0","t1","t2","t3","t4","t5","t6","t7"],
                    default="t0", help="특정 단계부터 시작")
    args = ap.parse_args()

    start = args.start_from

    # T0: 준비
    universities = t0_prepare(args)

    # T1: 크롤링
    if start <= "t1":
        t1_crawl(universities, args)

    # T2: 파싱
    if start <= "t2":
        t2_parse(universities, args)

    # T3: 룰 매핑
    if start <= "t3":
        t3_map(universities, args)

    # T4: LLM 정규화
    if start <= "t4":
        if args.skip_llm:
            t4_skip_copy(universities, force=args.force)
        else:
            t4_note()
            print("\n[안내] T4 완료 후 다시 run.py --start-from t5 로 실행하세요.")
            return

    # T5: 엑셀 빌드
    if start <= "t5":
        t5_build(args)

    # T6: 평가
    if start <= "t6" and not args.skip_eval:
        t6_evaluate(args)

    # T7: 리포트
    if start <= "t7":
        t7_report(args)

    print("\n" + "="*60)
    print(f"[완료] 전체 워크플로우 완료 — output/ 디렉토리 확인")
    print(f"  통합 워크북: output/adiga_{args.year}.xlsx")
    print(f"  평가 리포트: output/evaluation_report.xlsx")
    print(f"  검증 리포트: output/validation_report.md")


if __name__ == "__main__":
    main()
