"""셀 값 정규화 — 이지현 9섹션 사전을 MVP 4섹션만 적용.

- §3 NULL 토큰 → None
- §4 숫자 정규화 (천 단위 콤마, %, 단위 suffix)
- §6 전형구분 대분류 — 평가엔 미사용 (canonical schema에 컬럼 없음). 로드만.
- §1 반영교과 — 공백·중간점 → 콤마, "전 과목" → "전교과"

# adapted from leejihyun/handoff normalization-dictionary.md
"""
from __future__ import annotations
import re
import yaml
from pathlib import Path
from typing import Any, Optional


class Normalizer:
    def __init__(self, dict_path: Path):
        with open(dict_path, encoding="utf-8") as f:
            self.dict = yaml.safe_load(f)

        self.null_tokens = set(self.dict.get("null_tokens", []))
        self.number_patterns = self.dict.get("number_patterns", {})
        self.subject_aliases = {}
        for rule in self.dict.get("reflected_subjects", {}).get("rules", []):
            for p in rule["patterns"]:
                self.subject_aliases[p] = rule["canonical"]
        self.middle_dot = self.dict.get("reflected_subjects", {}).get("middle_dot_to_comma", "·")

    # ────────────────────────────────────────
    # 공통: 어떤 값이든 정규화
    # ────────────────────────────────────────
    def cell(self, value: Any) -> Any:
        """모든 셀에 적용. 타입 추정 후 적절한 정규화 함수 호출."""
        if value is None:
            return None
        s = str(value).strip()
        if s in self.null_tokens:
            return None
        if s == "":
            return None
        return s

    # ────────────────────────────────────────
    # 숫자
    # ────────────────────────────────────────
    def number(self, value: Any) -> Optional[float]:
        """수치형 셀 정규화. 실패 시 None."""
        c = self.cell(value)
        if c is None:
            return None
        s = str(c)
        # "N명 이하/이상" 류 꼬리말 제거 (충원합격순위 등 텍스트 표기) → 숫자만
        s = re.sub(r"\s*(명\s*)?(이하|이상|미만|초과)\s*$", "", s)
        # 천 단위 콤마 제거
        s = s.replace(self.number_patterns.get("thousand_separator", ","), "")
        # 퍼센트 기호 제거
        s = s.rstrip(self.number_patterns.get("percent_suffix", "%")).strip()
        # 단위 suffix 제거
        for suf in self.number_patterns.get("unit_suffixes", []):
            if s.endswith(suf):
                s = s[: -len(suf)].strip()
        # "약" 접두 제거
        ap = self.number_patterns.get("approximate_prefix", "약")
        if s.startswith(ap):
            s = s[len(ap):].strip()
        try:
            f = float(s)
            return round(f, 4)
        except (ValueError, TypeError):
            return None

    def integer(self, value: Any) -> Optional[int]:
        """정수형. 소수면 round."""
        n = self.number(value)
        if n is None:
            return None
        return int(round(n))

    # ────────────────────────────────────────
    # 반영교과
    # ────────────────────────────────────────
    def reflected_subjects(self, value: Any) -> Optional[str]:
        c = self.cell(value)
        if c is None:
            return None
        s = str(c)
        # 직접 매칭
        if s in self.subject_aliases:
            return self.subject_aliases[s]
        # 중간점·공백 → 콤마
        s = s.replace(self.middle_dot, ",")
        s = re.sub(r"\s+", ",", s)
        # 중복 콤마 제거
        s = re.sub(r",+", ",", s).strip(",")
        return s

    # ────────────────────────────────────────
    # 대학명 정규화 (골든·크롤러 표기 차이 흡수)
    # ────────────────────────────────────────
    @staticmethod
    def university(value: Any) -> Optional[str]:
        """대학명 표기 통일 — base 대학명으로 정규화.

        골든은 캠퍼스를 '(성심교정)'/'(인문)'/'(원주)'로, 어디가/유찬은
        '[본교]'/'[제2캠퍼스]' 또는 표기 없음으로 나타낸다. 표기 체계가
        달라 매칭이 안 되므로 괄호·대괄호 '내용까지' 제거해 base로 통합한다.
        (캠퍼스 구분은 모집단위 PK가 담당 → 합쳐도 행 단위로 구분됨)

        예: '국립공주대학교'≡'공주대학교', '명지대학교(인문)'≡'명지대학교[본교]'≡'명지대학교'
        """
        if value is None:
            return None
        s = str(value).strip()
        s = re.sub(r"^(국립|공립)", "", s)                # 국립/공립 접두
        s = re.sub(r"[\(\[][^)\]]*[\)\]]", "", s)          # (…)·[…] 내용까지 제거
        s = re.sub(r"\s", "", s)                            # 잔여 공백
        return s or None

    # ────────────────────────────────────────
    # PK 컬럼 정규화 (대학·전형·모집단위)
    # ────────────────────────────────────────
    @staticmethod
    def pk(value: Any) -> Optional[str]:
        """PK 일반: whitespace·괄호·중간점 normalize. None은 None.

        - 다중 공백 → 단일
        - 중간점(·) 주변 공백 제거: "금융 · 빅데이터" → "금융·빅데이터"
        - 괄호 안팎 공백 제거: "( 종합 )" → "(종합)"
        - 한글·중점·괄호 사이의 공백 제거: "AI 인문대학" → "AI인문대학" (heuristic)
        """
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        # 다중 공백 → 단일
        s = re.sub(r"\s+", " ", s)
        # 중간점 주변 공백 제거
        s = re.sub(r"\s*·\s*", "·", s)
        # 괄호 안팎 공백 제거
        s = re.sub(r"\(\s+", "(", s)
        s = re.sub(r"\s+\)", ")", s)
        s = re.sub(r"\s*\(\s*", "(", s)
        s = re.sub(r"\s*\)\s*", ")", s)
        # 한글-한글, 한글-괄호, 한글-숫자 사이 공백 제거 (heuristic — 영문 단어 보존)
        # 예: "AI 인문대학" → "AI인문대학" (영문+한글 사이 공백 제거)
        # 예: "기악전공 (관현악)" → "기악전공(관현악)"
        s = re.sub(r"([가-힣A-Za-z0-9])\s+([가-힣])", r"\1\2", s)
        s = re.sub(r"([가-힣])\s+([A-Za-z0-9])", r"\1\2", s)
        return s.strip()

    @classmethod
    def jeonghyeong(cls, value: Any) -> Optional[str]:
        """전형명 정규화 — 4개 출처(골든·이지현·임지현·유찬) 컨벤션 통일.

        패턴:
          - "학생부종합(X)" / "학생부교과(X)" → X (대분류 wrapper 제거)
          - " 전형" / "전형" 접미 제거
          - "(2026학년도...)" 같은 부가 annotation 제거
          - 공백·괄호 normalize
        """
        s = cls.pk(value)
        if s is None:
            return None

        # 1) 학생부종합/학생부교과 wrapper 제거 ("학생부종합(X)" → "X")
        m = re.match(r"^(?:학생부종합|학생부교과|학생부위주|수능위주|논술위주|실기/?실적위주)\((.+)\)$", s)
        if m:
            s = m.group(1).strip()

        # 2) 부가 annotation 제거 — "(2026학년도..." 같은 학년도/조건 부연
        s = re.sub(r"\s*\([^)]*년도[^)]*\)\s*$", "", s)
        s = re.sub(r"\s*\(\s*\d+\s*학년도부터[^)]*\)\s*$", "", s)

        # 3) 로마숫자 통일 (아라비아 II → 유니코드 Ⅱ; 긴 것부터, 영문단어 내부 제외)
        for ar, uni in (("VIII", "Ⅷ"), ("VII", "Ⅶ"), ("III", "Ⅲ"), ("VI", "Ⅵ"),
                        ("IV", "Ⅳ"), ("II", "Ⅱ"), ("V", "Ⅴ"), ("I", "Ⅰ")):
            s = re.sub(rf"(?<![A-Za-z]){ar}(?![A-Za-z])", uni, s)

        # 4) 중간점·구분점 제거 ("농·어촌" → "농어촌")
        s = re.sub(r"[·ㆍ•∙・]", "", s)

        # 5) 유형 표지 제거 — "전형" 모든 위치 + 정원 괄호 + 접두 유형
        #    단, (종합)/(교과)/(논술) 분류축은 보존 — '농어촌(교과)'와 '농어촌(종합)'을
        #    구분하는 유일한 단서이기 때문(지우면 PK 충돌).
        s = s.replace("전형", "")                                # "일반전형(종합)" → "일반(종합)"
        s = re.sub(r"\(\s*정원\s*[외내]\s*\)", "", s)            # (정원외)/(정원내)만 제거
        stripped = re.sub(r"^(?:학생부종합|학생부교과|학생부위주|수능위주|논술위주|실기실적위주|실기/실적위주)\s*", "", s)
        if stripped:                                             # 전부 제거되면(유형 자체가 전형명) 원복
            s = stripped

        # 6) 공백·빈괄호 정리 (내부 공백 제거 — 표기 흔들림 방지)
        s = re.sub(r"\s+", "", s)
        s = re.sub(r"\(\s*\)", "", s)

        return s or None
