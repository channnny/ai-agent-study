"""W05 평가 CLI.

사용법:
    python -m src.cli                                 # 전체 3인
    python -m src.cli --persons yuchan,lee            # 일부
    python -m src.cli --report-name custom.xlsx       # 출력 파일명 지정
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime
from pathlib import Path

# 패키지 import 가능하게 path 보강 (직접 python -m src.cli도 지원)
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "src"

from .config import (
    GOLDEN_PATH, NORMALIZATION_PATH, OUTPUT_DIR,
    YUCHAN_OUTPUT_DIR, LEE_PER_UNIV_DIR, LIM_OUTPUTS_DIR,
    PERSONS, PERSON_KOR,
)
from .normalizer import Normalizer
from .adapters import golden as adp_golden, yuchan as adp_yuchan, leejihyun as adp_lee, limjihyun as adp_lim
from .matcher import evaluate_person, PersonResult
from .reporter import write_report


def main():
    ap = argparse.ArgumentParser(description="W05 정확도 비교 프로그램")
    ap.add_argument("--persons", default=",".join(PERSONS),
                    help=f"평가 대상 사람 (콤마 구분). 가능: {','.join(PERSONS)}")
    ap.add_argument("--report-name", default=None,
                    help="출력 파일명 (기본: evaluation_report_<timestamp>.xlsx)")
    args = ap.parse_args()

    persons = [p.strip() for p in args.persons.split(",") if p.strip()]
    invalid = [p for p in persons if p not in PERSONS]
    if invalid:
        print(f"❌ 잘못된 person: {invalid}. 가능: {PERSONS}", file=sys.stderr)
        sys.exit(1)

    # ─────────────────────────────────────
    # 1. 정규화기 + 골든셋 로드
    # ─────────────────────────────────────
    print("="*60)
    print(f"W05 정확도 비교 시작 — 평가 대상: {persons}")
    print("="*60)

    if not GOLDEN_PATH.exists():
        print(f"❌ 골든셋 없음: {GOLDEN_PATH}", file=sys.stderr)
        sys.exit(1)
    if not NORMALIZATION_PATH.exists():
        print(f"❌ 정규화 사전 없음: {NORMALIZATION_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"\n[1/4] 정규화 사전 로드: {NORMALIZATION_PATH.name}")
    normalizer = Normalizer(NORMALIZATION_PATH)

    print(f"\n[2/4] 골든셋 로드: {GOLDEN_PATH.name}")
    golden = adp_golden.load(GOLDEN_PATH, normalizer)
    print(f"  → {len(golden)}개 대학, {sum(len(df) for df in golden.values())}행")

    # ─────────────────────────────────────
    # 2. 사람별 산출물 로드
    # ─────────────────────────────────────
    print(f"\n[3/4] 사람별 산출물 로드")
    person_data: dict[str, dict] = {}
    if "yuchan" in persons:
        print(f"  - 유찬: {YUCHAN_OUTPUT_DIR}")
        data = adp_yuchan.load(YUCHAN_OUTPUT_DIR, normalizer)
        print(f"    → {len(data)}개 대학, {sum(len(df) for df in data.values())}행")
        person_data["yuchan"] = data
    if "lee" in persons:
        print(f"  - 이지현: {LEE_PER_UNIV_DIR}")
        data = adp_lee.load(LEE_PER_UNIV_DIR, normalizer)
        print(f"    → {len(data)}개 대학, {sum(len(df) for df in data.values())}행")
        person_data["lee"] = data
    if "lim" in persons:
        print(f"  - 임지현: {LIM_OUTPUTS_DIR}")
        data = adp_lim.load(LIM_OUTPUTS_DIR, normalizer)
        print(f"    → {len(data)}개 대학, {sum(len(df) for df in data.values())}행")
        person_data["lim"] = data

    # ─────────────────────────────────────
    # 3. 사람별 평가
    # ─────────────────────────────────────
    print(f"\n[4/4] 평가 + 리포트 생성")
    results: list[PersonResult] = []
    for person in persons:
        if person not in person_data:
            continue
        print(f"  - {PERSON_KOR[person]}({person}) 평가 중...")
        r = evaluate_person(golden, person_data[person], person)
        s = r.summary
        print(f"      PK={s['pk_match_rate']*100:.2f}%  Cell={s['cell_match_rate']*100:.2f}%  "
              f"matched={s['n_matched']:,}/{s['n_golden_total']:,}  "
              f"missing_univ={s['n_missing_univ']}/{len(r.by_university)}")
        results.append(r)

    # ─────────────────────────────────────
    # 4. 리포트 출력
    # ─────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = args.report_name or f"evaluation_report_{ts}.xlsx"
    output_path = OUTPUT_DIR / fname
    write_report(results, output_path)

    # 최종 한 줄 요약
    print("\n" + "="*60)
    print("최종 요약:")
    for r in results:
        s = r.summary
        dod = "✓" if (s["pk_dod_pass"] and s["cell_dod_pass"]) else "✗"
        print(f"  {dod} {PERSON_KOR[r.person]:>3s}: PK {s['pk_match_rate']*100:.1f}% / "
              f"Cell {s['cell_match_rate']*100:.1f}% / coverage {s['coverage_pct']:.1f}%")
    print("="*60)


if __name__ == "__main__":
    main()
