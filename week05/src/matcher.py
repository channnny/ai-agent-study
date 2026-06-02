"""PK 정규화 + 조인 + 셀 비교.

# adapted from leejihyun/evaluate.py + 임지현 run_batch.py compare()
"""
from __future__ import annotations
import math
import pandas as pd
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Any

from .config import PK_COLUMNS, DATA_COLUMNS, PK_MATCH_THRESHOLD, CELL_MATCH_THRESHOLD


# ───────────────────────────────────────────────────
# 결과 구조
# ───────────────────────────────────────────────────
@dataclass
class PersonResult:
    person: str
    summary: dict = field(default_factory=dict)
    by_university: dict = field(default_factory=dict)  # 대학명 → metrics
    by_column: dict = field(default_factory=dict)      # 컬럼명 → match_rate
    missing_rows: list = field(default_factory=list)   # [(대학, 전형, 모집단위)]
    extra_rows: list = field(default_factory=list)
    mismatched_cells: list = field(default_factory=list)  # [(대학, 전형, 모집단위, 컬럼, golden, person, 비고)]


# ───────────────────────────────────────────────────
# 셀 비교
# ───────────────────────────────────────────────────
def _cells_equal(g: Any, p: Any) -> bool:
    """골든 vs 사람 셀 일치 판정. None은 None과만 일치. float은 ε 허용."""
    if g is None and p is None:
        return True
    if g is None or p is None:
        return False
    if isinstance(g, float) or isinstance(p, float):
        try:
            gf = float(g); pf = float(p)
            if math.isnan(gf) and math.isnan(pf):
                return True
            return abs(gf - pf) < 1e-3
        except (ValueError, TypeError):
            pass
    return str(g).strip() == str(p).strip()


def _note_for_mismatch(g: Any, p: Any) -> str:
    """비고: 사람이 보면 동치일 가능성을 표시."""
    if g is None:
        return "골든=null, 사람=값있음"
    if p is None:
        return "사람=null, 골든=값있음"
    try:
        gf = float(g); pf = float(p)
        if abs(gf - pf) < 0.1:
            return f"근접: 차이 {abs(gf-pf):.3f}"
        return f"차이: {pf - gf:+.2f}"
    except (ValueError, TypeError):
        gs, ps = str(g).strip(), str(p).strip()
        if gs.replace(",", "") == ps.replace(",", ""):
            return "콤마 차이"
        return "문자열 불일치"


