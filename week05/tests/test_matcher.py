"""Matcher 단위 테스트 — 미니 fixture로 PK 매칭률·셀 일치율 손계산 검증."""
from __future__ import annotations
import pandas as pd
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.matcher import evaluate_person, _cells_equal
from src.config import CANONICAL_COLUMNS


# ─────────────────────────────────────
# 미니 fixture: 골든 5행, 사람A 5행 중 3개만 일치
# ─────────────────────────────────────
def _mk(rows):
    """rows: list of dict. 누락 컬럼은 None."""
    return pd.DataFrame(rows, columns=CANONICAL_COLUMNS)


UNV = "0009999"  # 테스트 대학 unvCd


@pytest.fixture
def golden_mini():
    return {
        UNV: _mk([
            {"unvCd": UNV, "대학": "테스트대학교", "전형": "일반", "모집단위": "수학과", "모집인원": 10, "경쟁률": 5.5},
            {"unvCd": UNV, "대학": "테스트대학교", "전형": "일반", "모집단위": "물리학과", "모집인원": 8, "경쟁률": 4.2},
            {"unvCd": UNV, "대학": "테스트대학교", "전형": "일반", "모집단위": "화학과", "모집인원": 6, "경쟁률": 3.1},
            {"unvCd": UNV, "대학": "테스트대학교", "전형": "지역", "모집단위": "수학과", "모집인원": 3, "경쟁률": 2.5},
            {"unvCd": UNV, "대학": "테스트대학교", "전형": "지역", "모집단위": "물리학과", "모집인원": 2, "경쟁률": 1.8},
        ])
    }


@pytest.fixture
def person_mini():
    """사람A: 5개 PK 중 3개는 골든과 일치, 2개는 골든에 없음. 셀값 일부 불일치."""
    return {
        UNV: _mk([
            {"unvCd": UNV, "대학": "테스트대학교", "전형": "일반", "모집단위": "수학과",   "모집인원": 10, "경쟁률": 5.5},  # 완벽 일치
            {"unvCd": UNV, "대학": "테스트대학교", "전형": "일반", "모집단위": "물리학과", "모집인원": 8,  "경쟁률": 4.5},  # 경쟁률 mismatch
            {"unvCd": UNV, "대학": "테스트대학교", "전형": "일반", "모집단위": "화학과",   "모집인원": 5,  "경쟁률": 3.1},  # 모집인원 mismatch
            {"unvCd": UNV, "대학": "테스트대학교", "전형": "신규", "모집단위": "통계학과", "모집인원": 4,  "경쟁률": 2.0},  # 골든에 없음 (extra)
            {"unvCd": UNV, "대학": "테스트대학교", "전형": "신규", "모집단위": "지구과학", "모집인원": 3,  "경쟁률": 1.5},  # 골든에 없음 (extra)
        ])
    }


class TestCellsEqual:
    def test_both_none(self):
        assert _cells_equal(None, None) is True

    def test_one_none(self):
        assert _cells_equal(None, 5) is False
        assert _cells_equal(5, None) is False

    def test_float_near(self):
        assert _cells_equal(1.0, 1.0001) is True   # 1e-3 이내
        assert _cells_equal(1.0, 1.01) is False    # 1e-3 초과

    def test_string(self):
        assert _cells_equal("전교과", "전교과") is True
        assert _cells_equal("전교과", "전 교과") is False  # PK가 아니라 셀 비교라 strip만


class TestEvaluatePersonMini:
    def test_pk_matching(self, golden_mini, person_mini):
        r = evaluate_person(golden_mini, person_mini, "tester")
        # 골든 5행, 사람 5행. PK 일치 3개 (수학/물리/화학 — 일반).
        assert r.summary["n_matched"] == 3
        assert r.summary["n_golden_total"] == 5
        # PK 매칭률 = 3/5 = 60%
        assert abs(r.summary["pk_match_rate"] - 0.6) < 1e-6

    def test_missing_and_extra(self, golden_mini, person_mini):
        r = evaluate_person(golden_mini, person_mini, "tester")
        # missing: (일반, 지역×수학), (지역×물리) = 2
        assert r.summary["n_missing"] == 2
        # extra: (신규×통계), (신규×지구과학) = 2
        assert r.summary["n_extra"] == 2

    def test_cell_match_rate(self, golden_mini, person_mini):
        r = evaluate_person(golden_mini, person_mini, "tester")
        # matched 3개 × DATA_COLUMNS(8개) = 24 셀 비교 대상
        # 수학과: 모집인원 ✓, 경쟁률 ✓, 나머지 6개 None==None ✓ → 8/8
        # 물리학과: 모집인원 ✓, 경쟁률 ✗, 나머지 6개 None==None ✓ → 7/8
        # 화학과: 모집인원 ✗, 경쟁률 ✓, 나머지 6개 None==None ✓ → 7/8
        # 총 22/24 = 91.6%
        rate = r.summary["cell_match_rate"]
        assert 0.91 < rate < 0.92

    def test_by_university(self, golden_mini, person_mini):
        r = evaluate_person(golden_mini, person_mini, "tester")
        uni = r.by_university.get(UNV)
        assert uni is not None
        assert uni["n_matched"] == 3
        assert uni["n_golden"] == 5
        assert uni["n_extra"] == 2

    def test_missing_university(self, golden_mini):
        """사람이 시도조차 안 한 대학 → status=missing."""
        r = evaluate_person(golden_mini, {}, "tester")
        uni = r.by_university.get(UNV)
        assert uni["status"] == "missing"
        assert r.summary["n_matched"] == 0
        assert r.summary["n_missing"] == 5
