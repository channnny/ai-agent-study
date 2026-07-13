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


# ── 계열별/다조건 최저 파싱 ──
_AREA_KEYS = [("국", ["국어"]), ("수", ["수학"]), ("과", ["과학탐구", "과탐"]),
              ("사", ["사회탐구", "사탐"]), ("탐", ["탐구"])]


def _hab(block: str):
    """블록에서 (N개, 합M). '개수'는 반드시 '합' 바로 앞(등급/의 허용).
    '국어,수학 중 1개 포함하여 2개 과목 등급 합 4' → (2,4) — 앞의 '1개' 오취 방지."""
    m = re.search(r"(\d+)\s*개\s*(?:과목|영역)?\s*(?:의|등급|등급의)?\s*합\s*(?:이|의)?\s*(\d+)", block, re.S)
    return (m.group(1), m.group(2)) if m else None


def _caps(block: str) -> list:
    """영어·한국사 개별 등급 상한 → ['영3','한4']."""
    out = []
    e = re.search(r"영어\s*(\d+)\s*등급", block)
    if e:
        out.append(f"영{e.group(1)}")
    h = re.search(r"한국사\s*(\d+)\s*등급", block)
    if h:
        out.append(f"한{h.group(1)}")
    return out


def _areas(head: str) -> tuple:
    """조건1 앞부분에서 반영영역 + 필수 추출."""
    areas = []
    for code, keys in _AREA_KEYS:
        if any(k in head for k in keys):
            areas.append(code)
    # '탐구'가 사/과탐과 함께면 중복 → 사/과 우선
    if ("사" in areas or "과" in areas) and "탐" in areas:
        areas.remove("탐")
    필수 = []
    if re.search(r"수학.{0,8}포함", head):
        필수.append("수")
    return areas, 필수


def _parse_block(block: str) -> str:
    """단일 조건셋 블록 → '국,수,과 중 2개 등급합 5 (수 포함) 영3 한4' or None."""
    hab = _hab(block)
    if not hab:
        return None
    N, M = hab
    head = block[:block.find("합")]
    areas, 필수 = _areas(head)
    if not areas:
        return None
    body = ",".join(areas) + f" 중 {N}개 등급합 {M}"
    if 필수:
        body += f" ({','.join(필수)} 포함)"
    caps = _caps(block)
    if caps:
        body += " " + " ".join(caps)
    return body


def _parse_multi(txt: str):
    """계열별/다조건 → (①, ②) or None. 이중계열은 '인문…/자연…'."""
    # 이중 계열 — 계열별 블록 중 '합'을 가진 유효 블록만 취함(preamble '~기준 또는~' 무시)
    duo = re.findall(r"(인문|자연)\s*계열(.*?)(?=(?:인문|자연)\s*계열|$)", txt, re.S)
    by = {}
    for name, blk in duo:
        if name not in by and _hab(blk):
            by[name] = blk
    if len(by) >= 2:
        parts1 = [f"{n} {_hab(b)[0]}합{_hab(b)[1]}" for n, b in by.items()]
        parts2 = [f"[{n}] {_parse_block(b)}" for n, b in by.items()]
        if all("None" not in p for p in parts2) and all(_parse_block(b) for b in by.values()):
            return " / ".join(parts1), " / ".join(parts2)
        return None
    # 단일 조건셋
    y = _parse_block(txt)
    hab = _hab(txt)
    if y and hab:
        return f"{hab[0]}합{hab[1]}", y
    return None


def refine_choi(s1, flags: list) -> tuple:
    세부 = c(s1[S1_CHOI_세부])
    영역수 = num(s1[S1_CHOI_영역수])
    if not 세부 and not 영역수:
        return "최저 없음", "최저 없음"
    txt = 세부.replace("!", "")
    복잡 = bool(re.search(r"(인문|자연|예체능|국제)\s*계열", txt)) or \
        len(re.findall(r"(?:^|[\s\n])\d+\.\s", txt)) >= 2
    if 복잡:
        multi = _parse_multi(txt)
        if multi:
            return multi
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
