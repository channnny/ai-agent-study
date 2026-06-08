"""merger.py 단위 테스트 — 행 합집합 + best_row + 신뢰도/합의 셀 선택.

실행: cd week06 && .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import CANONICAL_COLUMNS  # noqa: E402
from src.merger import (  # noqa: E402
    build_reliability,
    flatten_merged,
    merge_persons,
    pick_cell,
)


def _row(univ, jh, mj, **data):
    rec = {c: None for c in CANONICAL_COLUMNS}
    rec["대학"], rec["전형"], rec["모집단위"] = univ, jh, mj
    rec.update(data)
    return rec


def _df(rows):
    return pd.DataFrame(rows, columns=CANONICAL_COLUMNS)


# ── pick_cell ──────────────────────────────────────────────
def test_pick_single_value():
    val, src, conflict = pick_cell([None, 21, None], ["yuchan", "lee", "lim"])
    assert val == 21 and src == "lee" and conflict is False


def test_pick_consensus_majority():
    # 21,21,6 → consensus 전략에서 다수결 21
    val, src, conflict = pick_cell([21, 21, 6], ["yuchan", "lee", "lim"], strategy="consensus")
    assert val == 21 and conflict is True


def test_pick_rounding_tolerant_consensus():
    # 3.0 ≈ 3.00 → 합의로 묶임(반올림 허용), 6과 충돌
    val, src, conflict = pick_cell([3.0, 3.001, 6.0], ["yuchan", "lee", "lim"], strategy="consensus")
    assert conflict is True and abs(float(val) - 3.0) < 0.01


def test_pick_trust_uses_reliability():
    # 값 갈림(10 vs 20). 신뢰도: lee 0.9 > yuchan 0.5 → trust는 lee(20) 선택
    rel = {"yuchan": 0.5, "lee": 0.9}
    val, src, conflict = pick_cell([10, 20], ["yuchan", "lee"], col_reliability=rel, strategy="trust")
    assert val == 20 and src == "lee" and conflict is True


def test_pick_all_empty():
    val, src, conflict = pick_cell([None, None], ["yuchan", "lee"])
    assert val is None and conflict is False


# ── merge_persons ──────────────────────────────────────────
def test_merge_union_and_fill():
    yu = {"가천대": _df([_row("가천대", "교과", "간호", 모집인원=10)])}
    lee = {"가천대": _df([
        _row("가천대", "교과", "간호", 경쟁률=3.0),   # 같은 PK 다른 셀
        _row("가천대", "교과", "물리", 모집인원=5),     # 유찬엔 없는 행
    ])}
    merged, lineage = merge_persons({"yuchan": yu, "lee": lee})
    out = flatten_merged(merged)
    assert len(out) == 2  # 행 합집합
    nurse = out[out["모집단위"] == "간호"].iloc[0]
    assert nurse["모집인원"] == 10 and nurse["경쟁률"] == 3.0  # 충진
    assert (out["모집단위"] == "물리").any()
    assert len(lineage) == 0  # 겹치는 셀 없음 → 충돌 없음


def test_merge_best_row_picks_most_filled():
    # 같은 소스·같은 PK 중복: 덜 채워진 행 + 더 채워진 행 → best_row(더 채워진) 채택
    yu = {"X대": _df([
        _row("X대", "종합", "A", 모집인원=21),
        _row("X대", "종합", "A", 모집인원=21, 경쟁률=4.5, 충원합격순위="3"),
    ])}
    merged, _ = merge_persons({"yuchan": yu})
    out = flatten_merged(merged)
    assert len(out) == 1
    assert out.iloc[0]["경쟁률"] == 4.5  # 더 채워진 행이 선택됨


def test_merge_trust_resolves_conflict_by_reliability():
    yu = {"X대": _df([_row("X대", "종합", "A", 모집인원=21)])}
    lim = {"X대": _df([_row("X대", "종합", "A", 모집인원=6)])}
    # 모집인원 신뢰도: lim 0.99 > yuchan 0.8 → 6 채택
    rel = {"모집인원": {"yuchan": 0.8, "lim": 0.99}}
    merged, lineage = merge_persons({"yuchan": yu, "lim": lim}, rel, strategy="trust")
    out = flatten_merged(merged)
    assert out.iloc[0]["모집인원"] == 6
    assert len(lineage) == 1


def test_build_reliability_shape():
    class _R:
        def __init__(self, bycol):
            self.by_column = bycol
    results = {"yuchan": _R({"모집인원": 0.97}), "lim": _R({"모집인원": 0.99})}
    rel = build_reliability(results)
    assert rel["모집인원"] == {"yuchan": 0.97, "lim": 0.99}
