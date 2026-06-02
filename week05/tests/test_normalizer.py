"""Normalizer 단위 테스트."""
from __future__ import annotations
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.normalizer import Normalizer
from src.config import NORMALIZATION_PATH


@pytest.fixture(scope="module")
def n():
    return Normalizer(NORMALIZATION_PATH)


# ─────────────────────────────────────
# cell / null / number
# ─────────────────────────────────────
class TestCell:
    def test_none_passthrough(self, n):
        assert n.cell(None) is None
        assert n.cell("") is None
        assert n.cell("  ") is None

    def test_null_tokens(self, n):
        assert n.cell("-") is None
        assert n.cell("–") is None
        assert n.cell("N/A") is None
        assert n.cell("해당없음") is None

    def test_passthrough(self, n):
        assert n.cell("가천대학교") == "가천대학교"


class TestNumber:
    def test_basic(self, n):
        assert n.number("12.5") == 12.5
        assert n.number("100") == 100.0

    def test_thousand_separator(self, n):
        assert n.number("1,234") == 1234.0

    def test_percent(self, n):
        assert n.number("12.5%") == 12.5

    def test_unit_suffix(self, n):
        assert n.number("25명") == 25.0
        assert n.number("3배수") == 3.0
        assert n.number("12점") == 12.0

    def test_about_prefix(self, n):
        assert n.number("약 25명") == 25.0

    def test_null_inputs(self, n):
        assert n.number(None) is None
        assert n.number("-") is None
        assert n.number("미공개") is None

    def test_invalid(self, n):
        assert n.number("hello") is None


class TestInteger:
    def test_basic(self, n):
        assert n.integer("5") == 5
        assert n.integer("5.0") == 5
        assert n.integer("4.7") == 5  # round


# ─────────────────────────────────────
# PK 정규화
# ─────────────────────────────────────
class TestPK:
    def test_basic(self, n):
        assert n.pk("가천대학교") == "가천대학교"
        assert n.pk("  가천대학교  ") == "가천대학교"

    def test_middle_dot_spacing(self, n):
        """중간점 주변 공백 제거 — 골든 vs 이지현 표기 차이."""
        assert n.pk("금융·빅데이터학부") == "금융·빅데이터학부"
        assert n.pk("금융 · 빅데이터학부") == "금융·빅데이터학부"

    def test_paren_spacing(self, n):
        assert n.pk("( 종합 )") == "(종합)"
        assert n.pk("농어촌 ( 교과 )") == "농어촌(교과)"

    def test_korean_english_space(self, n):
        """AI 인문대학 → AI인문대학 (영문+한글 사이 공백 제거)."""
        assert n.pk("AI 인문대학") == "AI인문대학"
        assert n.pk("AI인문대학") == "AI인문대학"


# ─────────────────────────────────────
# 전형명 정규화
# ─────────────────────────────────────
class TestJeonghyeong:
    def test_strip_suffix(self, n):
        """'... 전형' 접미 제거."""
        assert n.jeonghyeong("가천바람개비 전형") == "가천바람개비"
        assert n.jeonghyeong("논술전형") == "논술"

    def test_strip_wrapper(self, n):
        """'학생부종합(X)' / '학생부교과(X)' wrapper 제거."""
        assert n.jeonghyeong("학생부교과(논술 전형)") == "논술"
        assert n.jeonghyeong("학생부종합(가천바람개비 전형)") == "가천바람개비"

    def test_strip_annotation(self, n):
        """'(2026학년도부터 ...)' 부가 주석 제거."""
        assert n.jeonghyeong("특성화고교 전형( 2026학년도부터 교과전형으로 선발 )") == "특성화고교"

    def test_no_change(self, n):
        assert n.jeonghyeong("실기우수자") == "실기우수자"
        assert n.jeonghyeong("기회균형") == "기회균형"

    def test_null(self, n):
        assert n.jeonghyeong(None) is None
        assert n.jeonghyeong("") is None


# ─────────────────────────────────────
# 반영교과
# ─────────────────────────────────────
class TestReflectedSubjects:
    def test_alias(self, n):
        assert n.reflected_subjects("전 과목") == "전교과"
        assert n.reflected_subjects("전과목") == "전교과"
        assert n.reflected_subjects("전체") == "전교과"

    def test_middle_dot_to_comma(self, n):
        assert n.reflected_subjects("국·수·영·사") == "국,수,영,사"

    def test_whitespace_to_comma(self, n):
        assert n.reflected_subjects("국 수 영 사") == "국,수,영,사"

    def test_null(self, n):
        assert n.reflected_subjects(None) is None
        assert n.reflected_subjects("-") is None
