"""PK 정규화 + 조인 + 셀 비교.

# adapted from leejihyun/evaluate.py + 임지현 run_batch.py compare()
"""
from __future__ import annotations
import math
import pandas as pd
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Any

from .config import PK_COLUMNS, DATA_COLUMNS, PK_MATCH_THRESHOLD, CELL_MATCH_THRESHOLD, GROUP_LABEL_COL


def _univ_label(g_df, p_df) -> str:
    """표시용 대학명 — 골든 우선, 없으면 사람 출력에서."""
    for df in (g_df, p_df):
        if df is not None and not df.empty and GROUP_LABEL_COL in df.columns:
            vals = df[GROUP_LABEL_COL].dropna()
            if len(vals):
                return str(vals.iloc[0])
    return ""


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
    cell_fill_gaps: list = field(default_factory=list)     # 한쪽만 값있음(충진 차이) — 셀 일치율 분모 제외


# ───────────────────────────────────────────────────
# 셀 비교
# ───────────────────────────────────────────────────
def _is_empty(v: Any) -> bool:
    """셀이 비었는가 (None / NaN / 빈 문자열)."""
    if v is None:
        return True
    if isinstance(v, float):
        try:
            return math.isnan(v)
        except (ValueError, TypeError):
            return False
    return str(v).strip() == ""


def _decimals(x: float) -> int:
    """소수 자릿수 (말미 0 제외). 6.245 → 3, 6.25 → 2, 5.0 → 0."""
    s = repr(float(x))
    if "e" in s or "E" in s:
        return 10
    if "." not in s:
        return 0
    return len(s.split(".")[1].rstrip("0"))


def _best_match_row(g_row, p_candidates):
    """같은 PK에 묶인 크롤러 후보 행들 중, 골든 행과 셀 일치가 가장 많은 행 선택.

    전형명 과정규화('일반' 등)로 서로 다른 전형이 같은 PK로 뭉쳤을 때,
    골든이 가리키는 실제 행을 찾기 위함. (전형명은 평가에서 제외 — 회의 결정)
    """
    best, best_score = None, -1
    for i in range(len(p_candidates)):
        pr = p_candidates.iloc[i]
        score = 0
        for col in DATA_COLUMNS:
            gv, pv = g_row.get(col), pr.get(col)
            if not _is_empty(gv) and not _is_empty(pv) and _cells_equal(gv, pv):
                score += 1
        if score > best_score:
            best_score, best = score, pr
    return best