# ───────────────────────────────────────────────────
# 한 사람 평가
# ───────────────────────────────────────────────────
def evaluate_person(
    golden: dict[str, pd.DataFrame],
    person_data: dict[str, pd.DataFrame],
    person_name: str,
) -> PersonResult:
    """한 사람의 산출물을 골든셋과 비교 → PersonResult."""
    result = PersonResult(person=person_name)

    # 컬럼별 일치/총 카운트
    col_match_counts = defaultdict(lambda: [0, 0])  # 컬럼 → [matched, total]
    total_matched = total_missing = total_extra = total_golden = 0
    total_cells_compared = total_cells_matched = 0

    for univ in sorted(set(golden.keys()) | set(person_data.keys())):
        g_df = golden.get(univ)
        p_df = person_data.get(univ)

        # 사람이 시도조차 안 한 대학
        if p_df is None or p_df.empty:
            if g_df is not None and not g_df.empty:
                total_missing += len(g_df)
                total_golden += len(g_df)
                for _, grow in g_df.iterrows():
                    result.missing_rows.append({
                        "대학": grow.get("대학"),
                        "전형": grow.get("전형"),
                        "모집단위": grow.get("모집단위"),
                        "person": person_name,
                    })
            result.by_university[univ] = {
                "status": "missing",
                "pk_match_rate": None,
                "cell_match_rate": None,
                "n_matched": 0,
                "n_golden": len(g_df) if g_df is not None else 0,
                "n_extra": 0,
            }
            continue

        # 골든에 없는 대학은 extra만 카운트
        if g_df is None or g_df.empty:
            for _, prow in p_df.iterrows():
                total_extra += 1
                result.extra_rows.append({
                    "대학": prow.get("대학"),
                    "전형": prow.get("전형"),
                    "모집단위": prow.get("모집단위"),
                    "person": person_name,
                })
            result.by_university[univ] = {
                "status": "fail",  # 골든에 없는데 사람만 있는 케이스
                "pk_match_rate": None,
                "cell_match_rate": None,
                "n_matched": 0,
                "n_golden": 0,
                "n_extra": len(p_df),
            }
            continue

        # PK 조인
        g_keys = g_df.set_index(PK_COLUMNS).index
        p_keys = p_df.set_index(PK_COLUMNS).index
        g_set = set(g_keys.tolist())
        p_set = set(p_keys.tolist())
        matched_keys = g_set & p_set

        n_golden = len(g_set)
        n_matched = len(matched_keys)
        n_missing = len(g_set - p_set)
        n_extra = len(p_set - g_set)

        # missing/extra 누적
        for pk in (g_set - p_set):
            result.missing_rows.append({
                "대학": pk[0], "전형": pk[1], "모집단위": pk[2],
                "person": person_name,
            })
        for pk in (p_set - g_set):
            result.extra_rows.append({
                "대학": pk[0], "전형": pk[1], "모집단위": pk[2],
                "person": person_name,
            })

        # 셀 비교 (matched 행 한정)
        univ_cell_matched = univ_cell_total = 0
        if matched_keys:
            g_indexed = g_df.set_index(PK_COLUMNS)
            p_indexed = p_df.set_index(PK_COLUMNS)
            # PK 중복 가능성 — 첫 번째만 사용
            g_indexed = g_indexed[~g_indexed.index.duplicated(keep="first")]
            p_indexed = p_indexed[~p_indexed.index.duplicated(keep="first")]

            for pk in matched_keys:
                g_row = g_indexed.loc[pk]
                p_row = p_indexed.loc[pk]
                for col in DATA_COLUMNS:
                    gv = g_row.get(col)
                    pv = p_row.get(col)
                    matched = _cells_equal(gv, pv)
                    col_match_counts[col][1] += 1
                    univ_cell_total += 1
                    if matched:
                        col_match_counts[col][0] += 1
                        univ_cell_matched += 1
                    else:
                        result.mismatched_cells.append({
                            "대학": pk[0],
                            "전형": pk[1],
                            "모집단위": pk[2],
                            "컬럼": col,
                            "golden_value": gv,
                            "person_value": pv,
                            "person": person_name,
                            "비고": _note_for_mismatch(gv, pv),
                        })

        total_matched += n_matched
        total_missing += n_missing
        total_extra += n_extra
        total_golden += n_golden
        total_cells_matched += univ_cell_matched
        total_cells_compared += univ_cell_total

        pk_rate = (n_matched / n_golden) if n_golden else None
        cell_rate = (univ_cell_matched / univ_cell_total) if univ_cell_total else None

        # status 결정
        if pk_rate is None:
            status = "fail"
        elif pk_rate >= PK_MATCH_THRESHOLD and (cell_rate or 0) >= CELL_MATCH_THRESHOLD:
            status = "pass"
        else:
            status = "fail"

        result.by_university[univ] = {
            "status": status,
            "pk_match_rate": pk_rate,
            "cell_match_rate": cell_rate,
            "n_matched": n_matched,
            "n_golden": n_golden,
            "n_extra": n_extra,
        }

    # by_column 메트릭
    for col, (mch, tot) in col_match_counts.items():
        result.by_column[col] = (mch / tot) if tot else None

    # summary
    pk_match_rate = (total_matched / total_golden) if total_golden else 0
    cell_match_rate = (total_cells_matched / total_cells_compared) if total_cells_compared else 0
    n_failed_univ = sum(1 for u in result.by_university.values() if u["status"] == "fail")
    n_missing_univ = sum(1 for u in result.by_university.values() if u["status"] == "missing")
    coverage = 1 - (n_missing_univ / len(result.by_university)) if result.by_university else 0

    result.summary = {
        "pk_match_rate": pk_match_rate,
        "cell_match_rate": cell_match_rate,
        "n_matched": total_matched,
        "n_missing": total_missing,
        "n_extra": total_extra,
        "n_golden_total": total_golden,
        "n_failed_univ": n_failed_univ,
        "n_missing_univ": n_missing_univ,
        "coverage_pct": coverage * 100,
        "pk_dod_pass": pk_match_rate >= PK_MATCH_THRESHOLD,
        "cell_dod_pass": cell_match_rate >= CELL_MATCH_THRESHOLD,
    }

    return result
