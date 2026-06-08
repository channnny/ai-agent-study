"""W06 정규화 보강.

W05의 Normalizer를 그대로 상속하되, W05 리포트에서 확인된 표기 차이 중
의미가 명확한 alias만 보수적으로 추가한다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from week05.src.normalizer import Normalizer as W05Normalizer  # noqa: E402


class W06Normalizer(W05Normalizer):
    """W05 Normalizer + 안전한 W06 alias."""

    JEONGHYEONG_ALIASES = {
        "추천형": "추천형",
        "교과일반": "일반",
        "일반교과": "일반",
        "정원내일반": "일반",
        "일반정원내": "일반",
        "일반학생정원내": "일반학생",
        "농어촌": "농어촌학생",
        "농어촌학생정원외": "농어촌학생",
        "특성화교고": "특성화고교",
        "기회균형특별": "기회균형",
        "계열적합인재": "계열적합인재",
        "기초생활수급자차상위계층한부모가족": "기초생활수급자차상위계층한부모가족",
        "기초생활수급자차상위계층한부모가족지원대상자": "기초생활수급자차상위계층한부모가족",
        "기초생활수급권자및차상위계층자": "기초생활수급자차상위계층",
        "특성화고졸재직자": "특성화고교졸재직자",
        "특성화고교졸재직자정원외": "특성화고교졸재직자",
    }

    CATEGORY_PREFIXES = (
        "학생부종합",
        "학생부교과",
        "학생부위주",
        "수능위주",
        "논술위주",
        "실기실적위주",
        "실기/실적위주",
    )

    @classmethod
    def jeonghyeong(cls, value: Any) -> Optional[str]:
        s = super().jeonghyeong(value)
        if s is None:
            return None

        # 탭명만 남은 값은 실제 전형명으로 보기 어렵다. W05 후보 파일에서도
        # 빈도는 높지만 의미가 손실된 케이스라 자동 alias에서 제외한다.
        if re.fullmatch(r"[ⅠⅡⅢⅣⅤⅥⅦⅧ]\.?학생부(?:종합|교과)", s):
            return s

        # "(학생부교과)일반", "(학생부종합)지역인재"처럼 앞쪽 괄호에
        # 대분류만 들어간 표기는 실제 전형명만 남긴다.
        for prefix in cls.CATEGORY_PREFIXES:
            s = re.sub(rf"^\({re.escape(prefix)}\)", "", s)
            s = re.sub(rf"{re.escape(prefix)}\(([^)]+)\)", r"\1", s)

        # "학교장추천(학생부교과)"처럼 뒤쪽 괄호에 대분류만 붙은 경우 제거.
        for prefix in cls.CATEGORY_PREFIXES:
            s = s.replace(f"({prefix})", "")

        # 후보 CSV에 있던 malformed 정원외 표기와 구분자 흔들림 흡수.
        s = s.replace(")(", "")
        s = re.sub(r"[\s/_·ㆍ•∙・,-]+", "", s)
        s = s.replace("전형", "")
        s = re.sub(r"정원[외내]$", "", s)
        s = re.sub(r"^정원[외내]", "", s)
        s = s.strip("()")

        return cls.JEONGHYEONG_ALIASES.get(s, s) or None

    def reflected_subjects(self, value: Any) -> Optional[str]:
        c = self.cell(value)
        if c is None:
            return None
        raw = str(c)
        compact = re.sub(r"[\s,()·ㆍ•∙・/_:+-]+", "", raw)

        # 어디가 안내문이 반영교과 칸으로 밀려 들어온 명백한 매핑 오류.
        bad_markers = (
            "선발인원",
            "모집단위전형별공개",
            "최종등록자없음",
            "등록자없음",
            "전형결과산출방법",
        )
        if any(marker in compact for marker in bad_markers):
            return None

        if "전과목" in compact or "전교과" in compact or "전체교과" in compact:
            return "전교과"

        s = raw
        replacements = {
            "국어": "국",
            "수학": "수",
            "영어": "영",
            "외국어": "영",
            "사회": "사",
            "도덕": "사",
            "역사": "사",
            "과학": "과",
            "한국사": "한",
        }
        for old, new in replacements.items():
            s = s.replace(old, new)

        token = re.sub(r"[\s,()·ㆍ•∙・/_:+-]+", "", s)
        token = token.replace("교과", "").replace("과목", "")
        token = token.replace("공통", "").replace("반영", "")

        # 단순 과목 나열은 순서 차이를 제거한다.
        if token and re.fullmatch(r"[국수영사과한]+", token):
            order = "국수영사과한"
            present = {ch for ch in token}
            return "".join(ch for ch in order if ch in present)

        return super().reflected_subjects(value)


Normalizer = W06Normalizer
