"""①② 수능최저 — 구조화 컬럼(영역수+국수영탐 반영여부)이 신뢰 소스.
계열별 다조건은 검증필요 플래그."""
import re
from cols import (c, num, S1_CHOI_영역수, S1_CHOI_세부,
                  S1_국, S1_수, S1_영, S1_탐, S1_탐과목, S1_한)

_TAM_과 = ["물리", "화학", "생명", "지구과학", "과학"]
_TAM_사 = ["지리", "역사", "윤리", "사회", "경제", "정치", "세계", "수산", "해운", "농업", "공업", "상업", "가사"]


def _tamgu_label(과목: str) -> str:
    사 = any(k in 과목 for k in _TAM_사)
    과 = any(k in 과목 for k in _TAM_과)
    if 과 and not 사:
        return "과"
    if 사 and not 과:
        return "사"
    return "탐"


def _build_yeongyeok(s1, N: str, K: str) -> str:
    """구조화 컬럼 → '국,수,영,탐(1) 중 N개 등급합 K' (+ 필수 포함 / 한N)."""
    areas, 필수 = [], []
    for label, idx in [("국", S1_국), ("수", S1_수), ("영", S1_영)]:
        v = c(s1[idx])
        if v:
            areas.append(label)
            if "필수" in v:
                필수.append(label)
    탐과목 = c(s1[S1_탐과목])
    if c(s1[S1_탐]) or 탐과목:
        areas.append(f"{_tamgu_label(탐과목)}(1)")
        if "필수" in c(s1[S1_탐]):
            필수.append("탐")
    body = ",".join(areas) + f" 중 {N}개 등급합 {K}"
    # '선택 중 일부 필수'일 때만 의미(전 영역 필수/무필수면 생략)
    if 필수 and len(필수) < len(areas):
        body += f" ({','.join(필수)} 포함)"
    han = c(s1[S1_한])
    if han and "필수" not in han:            # 등급컷 표기 → 한N (응시필수 제외)
        hm = re.search(r"\d+", han)
        if hm:
            body += f" 한{hm.group(0)}"
    return body


def refine_choi(s1, flags: list) -> tuple:
    세부 = c(s1[S1_CHOI_세부])
    영역수 = num(s1[S1_CHOI_영역수])
    if not 세부 and not 영역수:
        return "최저 없음", "최저 없음"
    txt = 세부.replace("!", "")
    # 계열별(인문/자연/…) 또는 다중 조건(1. 2. …) → 본질적 검증필요
    복잡 = bool(re.search(r"(인문|자연|예체능|국제)\s*계열", txt)) or \
        len(re.findall(r"(?:^|[\s\n])\d+\.\s", txt)) >= 2
    if 복잡:
        flags.append("최저계열별")
        tag = f"검증필요:계열별 [{txt[:30]}]"
        return tag, tag
    # 단순 단일조건: N=영역수, K=합/등급 숫자
    mK = (re.search(r"등급\s*합\s*(\d+)", txt) or re.search(r"합\s*(?:이|의)?\s*(\d+)", txt)
          or re.search(r"(\d+)\s*등급\s*(?:이내|이하)", txt))
    if 영역수 and mK:
        return f"{영역수}합{mK.group(1)}", _build_yeongyeok(s1, 영역수, mK.group(1))
    flags.append("최저파싱")
    tag = f"검증필요:최저 [{txt[:30]}]"
    return tag, tag
