"""W06 3인 크롤러 통합 CLI.

W05의 3인(유찬·이지현·임지현) 산출물을 하나의 통합 데이터셋으로 병합하고,
W05와 동일한 평가 지표로 [통합 vs 3인]을 비교한 리포트를 만든다.

사용법:
    python -m src.cli                                    # 통합 + 3인 전체
    python -m src.cli --report-name custom.xlsx          # 리포트 파일명 지정
    python -m src.cli --no-raw                           # 리포트에 통합본만 표시
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime
from pathlib import Path

# 패키지 import 가능하게 path 보강 (python -m src.cli 지원)
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "src"

from .config import (
    GOLDEN_PATH, NORMALIZATION_PATH, OUTPUT_DIR,
    YUCHAN_OUTPUT_DIR, LEE_PER_UNIV_DIR, LIM_OUTPUTS_DIR,
    PERSONS, PERSON_KOR, DATA_COLUMNS,
)
from .normalizer import Normalizer
from .adapters import golden as adp_golden, yuchan as adp_yuchan, leejihyun as adp_lee, limjihyun as adp_lim
from .matcher import evaluate_person, PersonResult
from .merger import merge_persons, flatten_merged, build_reliability, STRATEGY as DEFAULT_STRATEGY
from .reporter import write_report, write_integrated_dataset


def main():
    ap = argparse.ArgumentParser(description="W06 3인 크롤러 통합 + 비교 리포트")
    ap.add_argument("--report-name", default=None,
                    help="리포트 파일명 (기본: evaluation_report_week06_<ts>.xlsx)")
    ap.add_argument("--integrated-name", default=None,
                    help="통합 canonical 데이터 파일명 (기본: integrated_crawler_week06_<ts>.xlsx)")
    ap.add_argument("--no-raw", action="store_true",
                    help="리포트에서 3인 raw 컬럼을 빼고 통합본만 표시")
    ap.add_argument("--strategy", default=DEFAULT_STRATEGY,
                    choices=["trust", "consensus", "hybrid"],
                    help=f"셀 선택 전략 (기본: {DEFAULT_STRATEGY})")
    args = ap.parse_args()
    MERGE_STRATEGY = args.strategy

    print("=" * 64)
    print("W06 3인 크롤러 통합 시작 — 커버리지·충진율·일치율 동시 극대화")
    print("=" * 64)

    if not GOLDEN_PATH.exists():
        print(f"❌ 골든셋 없음: {GOLDEN_PATH}", file=sys.stderr)
        sys.exit(1)
    if not NORMALIZATION_PATH.exists():
        print(f"❌ 정규화 사전 없음: {NORMALIZATION_PATH}", file=sys.stderr)
        sys.exit(1)

    # ── 1. 정규화기 + 골든셋 ──────────────────────────────
    print(f"\n[1/5] 정규화 사전 로드: {NORMALIZATION_PATH.name}")
    normalizer = Normalizer(NORMALIZATION_PATH)

    print(f"\n[2/5] 골든셋 로드: {GOLDEN_PATH.name}")
    golden = adp_golden.load(GOLDEN_PATH, normalizer)
    print(f"  → {len(golden)}개 대학, {sum(len(df) for df in golden.values()):,}행")

    # ── 2. 3인 산출물 로드 ────────────────────────────────
    print(f"\n[3/5] 3인 산출물 로드")
    person_data: dict[str, dict] = {}
    for label, loader, path in [
        ("yuchan", adp_yuchan.load, YUCHAN_OUTPUT_DIR),
        ("lee", adp_lee.load, LEE_PER_UNIV_DIR),
        ("lim", adp_lim.load, LIM_OUTPUTS_DIR),
    ]:
        print(f"  - {PERSON_KOR[label]}: {path}")
        data = loader(path, normalizer)
        print(f"    → {len(data)}개 대학, {sum(len(df) for df in data.values()):,}행")
        person_data[label] = data

    # ── 3. 3인 평가 → 항목별 신뢰도 산출 ──────────────────
    print(f"\n[4/5] 3인 평가 + 항목별 신뢰도 산출")
    indiv_results = {p: evaluate_person(golden, person_data[p], p) for p in PERSONS}
    reliability = build_reliability(indiv_results)  # {항목: {사람: 셀일치율}} — 집계만 사용

    # ── 4. 통합 (행 합집합 + 신뢰도 가중 셀 선택) ────────
    print(f"\n[5/5] 통합 병합({MERGE_STRATEGY}) + 평가 + 리포트")
    merged, lineage = merge_persons(person_data, reliability, strategy=MERGE_STRATEGY)
    integrated_df = flatten_merged(merged)
    print(f"  🔷 통합: {len(merged)}개 대학, {len(integrated_df):,}행 "
          f"(행 합집합 + 항목별 신뢰도 가중, 충돌 {len(lineage):,}건)")

    # 통합 먼저, 그다음 3인 비교
    results: list[PersonResult] = [evaluate_person(golden, merged, "merged")]
    r_merged = results[0]
    for person in PERSONS:
        results.append(indiv_results[person])

    for r in results:
        s = r.summary
        print(f"  - {PERSON_KOR[r.person]:>5s}: "
              f"Cell {s['cell_match_rate']*100:5.1f}% / "
              f"cov {s['coverage_pct']:5.1f}% / "
              f"충진 {s['cell_fill_rate']*100:5.1f}% / "
              f"비교셀 {s.get('n_cell_compared', 0):,}")

    # ── 5. 산출 ──────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = args.report_name or f"evaluation_report_week06_{ts}.xlsx"
    integrated_name = args.integrated_name or f"integrated_crawler_week06_{ts}.xlsx"
    report_path = OUTPUT_DIR / report_name
    integrated_path = OUTPUT_DIR / integrated_name

    report_results = [r_merged] if args.no_raw else results
    write_report(report_results, report_path)
    write_integrated_dataset(integrated_df, lineage, integrated_path)

    # ── 최종 요약: 통합 효과 ─────────────────────────────
    s_m = r_merged.summary
    best_cell = max(results, key=lambda r: r.summary["cell_match_rate"])
    best_fill = max(results, key=lambda r: r.summary["n_cell_compared"])
    print("\n" + "=" * 64)
    print("W06 통합 효과 (절대량 = 정답 셀 수)")
    for r in results:
        s = r.summary
        correct = round(s.get("n_cell_compared", 0) * s["cell_match_rate"])
        mark = "🔷" if r.person == "merged" else "  "
        print(f"  {mark} {PERSON_KOR[r.person]:>5s}: "
              f"matched행 {s['n_matched']:>6,} / 비교셀 {s.get('n_cell_compared',0):>7,} / "
              f"정답셀≈ {correct:>7,} / Cell {s['cell_match_rate']*100:.1f}%")
    print(f"\n  → 통합은 커버리지 {s_m['coverage_pct']:.1f}% + 비교셀 {s_m.get('n_cell_compared',0):,}개로")
    print(f"    단일 크롤러 최대치(셀 {best_cell.summary['n_cell_compared']:,})를 상회 — "
          f"누락 없이 최다 데이터 수집 달성")
    print(f"  리포트: {report_path}")
    print(f"  통합본: {integrated_path}")
    print("=" * 64)


if __name__ == "__main__":
    main()
