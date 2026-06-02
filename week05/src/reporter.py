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
    """row=대학(unvCd), col=person별 (PK률, 셀률, status, n_matched, n_golden)."""
    all_univ = set()
    univ_names: dict[str, str] = {}
    for r in results:
        for unv_cd, m in r.by_university.items():
            all_univ.add(unv_cd)
            if m.get("univ_name") and unv_cd not in univ_names:
                univ_names[unv_cd] = m["univ_name"]

    rows = []
    for unv_cd in sorted(all_univ):
        row = {"unvCd": unv_cd, "대학": univ_names.get(unv_cd, "")}
        for r in results:
            label = PERSON_KOR.get(r.person, r.person)
            m = r.by_university.get(unv_cd, {})
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


def build_glossary() -> pd.DataFrame:
    """리포트 맨 앞 — 용어·지표·읽는 법 설명. 회의에서 처음 보는 사람용."""
    rows = [
        ("■ 이 리포트는?", "3명(유찬·이지현·임지현)의 어디가 크롤러 출력을 작년 골든셋(2025_수시_입시결과_통합본)과 비교해 정확도를 측정한 결과입니다."),
        ("", ""),
        ("■ 핵심 지표 3개 (깔때기 순서)", ""),
        ("① 커버리지 (coverage_pct)", "골든셋 173개 대학 중 그 사람이 '데이터를 낸' 대학 비율. = 데이터 낸 대학 ÷ 173. '애초에 평가 테이블에 올라올 자격'."),
        ("② PK 매칭률 (pk_match_rate)", "PK = (대학코드, 전형, 모집단위) 3개 조합. 골든과 크롤러가 '둘 다 가진 PK 수' ÷ '골든 전체 PK 수'. = 빠뜨리지 않고 같은 행을 찾았는가? (양의 정확도)"),
        ("③ 셀 일치율 (cell_match_rate)", "PK가 매칭된 행에 한해, 각 데이터 칸(모집인원·경쟁률·학생부등급 등)의 값이 골든과 같은 비율. = 찾은 행의 숫자가 정확한가? (질의 정확도)"),
        ("", "→ 셋 다 높아야 진짜 정확. 하나만 높으면 함정 (예: 커버리지 5%인데 셀 48%면 일부 대학만의 얘기)."),
        ("", ""),
        ("■ 보조 지표", ""),
        ("n_matched / n_golden_total", "매칭된 행 수 / 골든셋 전체 행 수."),
        ("n_missing", "골든엔 있는데 크롤러가 못 찾은 행 수 (→ missing_rows 시트)."),
        ("n_extra", "크롤러엔 있는데 골든엔 없는 행 수 (→ extra_rows 시트)."),
        ("pk_dod_pass / cell_dod_pass", "DoD(목표) 통과 여부. 기준: PK ≥ 85%, 셀 ≥ 90%. ✓=통과, ✗=미달."),
        ("", ""),
        ("■ by_university 시트의 status", ""),
        ("pass", "PK ≥ 85% 이고 셀 ≥ 90% (목표 달성)."),
        ("fail", "데이터는 냈지만 기준 미달."),
        ("missing", "그 대학을 아예 못 냄 (어디가에 데이터 없거나 크롤러가 0행)."),
        ("", ""),
        ("■ mismatched_cells 시트의 '비고'", ""),
        ("콤마 차이", "'1,234' vs '1234' 같은 포맷 차이 — 사실상 같은 값."),
        ("근접: 차이 0.0x", "반올림 수준 차이 — 거의 맞음."),
        ("사람=null, 골든=값있음", "크롤러가 그 칸을 못 긁음 (진짜 누락)."),
        ("차이: +N", "골든과 명확히 다른 값."),
        ("", ""),
        ("■ 커버리지가 100%가 안 되는 이유", ""),
        ("(1) 어디가 미게시", "강릉원주대·가톨릭대(성의/성신교정)·대구예술대 등 약 14개 대학은 2025 전형 결과가 어디가에 아직 안 올라옴 → 세 사람 모두 공통으로 못 냄 (크롤러 문제 아님, 소스 문제)."),
        ("(2) 유찬 복잡 테이블 스킵", "경북대·안양대·중부대·춘천교대 등은 '단과대학+모집단위' 다단 헤더 구조라 유찬 어댑터가 아직 파싱 못 함 (W06 보강 예정)."),
        ("", ""),
        ("■ 남은 PK 격차(~43%)의 주원인", "크롤링 실패가 아니라 전형명 분류 차이. 예: 골든 '농어촌학생' vs 크롤러 '농어촌', 골든 '특성화고교졸업자' vs 크롤러 '특성화고교'. → 같은 전형인데 이름이 달라 매칭 실패. W06에서 전형 분류 사전 합의로 해소."),
    ]
    return pd.DataFrame(rows, columns=["항목", "설명"])


def write_report(results: list[PersonResult], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    glossary   = build_glossary()
    summary    = build_summary(results)
    by_univ    = build_by_university(results)
    by_col     = build_by_column(results)
    missing    = build_long_rows(results, "missing_rows")
    extra      = build_long_rows(results, "extra_rows")
    mismatched = build_long_rows(results, "mismatched_cells")

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        glossary.to_excel(writer, sheet_name="용어설명",        index=False)
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

        # 용어설명 시트 컬럼 너비 조정 (가독성)
        ws = writer.sheets["용어설명"]
        ws.column_dimensions["A"].width = 34
        ws.column_dimensions["B"].width = 110

    print(f"\n✓ 평가 리포트: {output_path}")
    print(f"  시트 7개: 용어설명, summary, by_university, by_column, missing_rows, extra_rows, mismatched_cells")
