"""충진율·검증 리포트 생성 — T7 단계

사용법:
    python report.py \\
        --normalized-dir output/normalized \\
        --schema input/schema_v3.yaml \\
        --eval-report output/evaluation_report.xlsx \\
        --errors output/logs/error_log.json \\
        --new-columns output/logs/new_columns_proposals.json \\
        --out output/validation_report.md
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


# ─────────────────────────────────────────────
# 충진율 계산
# ─────────────────────────────────────────────

def calc_fill_rates(
    normalized_dir: Path,
    schema: dict,
) -> dict[str, dict[str, float]]:
    """시트·컬럼별 채움 비율 계산."""
    # 시트별 컬럼 누적
    col_totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    col_filled: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    sheet_key_map = {
        "susi_result":    "seed_columns",
        "susi_eval":      "seed_columns",
        "jeongsi_result": "seed_columns",
        "jeongsi_eval":   "seed_columns",
    }

    for json_file in sorted(normalized_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        for sheet_name, rows in data.items():
            if not isinstance(rows, list):
                continue
            key = sheet_key_map.get(sheet_name, "seed_columns")
            schema_cols = (
                schema.get("sheets", {}).get(sheet_name, {}).get(key, [])
                or schema.get("sheets", {}).get(sheet_name, {}).get("columns", [])
            )
            # 컬럼명 추출 (columns는 dict 리스트일 수도)
            if schema_cols and isinstance(schema_cols[0], dict):
                schema_col_names = [c.get("name", "") for c in schema_cols]
            else:
                schema_col_names = schema_cols

            for row in rows:
                for col in schema_col_names:
                    if col in ("raw_text",):
                        continue
                    col_totals[sheet_name][col] += 1
                    val = row.get(col)
                    if val is not None and str(val).strip() not in {"", "-", "–"}:
                        col_filled[sheet_name][col] += 1

    # 비율 계산
    fill_rates: dict[str, dict[str, float]] = {}
    for sheet_name in col_totals:
        fill_rates[sheet_name] = {}
        for col, total in col_totals[sheet_name].items():
            filled = col_filled[sheet_name].get(col, 0)
            fill_rates[sheet_name][col] = filled / total if total else 0.0

    return fill_rates


def calc_sheet_avg(fill_rates: dict[str, float]) -> float:
    if not fill_rates:
        return 0.0
    return sum(fill_rates.values()) / len(fill_rates)


# ─────────────────────────────────────────────
# 평가 리포트 파싱 (summary 시트)
# ─────────────────────────────────────────────

def load_eval_summary(eval_report_path: Path) -> dict:
    if not HAS_OPENPYXL or not eval_report_path.exists():
        return {}
    try:
        wb = openpyxl.load_workbook(str(eval_report_path), read_only=True, data_only=True)
        if "summary" not in wb.sheetnames:
            return {}
        ws = wb["summary"]
        result = {}
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row and row[0] and row[1]:
                result[str(row[0])] = row[1]
        return result
    except Exception:
        return {}


# ─────────────────────────────────────────────
# 마크다운 리포트 생성
# ─────────────────────────────────────────────

def build_report(
    fill_rates: dict[str, dict[str, float]],
    eval_summary: dict,
    errors: list[dict],
    new_columns: list[dict],
    normalized_dir: Path,
    generated_at: str,
) -> str:
    lines: list[str] = []

    # 헤더
    lines += [
        "# adiga 입시 데이터 수집 — 검증 리포트",
        "",
        f"> 생성일시: {generated_at}",
        "",
        "---",
        "",
    ]

    # 1. 실행 요약
    total_files = len(list(normalized_dir.glob("*.json")))
    error_unvs = len({e.get("unvCd", "") for e in errors})
    lines += [
        "## 1. 실행 요약",
        "",
        f"| 항목 | 값 |",
        f"|---|---|",
        f"| 처리 대학 수 | {total_files}개 |",
        f"| 에러 대학 수 | {error_unvs}개 |",
        f"| 에러 건수 | {len(errors)}건 |",
        "",
    ]

    # 2. 시트별 충진율
    lines += [
        "## 2. 시트별 충진율",
        "",
    ]

    for sheet_name in ["susi_result", "susi_eval", "jeongsi_result", "jeongsi_eval"]:
        rates = fill_rates.get(sheet_name, {})
        avg = calc_sheet_avg(rates)
        lines += [
            f"### 2.{list(fill_rates.keys()).index(sheet_name) + 1 if sheet_name in fill_rates else '?'}. {sheet_name}",
            "",
            f"평균 채움률: **{avg:.0%}**",
            "",
            "| 컬럼 | 채움률 |",
            "|---|---|",
        ]
        for col, rate in sorted(rates.items(), key=lambda x: -x[1]):
            flag = " ⚠" if rate < 0.3 else ""
            lines.append(f"| {col} | {rate:.0%}{flag} |")
        lines.append("")

    # 3. 평가 결과 (골든셋 비교)
    lines += [
        "## 3. 골든셋 비교 결과 (susi_result)",
        "",
    ]
    if eval_summary:
        lines += [
            "| 지표 | 값 |",
            "|---|---|",
        ]
        for k, v in eval_summary.items():
            lines.append(f"| {k} | {v} |")
        pk_rate_str = eval_summary.get("PK 매칭률", "")
        try:
            pk_rate = float(str(pk_rate_str).replace("%", ""))
            if pk_rate >= 85:
                lines.append(f"\n**PK 매칭률 {pk_rate_str} → DoD 충족 (≥ 85%)**")
            else:
                lines.append(f"\n**PK 매칭률 {pk_rate_str} → DoD 미충족 (< 85%)**")
        except ValueError:
            pass
        lines.append("")
    else:
        lines += ["평가 리포트 없음 (T6 미실행 또는 실패)", ""]

    # 4. 신규 컬럼 후보
    lines += [
        "## 4. 신규 컬럼 후보 (LLM 제안)",
        "",
    ]
    if new_columns:
        lines += [
            "| 시트 | 후보 컬럼명 | 타입 | 등장 빈도 | 샘플 |",
            "|---|---|---|---|---|",
        ]
        for p in new_columns:
            samples = "; ".join(str(s) for s in (p.get("samples") or [])[:3])
            lines.append(
                f"| {p.get('sheet','')} | {p.get('candidate_name','')} "
                f"| {p.get('type','')} | {p.get('frequency','')} | {samples} |"
            )
        lines.append("")
    else:
        lines += ["신규 컬럼 후보 없음", ""]

    # 5. 이슈 및 권고사항
    lines += [
        "## 5. 이슈 및 권고사항",
        "",
    ]
    if errors:
        lines += [
            "### 5.1 에러 목록",
            "",
            "| unvCd | 대학 | 단계 | 오류 |",
            "|---|---|---|---|",
        ]
        for e in errors[:50]:
            msg = str(e.get("error", ""))[:80]
            lines.append(f"| {e.get('unvCd','')} | {e.get('university','')} | {e.get('stage','')} | {msg} |")
        if len(errors) > 50:
            lines.append(f"\n_... 외 {len(errors) - 50}건 (error_log.json 참조)_")
        lines.append("")

    # 충진율 낮은 컬럼 경고
    low_fill_cols: list[tuple[str, str, float]] = []
    for sheet_name, rates in fill_rates.items():
        for col, rate in rates.items():
            if rate < 0.3:
                low_fill_cols.append((sheet_name, col, rate))

    if low_fill_cols:
        lines += [
            "### 5.2 충진율 30% 미만 컬럼",
            "",
            "| 시트 | 컬럼 | 채움률 |",
            "|---|---|---|",
        ]
        for sheet_name, col, rate in sorted(low_fill_cols, key=lambda x: x[2]):
            lines.append(f"| {sheet_name} | {col} | {rate:.0%} |")
        lines.append("")

    lines += [
        "---",
        "",
        f"_자동 생성: adiga 에이전트 v1.0_",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="검증 리포트 생성")
    ap.add_argument("--normalized-dir", default="output/normalized")
    ap.add_argument("--schema",         default="input/schema_v3.yaml")
    ap.add_argument("--eval-report",    default="output/evaluation_report.xlsx")
    ap.add_argument("--errors",         default="output/logs/error_log.json")
    ap.add_argument("--new-columns",    default="output/logs/new_columns_proposals.json")
    ap.add_argument("--out",            default="output/validation_report.md")
    args = ap.parse_args()

    print("[T7 리포트] 시작")

    # 스키마 로드
    schema_path = Path(args.schema)
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8")) if schema_path.exists() else {}

    # 충진율 계산
    normalized_dir = Path(args.normalized_dir)
    fill_rates = calc_fill_rates(normalized_dir, schema) if normalized_dir.exists() else {}

    # 평가 요약
    eval_summary = load_eval_summary(Path(args.eval_report))

    # 에러 로그
    errors_path = Path(args.errors)
    errors: list[dict] = []
    if errors_path.exists():
        try:
            errors = json.loads(errors_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    # 신규 컬럼 후보
    nc_path = Path(args.new_columns)
    new_columns: list[dict] = []
    if nc_path.exists():
        try:
            new_columns = json.loads(nc_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_text = build_report(
        fill_rates, eval_summary, errors, new_columns,
        normalized_dir, generated_at,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_text, encoding="utf-8")

    print(f"[T7 리포트] 완료: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
