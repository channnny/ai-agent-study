"""normalizer.py 단위 테스트 — 반영교과·전형명 정규화(W06 핵심 개선).

실행: cd week06 && .venv/bin/python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import NORMALIZATION_PATH  # noqa: E402
from src.normalizer import Normalizer  # noqa: E402

NZ = Normalizer(NORMALIZATION_PATH)


# ── 반영교과: 순서·약어·표기차 흡수 (false match는 방지) ──
def test_subjects_order_invariant():
    assert NZ.reflected_subjects("국,영,수,사,과") == NZ.reflected_subjects("국,수,영,사,과")


def test_subjects_abbrev_equals_fullname():
    assert NZ.reflected_subjects("국수영과") == NZ.reflected_subjects("국어,수학,영어,과학")


def test_subjects_all_synonyms_to_jeongyogwa():
    canon = NZ.reflected_subjects("전교과")
    for v in ["전,교과", "전과목", "전체교과", "전교과목", "전과목(단, 최종등록자 교과성적...)"]:
        assert NZ.reflected_subjects(v) == canon == "전교과"


def test_subjects_strip_parenthetical():
    # 괄호 주석 제거 후 과목 집합 일치
    assert NZ.reflected_subjects("외국어(영어),국어,수학,사회,과학") == NZ.reflected_subjects("국,수,영,사,과")


def test_subjects_different_subjects_do_not_match():
    # 사회 vs 과학 → 달라야 (거짓 일치 방지)
    assert NZ.reflected_subjects("국수영사") != NZ.reflected_subjects("국수영과")


def test_subjects_track_not_collapsed_to_all():
    # 인문 트랙 지정은 '전교과'로 뭉뚱그리지 않음
    assert NZ.reflected_subjects("인문: 국영수사") != "전교과"


# ── 전형명: 오타·표기 통일 ──
def test_jeonghyeong_typo_alias():
    assert NZ.jeonghyeong("특성화교고") == NZ.jeonghyeong("특성화고교")


def test_jeonghyeong_wrapper_strip():
    # "학생부종합(지역인재)" → "지역인재"
    assert NZ.jeonghyeong("학생부종합(지역인재)") == NZ.jeonghyeong("지역인재")


def test_jeonghyeong_preserves_classification_axis():
    # (종합)/(교과) 분류축은 보존 — 충돌 방지
    assert NZ.jeonghyeong("농어촌(교과)") != NZ.jeonghyeong("농어촌(종합)")
