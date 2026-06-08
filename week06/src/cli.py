"""W06 통합 크롤러 CLI.

사용법:
    python -m src.cli
    python -m src.cli --report-name evaluation_report_week06.xlsx
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "src"

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from week05.src.adapters import golden as adp_golden  # noqa: E402
from week05.src.adapters import leejihyun as adp_lee  # noqa: E402
from week05.src.adapters import limjihyun as adp_lim  # noqa: E402
from week05.src.adapters import yuchan as adp_yuchan  # noqa: E402
from week05.src.matcher import evaluate_person  # noqa: E402

from .config import (  # noqa: E402
    GOLDEN_PATH,
    INTEGRATED_PERSON,
    LEE_PER_UNIV_DIR,
    LIM_OUTPUTS_DIR,
    NORMALIZATION_PATH,
    OUTPUT_DIR,
    SOURCE_LABELS,
    SOURCE_PERSONS,
    YUCHAN_OUTPUT_DIR,
)
from .integrator import flatten_integrated, integrate_sources  # noqa: E402
from .normalizer import W06Normalizer  # noqa: E402
from .reporter import write_integrated_dataset, write_week06_report  # noqa: E402


def _fmt_rate(v: float | None) -> str:
    if v is None:
        return "-"
    return f"{v * 100:.2f}%"


def main() -> None:
    ap = argparse.ArgumentParser(description="W06 3인 크롤러 통합 + 평가 리포트")
    ap.add_argument("--report-name", default=None, help="평가 리포트 파일명")
    ap.add_argument("--integrated-name", default=None, help="통합 canonical 데이터 파일명")
    ap.add_argument("--no-raw", action="store_true", help="리포트에서 raw 3인 결과를 빼고 통합본만 표시")
    args = ap.parse_args()

    print("=" * 72)
    print("W06 통합 크롤러 시작 — W05 3인 산출물 → 통합 canonical 데이터셋")
    print("=" * 72)

    print(f"\n[1/5] W06 정규화기 로드: {NORMALIZATION_PATH.name}")
    normalizer = W06Normalizer(NORMALIZATION_PATH)

    print(f"\n[2/5] 골든셋 로드: {GOLDEN_PATH.name}")
    golden = adp_golden.load(GOLDEN_PATH, normalizer)
    print(f"  → {len(golden)}개 대학, {sum(len(df) for df in golden.values()):,}행")

    print("\n[3/5] 3인 산출물 로드")
    sources = {}
    print(f"  - {SOURCE_LABELS['yuchan']}: {YUCHAN_OUTPUT_DIR}")
    sources["yuchan"] = adp_yuchan.load(YUCHAN_OUTPUT_DIR, normalizer)
    print(f"    → {len(sources['yuchan'])}개 대학, {sum(len(df) for df in sources['yuchan'].values()):,}행")

    print(f"  - {SOURCE_LABELS['lee']}: {LEE_PER_UNIV_DIR}")
    sources["lee"] = adp_lee.load(LEE_PER_UNIV_DIR, normalizer)
    print(f"    → {len(sources['lee'])}개 대학, {sum(len(df) for df in sources['lee'].values()):,}행")

    print(f"  - {SOURCE_LABELS['lim']}: {LIM_OUTPUTS_DIR}")
    sources["lim"] = adp_lim.load(LIM_OUTPUTS_DIR, normalizer)
    print(f"    → {len(sources['lim'])}개 대학, {sum(len(df) for df in sources['lim'].values()):,}행")

    print("\n[4/5] raw 3인 평가 후 신뢰도 산출")
    source_results = {}
    raw_results = []
    for person in SOURCE_PERSONS:
        result = evaluate_person(golden, sources[person], person)
        source_results[person] = result
        raw_results.append(result)
        s = result.summary
        print(
            f"  - {SOURCE_LABELS[person]}: "
            f"Cell={_fmt_rate(s['cell_match_rate'])}, "
            f"Fill={_fmt_rate(s['cell_fill_rate'])}, "
            f"PK={_fmt_rate(s['pk_match_rate'])}, "
            f"coverage={s['coverage_pct']:.1f}%"
        )

    print("\n[5/5] 통합 데이터 생성 + 평가 리포트")
    integrated, lineage, source_summary = integrate_sources(sources, source_results)
    integrated_df = flatten_integrated(integrated)
    integrated_result = evaluate_person(golden, integrated, INTEGRATED_PERSON)
    s = integrated_result.summary
    print(
        f"  - 통합: Cell={_fmt_rate(s['cell_match_rate'])}, "
        f"Fill={_fmt_rate(s['cell_fill_rate'])}, "
        f"PK={_fmt_rate(s['pk_match_rate'])}, "
        f"coverage={s['coverage_pct']:.1f}%, "
        f"rows={len(integrated_df):,}"
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = args.report_name or f"evaluation_report_week06_{ts}.xlsx"
    integrated_name = args.integrated_name or f"integrated_crawler_week06_{ts}.xlsx"
    report_path = OUTPUT_DIR / report_name
    integrated_path = OUTPUT_DIR / integrated_name

    report_results = [integrated_result] if args.no_raw else raw_results + [integrated_result]
    write_week06_report(report_results, report_path, source_summary, integrated_df, lineage)
    write_integrated_dataset(integrated_df, lineage, integrated_path)

    print("\n" + "=" * 72)
    print("W06 결과")
    print(f"  평가 리포트: {report_path}")
    print(f"  통합 데이터: {integrated_path}")
    print("=" * 72)


if __name__ == "__main__":
    main()