def _cells_equal(g: Any, p: Any) -> bool:
    """골든 vs 사람 셀 일치 판정.

    숫자는 '반올림 정합'을 허용 — 한쪽이 더 정밀하면(골든 6.245, 크롤러 6.25)
    덜 정밀한 쪽 자릿수의 반올림 오차(단위의 절반) 이내일 때 같은 값으로 본다.
    """
    if g is None and p is None:
        return True
    if g is None or p is None:
        return False
    if isinstance(g, (int, float)) or isinstance(p, (int, float)):
        try:
            gf = float(g); pf = float(p)
            if math.isnan(gf) and math.isnan(pf):
                return True
            if math.isnan(gf) or math.isnan(pf):
                return False
            diff = abs(gf - pf)
            if diff < 1e-3:
                return True
            # 반올림 정합: 양쪽 다 소수부가 있고 정밀도가 다를 때만(d≥1).
            # 정수끼리(모집인원 등)는 엄격 비교 — 2 vs 2.4를 같다고 보면 안 됨.
            d = min(_decimals(gf), _decimals(pf))
            if d >= 1:
                tol = 0.5 * (10 ** -d) + 1e-9
                return diff <= tol
            return False
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
    n_pk_collision = 0

    for univ in sorted(set(golden.keys()) | set(person_data.keys())):
        # univ = unvCd. 표시용 대학명은 별도로.
        g_df = golden.get(univ)
        p_df = person_data.get(univ)
        univ_label = _univ_label(g_df, p_df)

        # 사람이 시도조차 안 한 대학
        if p_df is None or p_df.empty:
            if g_df is not None and not g_df.empty:
                total_missing += len(g_df)
                total_golden += len(g_df)
                for _, grow in g_df.iterrows():
                    result.missing_rows.append({
                        "unvCd": univ,
                        "대학": grow.get("대학"),
                        "전형": grow.get("전형"),
                        "모집단위": grow.get("모집단위"),
                        "person": person_name,
                    })
            result.by_university[univ] = {
                "univ_name": univ_label,
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
                    "unvCd": univ,
                    "대학": prow.get("대학"),
                    "전형": prow.get("전형"),
                    "모집단위": prow.get("모집단위"),
                    "person": person_name,
                })
            result.by_university[univ] = {
                "univ_name": univ_label,
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

        # missing/extra 누적 (pk = (unvCd, 전형, 모집단위))
        for pk in (g_set - p_set):
            result.missing_rows.append({
                "unvCd": pk[0], "대학": univ_label, "전형": pk[1], "모집단위": pk[2],
                "person": person_name,
            })
        for pk in (p_set - g_set):
            result.extra_rows.append({
                "unvCd": pk[0], "대학": univ_label, "전형": pk[1], "모집단위": pk[2],
                "person": person_name,
            })

        # 셀 비교 (matched 행 한정)
        univ_cell_matched = univ_cell_total = 0
        if matched_keys:
            g_indexed = g_df.set_index(PK_COLUMNS)
            p_indexed = p_df.set_index(PK_COLUMNS)
            # 골든은 첫 행 사용(중복 드묾). 크롤러는 best-match로 행 선택.
            g_indexed = g_indexed[~g_indexed.index.duplicated(keep="first")]

            for pk in matched_keys:
                g_row = g_indexed.loc[pk]
                # 크롤러 후보 행들: 전형명 과정규화로 같은 PK에 여러 전형이
                # 뭉칠 수 있음 → 골든과 셀 일치가 가장 많은 행을 선택(best-match).
                p_candidates = p_indexed.loc[[pk]]
                if len(p_candidates) > 1:
                    n_pk_collision += 1
                    p_row = _best_match_row(g_row, p_candidates)
                else:
                    p_row = p_candidates.iloc[0]
                for col in DATA_COLUMNS:
                    gv = g_row.get(col)
                    pv = p_row.get(col)
                    g_empty = _is_empty(gv)
                    p_empty = _is_empty(pv)
                    # 둘 다 없음 → 비교 무의미, 건너뜀
                    if g_empty and p_empty:
                        continue
                    # 한쪽만 없음 → "긁은 값의 정확도"가 아닌 충진 차이.
                    # 셀 일치율 분모에서 제외하고 별도 카운트(충진 누락).
                    if g_empty != p_empty:
                        result.cell_fill_gaps.append({
                            "unvCd": pk[0], "대학": univ_label,
                            "전형": pk[1], "모집단위": pk[2], "컬럼": col,
                            "golden_value": gv, "person_value": pv,
                            "person": person_name,
                            "비고": "크롤러 미수집" if p_empty else "골든에 없음",
                        })
                        continue
                    # 양쪽 다 값 있음 → 실제 일치/불일치 판정
                    matched = _cells_equal(gv, pv)
                    col_match_counts[col][1] += 1
                    univ_cell_total += 1
                    if matched:
                        col_match_counts[col][0] += 1
                        univ_cell_matched += 1
                    else:
                        result.mismatched_cells.append({
                            "unvCd": pk[0],
                            "대학": univ_label,
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

        # status 결정 — 셀 일치율 단일 기준 (PK는 평가 제외: 전형명 변동 때문).
        if cell_rate is None:
            status = "fail"   # 매칭됐으나 비교 가능한 셀 없음
        elif cell_rate >= CELL_MATCH_THRESHOLD:
            status = "pass"
        else:
            status = "fail"

        result.by_university[univ] = {
            "univ_name": univ_label,
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

    # by_column 메트릭
    # summary
    pk_match_rate = (total_matched / total_golden) if total_golden else 0
    cell_match_rate = (total_cells_matched / total_cells_compared) if total_cells_compared else 0
    n_failed_univ = sum(1 for u in result.by_university.values() if u["status"] == "fail")
    n_missing_univ = sum(1 for u in result.by_university.values() if u["status"] == "missing")
    coverage = 1 - (n_missing_univ / len(result.by_university)) if result.by_university else 0

    # 셀 충진율: 매칭 행의 (비교된 셀 + 한쪽만 값) 중 양쪽 다 값 있는 비율
    n_fill_gap = len(result.cell_fill_gaps)
    cell_denom = total_cells_compared + n_fill_gap
    cell_fill_rate = (total_cells_compared / cell_denom) if cell_denom else 0

    result.summary = {
        "pk_match_rate": pk_match_rate,          # 참고용 (전형명 변동으로 평가 제외)
        "cell_match_rate": cell_match_rate,
        "cell_fill_rate": cell_fill_rate,
        "n_cell_compared": total_cells_compared,
        "n_cell_fill_gap": n_fill_gap,
        "n_pk_collision": n_pk_collision,        # best-match로 해소한 PK 충돌 수
        "n_matched": total_matched,
        "n_missing": total_missing,
        "n_extra": total_extra,
        "n_golden_total": total_golden,
        "n_failed_univ": n_failed_univ,
        "n_missing_univ": n_missing_univ,
        "coverage_pct": coverage * 100,
        # DoD = 셀 일치율 단일 기준 (PK 제외)
        "dod_pass": cell_match_rate >= CELL_MATCH_THRESHOLD,
        "cell_dod_pass": cell_match_rate >= CELL_MATCH_THRESHOLD,
    }

    return result
