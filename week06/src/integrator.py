"""3인 크롤러 산출물 통합.

원칙:
- 골든셋 값을 통합 데이터에 복사하지 않는다. 골든은 평가에만 사용한다.
- 같은 PK에 여러 소스가 값을 낸 경우 W06 실측 비교에서 가장 좋은
  유찬 → 임지현 → 이지현 순으로 선택한다.
- 한 소스만 값을 가진 셀은 누락 방지를 위해 그대로 채택한다.
- 어느 한 소스만 값을 가진 셀은 누락 방지를 위해 그대로 채택한다.
"""
from __future__ import annotations

import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from week05.src.matcher import PersonResult, _cells_equal, _is_empty  # noqa: E402

from .config import CANONICAL_COLUMNS, DATA_COLUMNS, PK_COLUMNS, SOURCE_LABELS


# W06 전략 비교 결과:
# - Claude식 consensus: Cell 96.127%
# - Codex score:       Cell 96.622%
# - learned priority:  Cell 96.722%
# 유찬은 값이 있을 때 정밀도가 높고, 임지현은 높은 충진율로 빈칸을 메운다.
SOURCE_PRIORITY = ("yuchan", "lim", "lee")


@dataclass(frozen=True)
class CellCandidate:
    source: str
    value: Any
    source_score: float
    row_fill: int


def _filled_count(row: dict[str, Any]) -> int:
    return sum(1 for c in DATA_COLUMNS if not _is_empty(row.get(c)))


def _norm_display(value: Any) -> str:
    if _is_empty(value):
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return f"{value:.6g}"
    return str(value)


def _index_by_pk(df: pd.DataFrame) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    indexed: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    if df is None or df.empty:
        return indexed
    for _, row in df.iterrows():
        rec = row.to_dict()
        key = tuple(rec.get(c) for c in PK_COLUMNS)
        if all(key):
            indexed[key].append(rec)
    return indexed


def _best_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """동일 소스 안에서 같은 PK가 중복될 때 가장 채워진 행을 대표로 사용."""
    return max(rows, key=lambda r: (_filled_count(r), tuple(_norm_display(r.get(c)) for c in DATA_COLUMNS)))


def _source_score(
    person: str,
    source_results: dict[str, PersonResult],
    univ: str,
    column: str,
) -> float:
    """W05 평가 기반 소스 신뢰도.

    golden의 개별 셀 값을 보지 않고 집계 지표만 사용한다.
    """
    result = source_results.get(person)
    if result is None:
        return 0.5

    global_rate = result.summary.get("cell_match_rate")
    column_rate = result.by_column.get(column)
    univ_rate = None
    univ_metrics = result.by_university.get(univ)
    if univ_metrics:
        univ_rate = univ_metrics.get("cell_match_rate")

    parts = []
    if global_rate is not None:
        parts.append((0.50, float(global_rate)))
    if column_rate is not None:
        parts.append((0.30, float(column_rate)))
    if univ_rate is not None:
        parts.append((0.20, float(univ_rate)))
    if not parts:
        return 0.5
    total_weight = sum(w for w, _ in parts)
    return sum(w * v for w, v in parts) / total_weight


def _cluster_candidates(candidates: Iterable[CellCandidate]) -> list[list[CellCandidate]]:
    clusters: list[list[CellCandidate]] = []
    for cand in candidates:
        placed = False
        for cluster in clusters:
            if _cells_equal(cluster[0].value, cand.value):
                cluster.append(cand)
                placed = True
                break
        if not placed:
            clusters.append([cand])
    return clusters


