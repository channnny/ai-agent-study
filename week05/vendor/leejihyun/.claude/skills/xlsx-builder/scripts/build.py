"""4시트 Excel 워크북 빌드 — T5 단계

사용법:
    python build.py --year 2027 \\
                    --normalized-dir output/normalized \\
                    --per-univ-dir output/per_university \\
                    --output output/adiga_2027.xlsx \\
                    --schema input/schema_v3.yaml \\
                    --errors output/logs/error_log.json \\
                    --new-columns output/logs/new_columns_proposals.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional

import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
import yaml

# ─────────────────────────────────────────────
# 스타일 상수
# ─────────────────────────────────────────────
HEADER_FONT      = Font(name="맑은 고딕", size=10, bold=True, color="FFFFFF")
HEADER_FILL_DARK = PatternFill("solid", start_color="1F4E78")
HEADER_FILL_MID  = PatternFill("solid", start_color="2E75B6")
CELL_FONT        = Font(name="맑은 고딕", size=10)
CENTER           = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT             = Alignment(horizontal="left",   vertical="center", wrap_text=True)


def style_header_cell(cell, fill=None):
    cell.font = HEADER_FONT
    cell.fill = fill or HEADER_FILL_DARK
    cell.alignment = CENTER


# ─────────────────────────────────────────────
# 골든셋 양식 (susi_result 2단 헤더)
# ─────────────────────────────────────────────
# (그룹, 컬럼명, JSON 키)
SUSI_RESULT_SCHEMA: list[tuple[Optional[str], str, str]] = [
    (None, "대학",         "대학"),
    (None, "전형",         "전형"),
    (None, "모집단위",     "모집단위"),
    (None, "라벨",         "_라벨"),           # ViveOn 내부용 빈 컬럼
    (None, "바이브온_대학명",     "_바이브온"),
    (None, "바이브온_대학코드",   "_바이브온"),
    (None, "바이브온_전형명",     "_바이브온"),
    (None, "바이브온_전형코드",   "_바이브온"),
    (None, "바이브온_모집단위명", "_바이브온"),
    (None, "바이브온_모집단위코드", "_바이브온"),
    (None, "모집인원",     "모집인원"),
    (None, "경쟁률",       "경쟁률"),
    (None, "충원합격순위", "충원합격순위"),
    ("대학별환산", "최고",  "대학별환산_최고"),
    ("대학별환산", "평균",  "대학별환산_평균"),
    ("대학별환산", "50컷", "대학별환산_50컷"),
    ("대학별환산", "70컷", "대학별환산_70컷"),
    ("대학별환산", "80컷", "대학별환산_80컷"),
    ("대학별환산", "100컷","대학별환산_100컷"),
    ("대학별환산", "총점",  "대학별환산_총점"),
    ("학생부등급", "최고",  "학생부등급_최고"),
    ("학생부등급", "평균",  "학생부등급_평균"),
    ("학생부등급", "50컷", "학생부등급_50컷"),
    ("학생부등급", "70컷", "학생부등급_70컷"),
    ("학생부등급", "80컷", "학생부등급_80컷"),
    ("학생부등급", "90컷", "학생부등급_90컷"),
    ("학생부등급", "최저",  "학생부등급_최저"),
    (None, "기준",         "기준"),
    (None, "반영교과",     "반영교과"),
]

# 그룹 병합 위치 (1-indexed 컬럼)
SUSI_RESULT_GROUP_MERGES = {
    "대학별환산": (14, 20),   # N~T (1-based: 14~20)
    "학생부등급": (21, 27),   # U~AA (1-based: 21~27)
}


def _col_letter(col_1based: int) -> str:
    return get_column_letter(col_1based)


def write_susi_result_sheet(ws, rows: list[dict]) -> None:
    """susi_result 시트: 2단 헤더 + 데이터"""
    # Row 1: 그룹 헤더
    for col_idx, (group, sub, _) in enumerate(SUSI_RESULT_SCHEMA, start=1):
        if group:
            c = ws.cell(row=1, column=col_idx, value=group)
            style_header_cell(c)

    # 그룹 병합
    for group_name, (start_col, end_col) in SUSI_RESULT_GROUP_MERGES.items():
        ws.merge_cells(
            start_row=1, start_column=start_col,
            end_row=1, end_column=end_col
        )

    # Row 2: 컬럼명
    for col_idx, (_, sub, _) in enumerate(SUSI_RESULT_SCHEMA, start=1):
        c = ws.cell(row=2, column=col_idx, value=sub)
        style_header_cell(c, HEADER_FILL_MID)

    # 데이터 행 (Row 3+)
    for r_idx, row in enumerate(rows, start=3):
        for col_idx, (_, sub, json_key) in enumerate(SUSI_RESULT_SCHEMA, start=1):
            if json_key.startswith("_"):
                continue
            val = row.get(json_key)
            if val is not None:
                c = ws.cell(row=r_idx, column=col_idx, value=val)
                c.font = CELL_FONT

    # 컬럼 너비
    for col_idx, (_, sub, _) in enumerate(SUSI_RESULT_SCHEMA, start=1):
        width = max(len(sub) * 2, 10)
        ws.column_dimensions[_col_letter(col_idx)].width = width


def write_generic_sheet(ws, rows: list[dict], schema_columns: list[str]) -> None:
    """범용 시트: 1단 헤더 + 데이터"""
    # 실제 등장한 컬럼들 수집
    all_keys: list[str] = []
    seen = set()
    for col in schema_columns:
        if col not in seen:
            all_keys.append(col)
            seen.add(col)
    for row in rows:
        for k in row.keys():
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    # 헤더
    for col_idx, col_name in enumerate(all_keys, start=1):
        c = ws.cell(row=1, column=col_idx, value=col_name)
        style_header_cell(c)
        ws.column_dimensions[_col_letter(col_idx)].width = max(len(col_name) * 2, 12)

    # 데이터
    for r_idx, row in enumerate(rows, start=2):
        for col_idx, col_name in enumerate(all_keys, start=1):
            val = row.get(col_name)
            if val is not None:
                c = ws.cell(row=r_idx, column=col_idx, value=val)
                c.font = CELL_FONT


def write_error_sheet(ws, errors: list[dict]) -> None:
    headers = ["unvCd", "university", "stage", "error", "timestamp"]
    for col_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=col_idx, value=h)
        style_header_cell(c)
    for r_idx, err in enumerate(errors, start=2):
        for col_idx, h in enumerate(headers, start=1):
            c = ws.cell(row=r_idx, column=col_idx, value=err.get(h, ""))
            c.font = CELL_FONT


def write_summary_sheet(ws, sheets_data: dict[str, list[dict]], errors: list[dict]) -> None:
    ws.cell(row=1, column=1, value="항목").font = HEADER_FONT
    ws.cell(row=1, column=2, value="값").font = HEADER_FONT

    rows = [
        ("susi_result 행수", len(sheets_data.get("susi_result", []))),
        ("susi_eval 행수",   len(sheets_data.get("susi_eval", []))),
        ("jeongsi_result 행수", len(sheets_data.get("jeongsi_result", []))),
        ("jeongsi_eval 행수",   len(sheets_data.get("jeongsi_eval", []))),
        ("에러 대학수", len({e.get("unvCd") for e in errors})),
    ]

    for r_idx, (k, v) in enumerate(rows, start=2):
        ws.cell(row=r_idx, column=1, value=k).font = CELL_FONT
        ws.cell(row=r_idx, column=2, value=v).font = CELL_FONT


def write_new_columns_sheet(ws, proposals: list[dict]) -> None:
    headers = ["sheet", "candidate_name", "type", "frequency", "samples"]
    for col_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=col_idx, value=h)
        style_header_cell(c)
    for r_idx, p in enumerate(proposals, start=2):
        for col_idx, h in enumerate(headers, start=1):
            val = p.get(h)
            if isinstance(val, list):
                val = "; ".join(str(x) for x in val[:5])
            c = ws.cell(row=r_idx, column=col_idx, value=val)
            c.font = CELL_FONT


def load_normalized_files(normalized_dir: Path) -> dict[str, list[dict]]:
    """normalized/ 디렉토리에서 모든 JSON 로드 → 시트별 합산."""
    combined: dict[str, list[dict]] = {
        "susi_result":    [],
        "susi_eval":      [],
        "jeongsi_result": [],
        "jeongsi_eval":   [],
    }
    for json_file in sorted(normalized_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            for sheet_name, rows in data.items():
                if sheet_name in combined:
                    combined[sheet_name].extend(rows)
        except Exception as exc:
            print(f"  [경고] {json_file.name} 로드 실패: {exc}")
    return combined


def build_workbook(
    sheets_data: dict[str, list[dict]],
    errors: list[dict],
    new_columns: list[dict],
    schema: dict,
) -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)

    # 시트 1: susi_result (골든셋 양식)
    ws1 = wb.create_sheet("수시 입시결과")
    write_susi_result_sheet(ws1, sheets_data.get("susi_result", []))

    # 시트 2: susi_eval
    ws2 = wb.create_sheet("수시 평가기준")
    seed_cols = schema.get("sheets", {}).get("susi_eval", {}).get("seed_columns", [])
    write_generic_sheet(ws2, sheets_data.get("susi_eval", []), seed_cols)

    # 시트 3: jeongsi_result
    ws3 = wb.create_sheet("정시 입시결과")
    jeongsi_r_cols = schema.get("sheets", {}).get("jeongsi_result", {}).get("seed_columns", [])
    write_generic_sheet(ws3, sheets_data.get("jeongsi_result", []), jeongsi_r_cols)

    # 시트 4: jeongsi_eval
    ws4 = wb.create_sheet("정시 평가기준")
    jeongsi_e_cols = schema.get("sheets", {}).get("jeongsi_eval", {}).get("seed_columns", [])
    write_generic_sheet(ws4, sheets_data.get("jeongsi_eval", []), jeongsi_e_cols)

    # 시트 5: error
    ws5 = wb.create_sheet("error")
    write_error_sheet(ws5, errors)

    # 시트 6: summary
    ws6 = wb.create_sheet("summary")
    write_summary_sheet(ws6, sheets_data, errors)

    # 시트 7: new_columns
    ws7 = wb.create_sheet("new_columns")
    write_new_columns_sheet(ws7, new_columns)

    return wb


def build_per_univ_workbook(unvcd: str, data: dict[str, list[dict]], schema: dict) -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)

    ws1 = wb.create_sheet("수시 입시결과")
    write_susi_result_sheet(ws1, data.get("susi_result", []))

    ws2 = wb.create_sheet("수시 평가기준")
    seed_cols = schema.get("sheets", {}).get("susi_eval", {}).get("seed_columns", [])
    write_generic_sheet(ws2, data.get("susi_eval", []), seed_cols)

    ws3 = wb.create_sheet("정시 입시결과")
    jeongsi_r_cols = schema.get("sheets", {}).get("jeongsi_result", {}).get("seed_columns", [])
    write_generic_sheet(ws3, data.get("jeongsi_result", []), jeongsi_r_cols)

    ws4 = wb.create_sheet("정시 평가기준")
    jeongsi_e_cols = schema.get("sheets", {}).get("jeongsi_eval", {}).get("seed_columns", [])
    write_generic_sheet(ws4, data.get("jeongsi_eval", []), jeongsi_e_cols)

    return wb


def main():
    ap = argparse.ArgumentParser(description="엑셀 워크북 빌더")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--normalized-dir", default="output/normalized")
    ap.add_argument("--per-univ-dir",   default="output/per_university")
    ap.add_argument("--output",          default=None)
    ap.add_argument("--schema",          default="input/schema_v3.yaml")
    ap.add_argument("--errors",          default="output/logs/error_log.json")
    ap.add_argument("--new-columns",     default="output/logs/new_columns_proposals.json")
    ap.add_argument("--state",           default="output/run_state.json")
    args = ap.parse_args()

    normalized_dir = Path(args.normalized_dir)
    per_univ_dir   = Path(args.per_univ_dir)
    per_univ_dir.mkdir(parents=True, exist_ok=True)

    out_path = Path(args.output) if args.output else Path(f"output/adiga_{args.year}.xlsx")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 스키마 로드
    schema_path = Path(args.schema)
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8")) if schema_path.exists() else {}

    # 에러 로그 로드
    errors_path = Path(args.errors)
    errors: list[dict] = []
    if errors_path.exists():
        try:
            errors = json.loads(errors_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    # 신규 컬럼 후보 로드
    new_cols_path = Path(args.new_columns)
    new_columns: list[dict] = []
    if new_cols_path.exists():
        try:
            new_columns = json.loads(new_cols_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    print(f"[T5 엑셀빌드] 시작: normalized_dir={normalized_dir}")

    # 대학별 워크북 + 통합 데이터 수집
    combined: dict[str, list[dict]] = {
        "susi_result": [], "susi_eval": [],
        "jeongsi_result": [], "jeongsi_eval": [],
    }

    for json_file in sorted(normalized_dir.glob("*.json")):
        unvcd = json_file.stem
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            for sheet_name, rows in data.items():
                if sheet_name in combined:
                    combined[sheet_name].extend(rows)

            # 대학별 워크북
            wb_univ = build_per_univ_workbook(unvcd, data, schema)
            per_univ_path = per_univ_dir / f"{unvcd}.xlsx"
            wb_univ.save(str(per_univ_path))
            print(f"  [{unvcd}] 대학별 워크북 저장: {per_univ_path}")
        except Exception as exc:
            print(f"  [{unvcd}] 오류: {exc}")

    # 통합 워크북
    wb_master = build_workbook(combined, errors, new_columns, schema)
    wb_master.save(str(out_path))

    total_rows = sum(len(v) for v in combined.values())
    print(f"[T5 엑셀빌드] 완료: {out_path} (총 {total_rows:,}행)")
    for sheet, rows in combined.items():
        print(f"  {sheet}: {len(rows):,}행")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
