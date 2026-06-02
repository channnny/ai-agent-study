"""6시트 평가 리포트 (Excel) 작성.

시트:
  1) summary           — row=metric × col=person
  2) by_university     — row=대학 × col=person별 metric
  3) by_column         — row=DATA 컬럼 × col=person별 match_rate
  4) missing_rows      — golden에 있고 person에 없음 (long-format)
  5) extra_rows        — person에만 있음
  6) mismatched_cells  — matched 행의 셀 불일치 (long-format)

# adapted from leejihyun/evaluation_report.xlsx 양식
"""
from __future__ import annotations
import pandas as pd
from pathlib import Path
from datetime import datetime

from .config import DATA_COLUMNS, PERSON_KOR
from .matcher import PersonResult


SUMMARY_METRICS_ORDER = [
    ("pk_match_rate",   "PK 매칭률"),
    ("cell_match_rate", "셀 일치율"),
    ("n_matched",       "matched 행 수"),
    ("n_missing",       "missing 행 수"),
    ("n_extra",         "extra 행 수"),
    ("n_golden_total",  "골든 전체 행 수"),
    ("coverage_pct",    "커버리지(%)"),
    ("n_failed_univ",   "fail 대학 수"),
    ("n_missing_univ",  "missing 대학 수"),
    ("pk_dod_pass",     "PK DoD 통과 (≥85%)"),
    ("cell_dod_pass",   "셀 DoD 통과 (≥90%)"),
]


def _format_rate(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return "✓" if v else "✗"
    if isinstance(v, float) and 0 <= v <= 1:
        return f"{v*100:.2f}%"
    if isinstance(v, float):
        return round(v, 2)
    return v


def build_summary(results: list[PersonResult]) -> pd.DataFrame:
    rows = []
    for key, label in SUMMARY_METRICS_ORDER:
        row = {"metric": label}
        for r in results:
            row[PERSON_KOR.get(r.person, r.person)] = _format_rate(r.summary.get(key))
        rows.append(row)
    return pd.DataFrame(rows)


def build_by_university(results: list[PersonResult]) -> pd.DataFrame:
    """row=대학, col=person별 (PK률, 셀률, status, n_matched, n_golden)."""
    all_univ = set()
    for r in results:
        all_univ.update(r.by_university.keys())

    rows = []
    for univ in sorted(all_univ):
        row = {"대학": univ}
        for r in results:
            label = PERSON_KOR.get(r.person, r.person)
            m = r.by_university.get(univ, {})
            row[f"{label}_PK률"]   = _format_rate(m.get("pk_match_rate"))
            row[f"{label}_셀률"]   = _format_rate(m.get("cell_match_rate"))
            row[f"{label}_status"] = m.get("status")
            row[f"{label}_matched/golden"] = f"{m.get('n_matched', 0)}/{m.get('n_golden', 0)}"
        rows.append(row)
    return pd.DataFrame(rows)


def build_by_column(results: list[PersonResult]) -> pd.DataFrame:
    rows = []
    for col in DATA_COLUMNS:
        row = {"컬럼": col}
        for r in results:
            label = PERSON_KOR.get(r.person, r.person)
            row[label] = _format_rate(r.by_column.get(col))
        rows.append(row)
    return pd.DataFrame(rows)


def build_long_rows(results: list[PersonResult], attr: str) -> pd.DataFrame:
    """missing_rows / extra_rows / mismatched_cells 통합."""
    rows = []
    for r in results:
        rows.extend(getattr(r, attr))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def write_report(results: list[PersonResult], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    summary    = build_summary(results)
    by_univ    = build_by_university(results)
    by_col     = build_by_column(results)
    missing    = build_long_rows(results, "missing_rows")
    extra      = build_long_rows(results, "extra_rows")
    mismatched = build_long_rows(results, "mismatched_cells")

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer,  sheet_name="summary",        index=False)
        by_univ.to_excel(writer,  sheet_name="by_university",  index=False)
        by_col.to_excel(writer,   sheet_name="by_column",      index=False)
        if not missing.empty:
            missing.to_excel(writer, sheet_name="missing_rows", index=False)
        else:
            pd.DataFrame([{"info": "missing 행 없음 — 모든 골든 PK가 사람 출력에 존재"}]) \
                .to_excel(writer, sheet_name="missing_rows", index=False)
        if not extra.empty:
            extra.to_excel(writer, sheet_name="extra_rows", index=False)
        else:
            pd.DataFrame([{"info": "extra 행 없음"}]) \
                .to_excel(writer, sheet_name="extra_rows", index=False)
        if not mismatched.empty:
            mismatched.to_excel(writer, sheet_name="mismatched_cells", index=False)
        else:
            pd.DataFrame([{"info": "셀 불일치 없음 — 완벽 일치"}]) \
                .to_excel(writer, sheet_name="mismatched_cells", index=False)

    print(f"\n✓ 평가 리포트: {output_path}")
    print(f"  시트 6개: summary, by_university, by_column, missing_rows, extra_rows, mismatched_cells")
