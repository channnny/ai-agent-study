from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import CANONICAL_COLUMNS
from src.integrator import flatten_integrated, integrate_sources


def _df(rows):
    return pd.DataFrame(rows, columns=CANONICAL_COLUMNS)


def test_union_keeps_rows_from_all_sources():
    sources = {
        "yuchan": {
            "테스트대학교": _df([
                {"대학": "테스트대학교", "전형": "일반", "모집단위": "수학과", "모집인원": 10},
            ])
        },
        "lee": {
            "테스트대학교": _df([
                {"대학": "테스트대학교", "전형": "지역", "모집단위": "물리학과", "모집인원": 5},
            ])
        },
    }
    integrated, lineage, source_summary = integrate_sources(sources)
    flat = flatten_integrated(integrated)

    assert len(flat) == 2
    assert set(flat["모집단위"]) == {"수학과", "물리학과"}
    assert len(lineage) == 2
    assert not source_summary.empty


def test_consensus_beats_single_conflict():
    sources = {
        "yuchan": {
            "테스트대학교": _df([
                {"대학": "테스트대학교", "전형": "일반", "모집단위": "수학과", "모집인원": 10},
            ])
        },
        "lee": {
            "테스트대학교": _df([
                {"대학": "테스트대학교", "전형": "일반", "모집단위": "수학과", "모집인원": 10},
            ])
        },
        "lim": {
            "테스트대학교": _df([
                {"대학": "테스트대학교", "전형": "일반", "모집단위": "수학과", "모집인원": 11},
            ])
        },
    }
    integrated, lineage, _ = integrate_sources(sources)
    row = flatten_integrated(integrated).iloc[0]

    assert row["모집인원"] == 10
    assert lineage.iloc[0]["충돌항목"] == "모집인원"


def test_single_non_empty_value_fills_gap():
    sources = {
        "yuchan": {
            "테스트대학교": _df([
                {"대학": "테스트대학교", "전형": "일반", "모집단위": "수학과", "모집인원": None},
            ])
        },
        "lee": {
            "테스트대학교": _df([
                {"대학": "테스트대학교", "전형": "일반", "모집단위": "수학과", "모집인원": 7},
            ])
        },
    }
    integrated, _, _ = integrate_sources(sources)
    row = flatten_integrated(integrated).iloc[0]

    assert row["모집인원"] == 7

