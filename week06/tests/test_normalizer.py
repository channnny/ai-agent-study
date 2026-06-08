from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import NORMALIZATION_PATH
from src.normalizer import W06Normalizer


@pytest.fixture(scope="module")
def n():
    return W06Normalizer(NORMALIZATION_PATH)


def test_strip_leading_category_wrapper(n):
    assert n.jeonghyeong("(학생부교과)일반") == "일반"
    assert n.jeonghyeong("(학생부종합)지역인재") == "지역인재"


def test_strip_trailing_category_wrapper(n):
    assert n.jeonghyeong("학교장추천(학생부교과)") == "학교장추천"


def test_safe_aliases(n):
    assert n.jeonghyeong("특성화교고") == "특성화고교"
    assert n.jeonghyeong("농어촌학생)(정원외") == "농어촌학생"


def test_reflected_subjects_long_explanation(n):
    value = "전과목 (본 전형에서는 전과목을 평가하며 교과성적을 산출)"
    assert n.reflected_subjects(value) == "전교과"

