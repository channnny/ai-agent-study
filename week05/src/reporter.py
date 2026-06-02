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


def build_uncovered(results: list[PersonResult]) -> pd.DataFrame:
    """커버리지 100%가 안 되는 이유 — 데이터를 못 낸 골든 대학 명단.

    유찬·이지현 둘 다 못 낸 대학 = 어디가 2025 미게시 추정(소스 문제).
    한쪽만 못 낸 대학 = 해당 크롤러 미수집.
    """
    by_person = {r.person: r for r in results}
    yuchan = by_person.get("yuchan")
    lee = by_person.get("lee")

    # 모든 unvCd + 대학명 수집
    names: dict[str, str] = {}
    for r in results:
        for u, m in r.by_university.items():
            if m.get("univ_name"):
                names[u] = m["univ_name"]
            names.setdefault(u, "")

    rows = []
    for u in sorted(names):
        # 골든에 실재하는 대학만 (어느 사람 기준이든 골든 행 수 > 0)
        ng = max((r.by_university.get(u, {}).get("n_golden", 0) or 0) for r in results)
        if ng == 0:
            continue
        y_st = yuchan.by_university.get(u, {}).get("status") if yuchan else None
        l_st = lee.by_university.get(u, {}).get("status") if lee else None
        y_miss = (y_st == "missing")
        l_miss = (l_st == "missing")
        if not (y_miss or l_miss):
            continue  # 둘 다 데이터 냄 → 제외

        if y_miss and l_miss:
            cause = "① 어디가 2025 미게시 추정 (유찬·이지현 공통 누락)"
        elif y_miss:
            cause = "② 유찬만 미수집 (복잡 테이블 등)"
        else:
            cause = "③ 이지현만 미수집"
        rows.append({
            "unvCd": u,
            "대학명": names[u],
            "골든 행수": ng,
            "유찬": y_st or "-",
            "이지현": l_st or "-",
            "추정 원인": cause,
        })
    # 공통 누락(①) 먼저 보이도록 정렬
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["추정 원인", "대학명"]).reset_index(drop=True)
    return df


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
        ("■ 커버리지가 100%가 안 되는 이유", "→ 대학별 상세 명단은 '미수집대학' 시트 참조"),
        ("(1) 어디가 미게시", "강릉원주대·가톨릭대(성의/성신교정)·대구예술대 등은 2025 전형 결과가 어디가에 아직 안 올라옴 → 유찬·이지현 모두 공통으로 못 냄 (크롤러 문제 아님, 소스 문제)."),
        ("(2) 유찬 복잡 테이블 스킵", "경북대·안양대·중부대·춘천교대 등은 '단과대학+모집단위' 다단 헤더 구조라 유찬 어댑터가 아직 파싱 못 함 (W06 보강 예정)."),
        ("", ""),
        ("■ 남은 PK 격차(~43%)의 주원인", "크롤링 실패가 아니라 전형명 분류 차이. 예: 골든 '농어촌학생' vs 크롤러 '농어촌', 골든 '특성화고교졸업자' vs 크롤러 '특성화고교'. → 같은 전형인데 이름이 달라 매칭 실패. W06에서 전형 분류 사전 합의로 해소."),
        ("", ""),
        ("■ 탭(시트)별 보는 법", ""),
        ("종합", "3명 × 11개 지표 한눈에. 핵심은 커버리지·PK매칭률·셀일치율. ✓/✗는 DoD(목표) 통과 여부."),
        ("대학별", "173개 대학별로 누가 얼마나 정확한지. 초록=목표달성, 빨강=미달, 회색=미수집."),
        ("항목별", "8개 데이터 항목(모집인원·경쟁률·등급 등)별 일치율. 어떤 항목이 약한지 → 우선 개선 대상."),
        ("누락행", "골든엔 있는데 크롤러가 못 찾은 행. 전형명을 보면 분류 차이가 드러남."),
        ("잉여행", "크롤러엔 있는데 골든엔 없는 행. 잘못 긁었거나 전형 표기 차이로 매칭 실패."),
        ("불일치셀", "PK는 맞았는데 값이 틀린 칸. '비고'가 콤마차이/근접이면 사실상 맞은 것."),
        ("미수집대학", "커버리지가 100%가 안 되는 대학 명단 + 추정 원인."),
    ]
    return pd.DataFrame(rows, columns=["항목", "설명"])


# ──────────────────────────────────────────────────────────────
# 스타일링 (openpyxl)
# ──────────────────────────────────────────────────────────────
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

_HEADER_FILL = PatternFill("solid", fgColor="4472C4")   # 진파랑
_HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
_DESC_FILL   = PatternFill("solid", fgColor="D9E1F2")    # 연파랑
_DESC_FONT   = Font(italic=True, color="1F3864", size=10)
_PASS_FILL   = PatternFill("solid", fgColor="C6EFCE")    # 연초록
_FAIL_FILL   = PatternFill("solid", fgColor="FFC7CE")    # 연빨강
_MISS_FILL   = PatternFill("solid", fgColor="EDEDED")    # 회색
_SECTION_FONT = Font(bold=True, color="1F3864", size=11)
_THIN = Side(style="thin", color="D0D0D0")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _disp_width(s: str) -> int:
    """한글 등 전각 문자는 2폭으로 계산."""
    return sum(2 if ord(c) > 0x1100 else 1 for c in str(s))


