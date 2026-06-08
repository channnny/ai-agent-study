"""3인(유찬·이지현·임지현) 크롤러 출력 → 통합 1개 데이터셋.

목표: 누락 없이 최대한 많은 데이터. 3가지 지표 동시 극대화
  - 커버리지: 행(PK=대학·전형·모집단위) 합집합 → 한 명이라도 긁으면 포함
  - 충진율:   같은 행에서 셀별로 '값 있는 것' 채택 → 한 명이라도 값 있으면 채움
  - 일치율:   여러 명 값이 다르면 합의(다수결)·신뢰도 기반 선택

셀 선택 전략(STRATEGY)은 W05 평가 기반 '항목별 신뢰도'와 '소스 합의'를 조합한다.
codex 구현에서 학습: ①source 내 PK 중복 시 best_row(최다충진) ②반올림 허용
클러스터링으로 합의 판정 ③항목별 신뢰도 우선. 골든값은 병합에 쓰지 않는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from .config import (
    CANONICAL_COLUMNS,
    DATA_COLUMNS,
    MERGE_PRIORITY,
    PK_COLUMNS,
)
from .matcher import _cells_equal, _is_empty

# 셀 선택 전략 (W06 실측 비교 결과):
#   "consensus" — 다수결 우선(2+ 합의), 동률이면 신뢰도         → 96.20% (골든 미참조, 보수적)
#   "trust"     — 항목별 신뢰도 우선, 동률이면 합의 수          → 96.82% (최고) ← 기본
#   "hybrid"    — 합의가 있으면 합의, 없으면 신뢰도             → 96.37%
# trust는 W05 평가의 '항목별 신뢰도'(build_reliability)를 함께 줄 때 최고 성능.
STRATEGY = "trust"

# 신뢰도 정보가 없을 때 동률 tiebreak (충진율·정확도 높은 순)
_PRIORITY_RANK = {p: i for i, p in enumerate(MERGE_PRIORITY)}


def _filled_count(row) -> int:
    return sum(1 for c in DATA_COLUMNS if not _is_empty(row.get(c)))


def _best_row(rows: list[dict]) -> dict:
    """같은 소스 안에서 같은 PK가 중복되면 가장 많이 채워진 행을 대표로."""
    return max(rows, key=_filled_count)


def _cluster(cands: list[tuple[str, object]]) -> list[list[tuple[str, object]]]:
    """후보를 값 동치(반올림 허용)로 군집화."""
    clusters: list[list[tuple[str, object]]] = []
    for p, v in cands:
        for cl in clusters:
            if _cells_equal(cl[0][1], v):
                cl.append((p, v))
                break
        else:
            clusters.append([(p, v)])
    return clusters


def _rank(person: str, col_reliability: dict[str, float] | None) -> float:
    """소스 우선도 점수 — 항목별 신뢰도가 있으면 사용, 없으면 고정 우선순위."""
    if col_reliability and person in col_reliability:
        return col_reliability[person]
    # 고정 우선순위를 0~1 점수로 (앞일수록 높음)
    n = max(len(_PRIORITY_RANK), 1)
    return (n - _PRIORITY_RANK.get(person, n)) / n


def pick_cell(values: list, persons: list,
              col_reliability: dict[str, float] | None = None,
              strategy: str = STRATEGY) -> tuple[object, str, bool]:
    """후보 셀 값들 중 최종값 선택.

    반환: (선택값, 채택출처, 충돌여부)
    """
    cands = [(p, v) for p, v in zip(persons, values) if not _is_empty(v)]
    if not cands:
        return None, "", False
    if len(cands) == 1:
        return cands[0][1], cands[0][0], False

    clusters = _cluster(cands)
    conflict = len(clusters) > 1

    def cluster_rep(cl):
        # 군집 내 대표값 = 가장 신뢰도 높은 소스의 값/출처
        p, v = max(cl, key=lambda pv: _rank(pv[0], col_reliability))
        return v, p

    if not conflict:
        v, p = cluster_rep(clusters[0])
        return v, p, False

    # 군집별 합의 수(소스 개수)
    sizes = [len({p for p, _ in cl}) for cl in clusters]
    max_size = max(sizes)

    if strategy == "trust":
        # 신뢰도 최고 후보 → 동률이면 합의 큰 군집
        best = max(
            cands,
            key=lambda pv: (_rank(pv[0], col_reliability),
                            len([1 for cl in clusters if (pv in cl)])),
        )
        return best[1], best[0], True

    if strategy == "consensus" or strategy == "hybrid":
        # 합의(2+)가 있으면 가장 큰 합의 군집 채택
        if max_size >= 2:
            winners = [cl for cl, sz in zip(clusters, sizes) if sz == max_size]
            # 합의 군집이 여럿이면 신뢰도 합이 큰 군집
            best_cl = max(winners, key=lambda cl: sum(_rank(p, col_reliability) for p, _ in cl))
            v, p = cluster_rep(best_cl)
            return v, p, True
        # 합의 없음(전부 1) → 신뢰도 우선
        v, p = cluster_rep(max(clusters, key=lambda cl: _rank(cl[0][0], col_reliability)))
        return v, p, True

    # fallback
    v, p = cluster_rep(clusters[0])
    return v, p, True


def merge_persons(
    person_data: dict[str, dict[str, pd.DataFrame]],
    source_reliability: dict[str, dict[str, float]] | None = None,
    strategy: str = STRATEGY,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """{사람: {대학: df}} → ({대학: 통합 df}, lineage).

    source_reliability: {column: {person: cell_match_rate}} — W05 평가 항목별 신뢰도.
                        None이면 고정 우선순위(MERGE_PRIORITY) 사용.
    """
    persons = list(person_data.keys())
    all_univ: set[str] = set()
    for d in person_data.values():
        all_univ |= set(d.keys())

    merged: dict[str, pd.DataFrame] = {}
    lineage_rows: list[dict] = []

    for univ in sorted(all_univ):
        # 대학별 각 사람의 PK→대표행(best_row)
        per_person_rows: dict[str, dict[tuple, dict]] = {}
        for p in persons:
            df = person_data[p].get(univ)
            if df is None or df.empty:
                continue
            bucket: dict[tuple, list[dict]] = {}
            for rec in df.to_dict("records"):
                pk = tuple(rec.get(c) for c in PK_COLUMNS)
                if all(x is not None and x == x for x in pk):  # None/NaN 제외
                    bucket.setdefault(pk, []).append(rec)
            per_person_rows[p] = {pk: _best_row(rows) for pk, rows in bucket.items()}

        if not per_person_rows:
            continue

        all_pk: set[tuple] = set()
        for rows in per_person_rows.values():
            all_pk |= set(rows.keys())

        out_rows = []
        for pk in all_pk:
            rec = {c: None for c in CANONICAL_COLUMNS}
            rec["대학"], rec["전형"], rec["모집단위"] = pk
            havers = [p for p in persons if p in per_person_rows and pk in per_person_rows[p]]
            for col in DATA_COLUMNS:
                vals = [per_person_rows[p][pk].get(col) for p in havers]
                col_rel = source_reliability.get(col) if source_reliability else None
                chosen, src, conflict = pick_cell(vals, havers, col_rel, strategy)
                rec[col] = chosen
                if conflict:
                    lineage_rows.append({
                        "대학": pk[0], "전형": pk[1], "모집단위": pk[2], "항목": col,
                        "채택값": chosen, "채택출처": src,
                        **{f"_{p}": (per_person_rows[p][pk].get(col) if p in havers else None)
                           for p in persons},
                    })
            out_rows.append(rec)

        if out_rows:
            merged[univ] = pd.DataFrame(out_rows, columns=CANONICAL_COLUMNS)

    lineage_cols = ["대학", "전형", "모집단위", "항목", "채택값", "채택출처"] + [f"_{p}" for p in persons]
    lineage = pd.DataFrame(lineage_rows, columns=lineage_cols)
    return merged, lineage


def build_reliability(source_results: dict) -> dict[str, dict[str, float]]:
    """W05 평가 결과 → {column: {person: cell_match_rate}} 항목별 신뢰도.

    항목(8개)별 집계만 사용(대학·셀 단위 골든값 미사용) → 평가 독립성 유지.
    """
    rel: dict[str, dict[str, float]] = {c: {} for c in DATA_COLUMNS}
    for person, result in source_results.items():
        for col in DATA_COLUMNS:
            rate = result.by_column.get(col)
            if rate is not None:
                rel[col][person] = float(rate)
    return rel


def flatten_merged(merged: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """{대학: df} → 단일 DataFrame (canonical 스키마, 정렬)."""
    if not merged:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    df = pd.concat(merged.values(), ignore_index=True)
    df = df.sort_values(PK_COLUMNS, kind="stable").reset_index(drop=True)
    return df[CANONICAL_COLUMNS]