def _choose_cell(
    candidates: list[CellCandidate],
) -> tuple[Any, str | None, str, bool, str]:
    """셀 후보 중 최종 값 선택.

    Returns: value, source, decision, conflict, values_display
    """
    filled = [c for c in candidates if not _is_empty(c.value)]
    if not filled:
        return None, None, "empty", False, ""

    clusters = _cluster_candidates(filled)
    conflict = len(clusters) > 1
    priority_rank = {source: rank for rank, source in enumerate(SOURCE_PRIORITY)}
    best = min(
        filled,
        key=lambda c: (
            priority_rank.get(c.source, len(SOURCE_PRIORITY)),
            -c.row_fill,
            c.source,
        ),
    )
    decision = "consensus" if not conflict and len(filled) >= 2 else "learned_priority"

    values_display = " | ".join(
        f"{SOURCE_LABELS.get(c.source, c.source)}={_norm_display(c.value)}"
        for c in sorted(filled, key=lambda x: x.source)
    )
    return best.value, best.source, decision, conflict, values_display


def integrate_sources(
    sources: dict[str, dict[str, pd.DataFrame]],
    source_results: dict[str, PersonResult] | None = None,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    """소스별 canonical DataFrame을 하나의 canonical 결과로 통합한다."""
    source_results = source_results or {}
    integrated: dict[str, list[dict[str, Any]]] = defaultdict(list)
    lineage_rows: list[dict[str, Any]] = []
    choice_counter: Counter[tuple[str, str, str]] = Counter()

    all_univs = sorted({u for data in sources.values() for u in data.keys()})
    for univ in all_univs:
        source_indexes = {
            person: _index_by_pk(data.get(univ))
            for person, data in sources.items()
            if data.get(univ) is not None and not data.get(univ).empty
        }
        all_keys = sorted({key for idx in source_indexes.values() for key in idx.keys()})

        for key in all_keys:
            source_rows = {
                person: _best_row(idx[key])
                for person, idx in source_indexes.items()
                if key in idx
            }
            row_fill_by_source = {person: _filled_count(row) for person, row in source_rows.items()}

            rec = {col: None for col in CANONICAL_COLUMNS}
            for col, value in zip(PK_COLUMNS, key):
                rec[col] = value

            lineage = {
                "대학": key[0],
                "전형": key[1],
                "모집단위": key[2],
                "참여소스": ",".join(SOURCE_LABELS.get(p, p) for p in sorted(source_rows)),
                "참여소스수": len(source_rows),
            }
            conflict_cols = []
            filled_cols = 0

            for col in DATA_COLUMNS:
                candidates = [
                    CellCandidate(
                        source=person,
                        value=row.get(col),
                        source_score=_source_score(person, source_results, univ, col),
                        row_fill=row_fill_by_source[person],
                    )
                    for person, row in source_rows.items()
                ]
                value, source, decision, conflict, values_display = _choose_cell(candidates)
                rec[col] = value
                if not _is_empty(value):
                    filled_cols += 1
                if conflict:
                    conflict_cols.append(col)
                if source:
                    choice_counter[(col, source, decision)] += 1
                lineage[f"{col}_출처"] = SOURCE_LABELS.get(source, source) if source else ""
                lineage[f"{col}_판정"] = decision
                lineage[f"{col}_후보값"] = values_display

            lineage["충진셀수"] = filled_cols
            lineage["충돌항목"] = ", ".join(conflict_cols)
            integrated[univ].append(rec)
            lineage_rows.append(lineage)

    integrated_frames = {
        univ: pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
        for univ, rows in integrated.items()
        if rows
    }

    lineage_df = pd.DataFrame(lineage_rows)
    summary_rows = []
    for (column, source, decision), count in sorted(choice_counter.items()):
        summary_rows.append({
            "항목": column,
            "채택출처": SOURCE_LABELS.get(source, source),
            "판정": decision,
            "채택셀수": count,
        })
    source_summary = pd.DataFrame(summary_rows)
    if not source_summary.empty:
        source_summary = source_summary.sort_values(["항목", "채택셀수"], ascending=[True, False])

    return integrated_frames, lineage_df, source_summary


def flatten_integrated(integrated: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if not integrated:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    return pd.concat([df for _, df in sorted(integrated.items())], ignore_index=True)