def _autofit(ws, df: pd.DataFrame, header_row: int, max_w: int = 60):
    for j, col in enumerate(df.columns, start=1):
        vals = [str(col)] + [str(v) for v in df[col] if v is not None]
        w = max((_disp_width(v) for v in vals), default=8)
        ws.column_dimensions[get_column_letter(j)].width = min(max(w + 2, 9), max_w)


def _write_styled(writer, df: pd.DataFrame, sheet: str, desc: str):
    """설명행(1행) + 헤더(2행) + 데이터 시트 작성 + 스타일."""
    if df.empty:
        df = pd.DataFrame([{"info": "해당 행 없음"}])
    df.to_excel(writer, sheet_name=sheet, index=False, startrow=1)
    ws = writer.sheets[sheet]
    n_cols = len(df.columns)

    # 1행: 설명 (병합)
    ws.cell(1, 1, "📌 " + desc)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    c = ws.cell(1, 1)
    c.fill = _DESC_FILL
    c.font = _DESC_FONT
    c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="left")
    ws.row_dimensions[1].height = 42

    # 2행: 헤더
    for j in range(1, n_cols + 1):
        h = ws.cell(2, j)
        h.fill = _HEADER_FILL
        h.font = _HEADER_FONT
        h.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        h.border = _BORDER

    # 데이터 영역 테두리 + 정렬
    for r in range(3, ws.max_row + 1):
        for j in range(1, n_cols + 1):
            cell = ws.cell(r, j)
            cell.border = _BORDER
            cell.alignment = Alignment(vertical="center", wrap_text=True)

    _autofit(ws, df, header_row=2)
    ws.freeze_panes = "A3"  # 설명+헤더 고정


def _colorize_status(ws, df: pd.DataFrame):
    """대학별 시트의 *_status 컬럼을 pass/fail/missing 색으로."""
    status_cols = [j for j, c in enumerate(df.columns, start=1) if str(c).endswith("status")]
    for r in range(3, ws.max_row + 1):
        for j in status_cols:
            v = ws.cell(r, j).value
            if v == "pass":
                ws.cell(r, j).fill = _PASS_FILL
            elif v == "fail":
                ws.cell(r, j).fill = _FAIL_FILL
            elif v == "missing":
                ws.cell(r, j).fill = _MISS_FILL


def _style_glossary(ws, df: pd.DataFrame):
    """용어설명 시트 전용 스타일 — 섹션 헤더(■) 강조."""
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 105
    # 헤더행
    for j in (1, 2):
        h = ws.cell(1, j)
        h.fill = _HEADER_FILL
        h.font = _HEADER_FONT
        h.alignment = Alignment(horizontal="center", vertical="center")
    for r in range(2, ws.max_row + 1):
        a = ws.cell(r, 1)
        b = ws.cell(r, 2)
        a.alignment = Alignment(vertical="top", wrap_text=True)
        b.alignment = Alignment(vertical="top", wrap_text=True)
        if a.value and str(a.value).startswith("■"):
            a.font = _SECTION_FONT
            a.fill = _DESC_FILL
            b.fill = _DESC_FILL


def write_report(results: list[PersonResult], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    glossary   = build_glossary()
    summary    = build_summary(results)
    by_univ    = build_by_university(results)
    by_col     = build_by_column(results)
    uncovered  = build_uncovered(results)
    missing    = build_long_rows(results, "missing_rows")
    extra      = build_long_rows(results, "extra_rows")
    mismatched = build_long_rows(results, "mismatched_cells")

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        # 용어설명 (자체가 설명이라 별도 desc 없이)
        glossary.to_excel(writer, sheet_name="용어설명", index=False)
        _style_glossary(writer.sheets["용어설명"], glossary)

        _write_styled(writer, summary, "종합",
            "3명 × 11개 지표 한눈에. 핵심 3개 = 커버리지(몇 대학 시도) → PK매칭률(같은 행 찾음) → 셀일치율(값 정확). ✓/✗ = 목표(DoD) 통과 여부.")
        _write_styled(writer, by_univ, "대학별",
            "173개 대학별 정확도. status 색: 초록=목표달성(pass) / 빨강=미달(fail) / 회색=미수집(missing). PK률·셀률은 각자 컬럼.")
        _colorize_status(writer.sheets["대학별"], by_univ)
        _write_styled(writer, by_col, "항목별",
            "8개 데이터 항목별 일치율(매칭된 행 한정). 낮은 항목 = 그 항목 파싱을 우선 개선해야 함.")
        _write_styled(writer, uncovered, "미수집대학",
            "커버리지가 100%가 안 되는 대학 명단. ① = 어디가에 2025 결과 미게시(소스 문제, 크롤러 무관) / ② ③ = 해당 크롤러만 미수집.")
        _write_styled(writer, missing, "누락행",
            "골든엔 있는데 크롤러가 못 찾은 행. 전형명을 보면 분류 차이(예: '농어촌학생' vs '농어촌')가 드러남 → PK 격차의 주원인.")
        _write_styled(writer, extra, "잉여행",
            "크롤러엔 있는데 골든엔 없는 행. 잘못 긁었거나 전형 표기가 달라 매칭이 안 된 케이스.")
        _write_styled(writer, mismatched, "불일치셀",
            "PK는 맞았는데 값이 틀린 칸. '비고'가 '콤마 차이'·'근접'이면 사실상 맞은 것 → 실제 정확도는 셀일치율보다 높을 수 있음.")

    print(f"\n✓ 평가 리포트: {output_path}")
    print(f"  시트 8개: 용어설명 · 종합 · 대학별 · 항목별 · 미수집대학 · 누락행 · 잉여행 · 불일치셀")
