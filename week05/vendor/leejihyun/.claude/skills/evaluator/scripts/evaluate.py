"""adiga 에이전트 결과 평가 — T6 단계

PoC evaluate.py를 기반으로, 새 스키마(수시 입시결과 시트명)에 맞게 수정.

사용법:
    python evaluate.py \\
        --golden input/2025_어디가입결_통합본.xlsx \\
        --predicted output/adiga_2027.xlsx \\
        --out output/evaluation_report.xlsx
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

DEFAULT_TARGETS = [
    "가천대학교", "서울대학교", "제주대학교", "연세대학교",
    "고려대학교", "부산대학교", "경북대학교", "남서울대학교",
]

EXCLUDED_COLS = {
    "라벨",
    "바이브온_대학명", "바이브온_대학코드",
    "바이브온_전형명", "바이브온_전형코드",
    "바이브온_모집단위명", "바이브온_모집단위코드",
    "raw_text", "데이터공개수준", "전형구분_대분류",
    "전형구분_소분류", "결과학년도", "캠퍼스",
}

PK_COLS = ["대학", "전형", "모집단위"]

HEADER_FONT = Font(name="맑은 고딕", size=10, bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", start_color="1F4E78")
CELL_FONT   = Font(name="맑은 고딕", size=10)
CENTER      = Alignment(horizontal="center", vertical="center", wrap_text=True)


# ─────────────────────────────────────────────
# 데이터 로딩
# ─────────────────────────────────────────────

def load_sheet_flat(path: str, sheet_name: str) -> pd.DataFrame:
    """2단 헤더 엑셀 → 평탄화 (그룹_컬럼 형식)."""
    try:
        df = pd.read_excel(path, sheet_name=sheet_name, header=[0, 1])
    except Exception:
        # 1단 헤더 폴백
        df = pd.read_excel(path, sheet_name=sheet_name)
        return df

    new_cols = []
    seen: dict[str, int] = defaultdict(int)
    for top, sub in df.columns:
        top_str = str(top)
        if top_str.startswith("Unnamed") or pd.isna(top):
            name = str(sub)
        else:
            name = f"{top_str}_{sub}"
        count = seen[name]
        seen[name] += 1
        if count > 0:
            name = f"{name}__{count}"
        new_cols.append(name)
    df.columns = new_cols
    return df


def normalize_pk_value(v) -> str:
    if pd.isna(v):
        return ""
    s = str(v).strip()
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s)
    # 전각 괄호 → 반각
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("【", "[").replace("】", "]")
    # 괄호 주변 공백 제거: "( 종합 )" → "(종합)"
    s = re.sub(r"\s*\(\s*", "(", s)
    s = re.sub(r"\s*\)\s*", ")", s)
    s = re.sub(r"\s*\[\s*", "[", s)
    s = re.sub(r"\s*\]\s*", "]", s)
    # 괄호 안의 쉼표 공백 정규화: "해외고 , 검정고시" → "해외고,검정고시"
    s = re.sub(r"\s*,\s*", ",", s)
    # 가운뎃점(·) 주변 공백 정규화: "물리 · 천문학부" → "물리·천문학부"
    s = re.sub(r"\s*·\s*", "·", s)
    # 후미 별표 마커 제거: "전공(*)" → "전공"
    s = re.sub(r"\s*\(\*+\)\s*$", "", s)
    # 접미사 "전형" 제거
    s = re.sub(r"\s*전형\s*$", "", s)
    return s.strip()


def jeon_keyword(v: str) -> str:
    """전형명에서 대분류 wrapper를 제거한 핵심 키워드 반환. PK 폴백 매칭용."""
    s = normalize_pk_value(v)
    # "학생부종합(X)" → "X"
    m = re.match(r"학생부[^\(]*\((.+)\)$", s)
    if m:
        return re.sub(r"\s*전형\s*$", "", m.group(1)).strip()
    # "학생부종합전형(X)" → "X" (예: 고려대 "학생부종합전형(학업우수)")
    m = re.match(r"학생부[^\(]*전형?\((.+)\)$", s)
    if m:
        return m.group(1).strip()
    # "수시 X" → "X"
    s = re.sub(r"^수시\s*", "", s).strip()
    return s


def build_pk(row, pk_cols=PK_COLS) -> tuple:
    return tuple(normalize_pk_value(row[c]) for c in pk_cols if c in row)


def build_pk_fallback(row, pk_cols=PK_COLS) -> tuple:
    """대분류 wrapper를 제거한 폴백 PK (전형 키워드만 사용)."""
    result = []
    for c in pk_cols:
        if c not in row:
            continue
        v = normalize_pk_value(row[c])
        if c == "전형":
            v = jeon_keyword(normalize_pk_value(row[c]))
        result.append(v)
    return tuple(result)


# ─────────────────────────────────────────────
# 셀 일치 판정
# ─────────────────────────────────────────────

INT_STRICT_COLS  = {"모집인원", "충원합격순위"}
FLOAT_RATIO_COLS = {"경쟁률"}


def cells_match(golden, predicted, col_name: str) -> tuple[bool, str]:
    g_null = pd.isna(golden) if not isinstance(golden, str) else (golden.strip() == "")
    p_null = pd.isna(predicted) if not isinstance(predicted, str) else (predicted.strip() == "")

    if g_null and p_null:
        return True, "both_null"
    if g_null and not p_null:
        return True, "golden_null_pred_present"
    if not g_null and p_null:
        return False, "pred_missing"

    # 숫자 비교
    try:
        g_num = float(str(golden).replace(",", "").replace(" ", ""))
        p_num = float(str(predicted).replace(",", "").replace(" ", ""))
        if col_name in INT_STRICT_COLS:
            return (g_num == p_num), "int_compare"
        if col_name in FLOAT_RATIO_COLS:
            return (abs(g_num - p_num) <= 0.01), "ratio_compare"
        return (abs(g_num - p_num) <= 0.01), "numeric_compare"
    except (ValueError, TypeError):
        pass

    # 문자열 비교
    g_str = re.sub(r"[\s,]+", " ", str(golden).strip())
    p_str = re.sub(r"[\s,]+", " ", str(predicted).strip())
    return (g_str == p_str), "string_compare"


# ─────────────────────────────────────────────
# 평가 본체
# ─────────────────────────────────────────────

@dataclass
class EvaluationResult:
    targets: list[str]
    golden_rows: int = 0
    pred_rows:   int = 0
    matched_pks: int = 0
    missing_pks: list[tuple] = field(default_factory=list)
    extra_pks:   list[tuple] = field(default_factory=list)
    eval_cols:   list[str]   = field(default_factory=list)
    col_total:   dict = field(default_factory=lambda: defaultdict(int))
    col_match:   dict = field(default_factory=lambda: defaultdict(int))
    univ_match_cells: dict = field(default_factory=lambda: defaultdict(int))
    univ_total_cells: dict = field(default_factory=lambda: defaultdict(int))
    univ_matched_pks: dict = field(default_factory=lambda: defaultdict(int))
    univ_golden_pks:  dict = field(default_factory=lambda: defaultdict(int))
    mismatches: list[dict] = field(default_factory=list)

    def pk_match_rate(self) -> float:
        return self.matched_pks / self.golden_rows if self.golden_rows else 0.0

    def cell_match_rate(self) -> float:
        total = sum(self.col_total.values())
        match = sum(self.col_match.values())
        return match / total if total else 0.0

    def extra_rate(self) -> float:
        return len(self.extra_pks) / self.pred_rows if self.pred_rows else 0.0


def evaluate(
    golden_df: pd.DataFrame,
    pred_df: pd.DataFrame,
    targets: list[str],
) -> EvaluationResult:
    golden_df = golden_df[golden_df["대학"].isin(targets)].copy()
    pred_df   = pred_df[pred_df["대학"].isin(targets)].copy()

    golden_df["_pk"]  = golden_df.apply(build_pk, axis=1)
    pred_df["_pk"]    = pred_df.apply(build_pk, axis=1)
    golden_df["_pkf"] = golden_df.apply(build_pk_fallback, axis=1)
    pred_df["_pkf"]   = pred_df.apply(build_pk_fallback, axis=1)

    golden_df = golden_df.drop_duplicates(subset="_pk", keep="last")
    pred_df   = pred_df.drop_duplicates(subset="_pk", keep="last")

    golden_pks = set(golden_df["_pk"])
    pred_pks   = set(pred_df["_pk"])

    # 1차: 정확 매칭
    matched_exact = golden_pks & pred_pks

    # 2차: 폴백 매칭 (전형명 핵심 키워드 기반)
    unmatched_golden = golden_pks - matched_exact
    unmatched_pred   = pred_pks   - matched_exact
    g_fallback: dict[tuple, list[tuple]] = defaultdict(list)
    p_fallback: dict[tuple, list[tuple]] = defaultdict(list)
    for _, row in golden_df[golden_df["_pk"].isin(unmatched_golden)].iterrows():
        g_fallback[row["_pkf"]].append(row["_pk"])
    for _, row in pred_df[pred_df["_pk"].isin(unmatched_pred)].iterrows():
        p_fallback[row["_pkf"]].append(row["_pk"])
    # 폴백 PK가 양쪽에 유일하게 존재할 때만 매핑 허용
    fallback_pairs: dict[tuple, tuple] = {}
    for f_pk, g_list in g_fallback.items():
        p_list = p_fallback.get(f_pk, [])
        if len(g_list) == 1 and len(p_list) == 1:
            fallback_pairs[g_list[0]] = p_list[0]

    matched = matched_exact | set(fallback_pairs.keys())

    eval_cols = [
        c for c in golden_df.columns
        if c not in EXCLUDED_COLS and c not in PK_COLS and c not in ("_pk", "_pkf")
    ]

    result = EvaluationResult(
        targets=targets,
        golden_rows=len(golden_df),
        pred_rows=len(pred_df),
        matched_pks=len(matched),
        missing_pks=sorted(golden_pks - pred_pks - set(fallback_pairs.keys()))[:200],
        extra_pks=sorted(pred_pks - golden_pks - set(fallback_pairs.values()))[:200],
        eval_cols=eval_cols,
    )

    for pk in golden_pks:
        result.univ_golden_pks[pk[0]] += 1
    for pk in matched:
        result.univ_matched_pks[pk[0]] += 1

    g_rows = {pk: row for pk, row in zip(golden_df["_pk"], golden_df.to_dict("records"))}
    p_rows = {pk: row for pk, row in zip(pred_df["_pk"],   pred_df.to_dict("records"))}

    for pk in matched:
        g_row = g_rows.get(pk)
        # 폴백 매칭된 행은 pred_pk가 다를 수 있음
        pred_pk = fallback_pairs.get(pk, pk)
        p_row = p_rows.get(pred_pk)
        if g_row is None or p_row is None:
            continue
        univ = pk[0]
        for col in eval_cols:
            if col not in p_row:
                continue
            g_val = g_row.get(col)
            if pd.isna(g_val) if not isinstance(g_val, str) else (g_val.strip() == ""):
                continue
            result.col_total[col] += 1
            result.univ_total_cells[univ] += 1
            match, reason = cells_match(g_val, p_row.get(col), col)
            if match:
                result.col_match[col] += 1
                result.univ_match_cells[univ] += 1
            elif len(result.mismatches) < 1000:
                result.mismatches.append({
                    "대학": pk[0], "전형": pk[1], "모집단위": pk[2],
                    "컬럼": col, "골든셋": g_val, "에이전트": p_row.get(col),
                    "판정사유": reason,
                })

    return result


# ─────────────────────────────────────────────
# 리포트 작성
# ─────────────────────────────────────────────

def _style_header(ws, n_cols: int) -> None:
    for i in range(1, n_cols + 1):
        c = ws.cell(row=1, column=i)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = CENTER


def write_report(result: EvaluationResult, out_path: str) -> None:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    # 1. summary
    ws = wb.create_sheet("summary")
    rows = [
        ("타겟 대학", ", ".join(result.targets)),
        ("골든셋 행수", result.golden_rows),
        ("에이전트 행수", result.pred_rows),
        ("PK 매칭률", f"{result.pk_match_rate()*100:.2f}%"),
        ("매칭 PK 수", result.matched_pks),
        ("미매칭 PK 수", len(result.missing_pks)),
        ("잉여행수", len(result.extra_pks)),
        ("셀 일치율", f"{result.cell_match_rate()*100:.2f}%"),
        ("일치 셀수", sum(result.col_match.values())),
        ("비교 셀수", sum(result.col_total.values())),
    ]
    ws["A1"] = "지표"; ws["B1"] = "값"
    _style_header(ws, 2)
    for r_idx, (k, v) in enumerate(rows, start=2):
        ws.cell(row=r_idx, column=1, value=k).font = CELL_FONT
        ws.cell(row=r_idx, column=2, value=v).font = CELL_FONT
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 50

    # 2. by_university
    ws = wb.create_sheet("by_university")
    ws.append(["대학", "골든셋_PK", "매칭_PK", "PK매칭률(%)", "비교셀", "일치셀", "셀일치율(%)"])
    _style_header(ws, 7)
    for univ in result.targets:
        g = result.univ_golden_pks.get(univ, 0)
        m = result.univ_matched_pks.get(univ, 0)
        t = result.univ_total_cells.get(univ, 0)
        mc = result.univ_match_cells.get(univ, 0)
        ws.append([
            univ, g, m,
            round((m / g * 100) if g else 0, 2),
            t, mc,
            round((mc / t * 100) if t else 0, 2),
        ])

    # 3. by_column
    ws = wb.create_sheet("by_column")
    ws.append(["컬럼", "비교셀", "일치셀", "일치율(%)"])
    _style_header(ws, 4)
    for col in result.eval_cols:
        t = result.col_total.get(col, 0)
        m = result.col_match.get(col, 0)
        if t == 0:
            continue
        ws.append([col, t, m, round(m / t * 100, 2)])
    ws.column_dimensions["A"].width = 30

    # 4. missing_rows
    ws = wb.create_sheet("missing_rows")
    ws.append(["대학", "전형", "모집단위"])
    _style_header(ws, 3)
    for pk in result.missing_pks:
        ws.append(list(pk))

    # 5. extra_rows
    ws = wb.create_sheet("extra_rows")
    ws.append(["대학", "전형", "모집단위"])
    _style_header(ws, 3)
    for pk in result.extra_pks:
        ws.append(list(pk))

    # 6. mismatched_cells
    ws = wb.create_sheet("mismatched_cells")
    ws.append(["대학", "전형", "모집단위", "컬럼", "골든셋", "에이전트", "판정사유"])
    _style_header(ws, 7)
    for m in result.mismatches:
        ws.append([m["대학"], m["전형"], m["모집단위"],
                   m["컬럼"], m["골든셋"], m["에이전트"], m["판정사유"]])

    wb.save(out_path)
    print(f"[T6 평가] 리포트 저장: {out_path}")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="adiga 에이전트 결과 평가")
    ap.add_argument("--golden",    required=True, help="골든셋 엑셀")
    ap.add_argument("--predicted", required=True, help="에이전트 결과 엑셀")
    ap.add_argument("--out",  default="output/evaluation_report.xlsx")
    ap.add_argument("--sheet",      default="수시",         help="골든셋 시트명")
    ap.add_argument("--pred-sheet", default="수시 입시결과", help="에이전트 시트명")
    ap.add_argument("--targets", nargs="+", default=DEFAULT_TARGETS)
    args = ap.parse_args()

    print(f"[T6 평가] 골든셋 로딩: {args.golden}")
    golden = load_sheet_flat(args.golden, args.sheet)
    print(f"  → {len(golden):,}행, {len(golden.columns)}컬럼")

    print(f"[T6 평가] 에이전트 결과 로딩: {args.predicted} (시트: {args.pred_sheet})")
    pred = load_sheet_flat(args.predicted, args.pred_sheet)
    print(f"  → {len(pred):,}행, {len(pred.columns)}컬럼")

    print(f"[T6 평가] 평가 실행 ({len(args.targets)}개 대학)")
    result = evaluate(golden, pred, args.targets)

    print(f"\n  PK 매칭률:  {result.pk_match_rate()*100:.1f}% ({result.matched_pks}/{result.golden_rows})")
    print(f"  셀 일치율:  {result.cell_match_rate()*100:.1f}%")
    print(f"  잉여행수:   {len(result.extra_pks)}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    write_report(result, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
