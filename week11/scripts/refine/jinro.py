"""④ 진로 A/B/C — 각주 환산표 파싱(등급/점수). 없으면 내부확인/미반영."""
import re
from cols import c, S2_진로선택, S2_각주


def refine_jinro(s2, jonghap: bool, flags: list) -> str:
    if jonghap:
        return "해당없음(종합)"
    진로 = c(s2[S2_진로선택]).replace("/", "").strip()
    if not 진로:
        return "미반영"
    각주 = c(s2[S2_각주])
    m = re.search(r"A\s*[:(]?\s*(\d+)\s*등급.*?B\s*[:(]?\s*(\d+)\s*등급.*?C\s*[:(]?\s*(\d+)\s*등급", 각주, re.S)
    if m:
        return f"A={m.group(1)},B={m.group(2)},C={m.group(3)}등급"
    m = re.search(r"A\s*[:(]?\s*(\d+)\s*점.*?B\s*[:(]?\s*(\d+)\s*점.*?C\s*[:(]?\s*(\d+)\s*점", 각주, re.S)
    if m:
        return f"A={m.group(1)},B={m.group(2)},C={m.group(3)}점"
    flags.append("진로소스없음")
    return "내부확인"
