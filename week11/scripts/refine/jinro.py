"""④ 진로 A/B/C — 각주 환산표 파싱. 등급/점 명시 + 등호형(단위없음, context 추론).
환산표 진짜 없으면 '내부확인'(사유 포함), 진로칸 공란이면 '미반영'."""
import re
from cols import c, S2_진로선택, S2_각주

# A..B..C 근접 triple(값 인접 + 항목간격 짧게). 넓은 span의 우연한 A/B/C 배제(거짓양성 방지).
# 라벨 괄호(우수) 허용. gap .{0,15}? = 진짜 성취도표는 "A:10, B:8, C:6"처럼 촘촘.
_P_등급 = re.compile(r"A\D{0,4}(\d+)\s*등급.{0,15}?B\D{0,4}(\d+)\s*등급.{0,15}?C\D{0,4}(\d+)\s*등급", re.S)
_P_점 = re.compile(r"A\D{0,4}(\d+)\s*점.{0,15}?B\D{0,4}(\d+)\s*점.{0,15}?C\D{0,4}(\d+)\s*점", re.S)
_P_등호 = re.compile(r"A(?:\([^)]*\))?\s*[=:]\s*(\d+).{0,15}?B(?:\([^)]*\))?\s*[=:]\s*(\d+)"
                     r".{0,15}?C(?:\([^)]*\))?\s*[=:]\s*(\d+)", re.S)


def _reason(각주: str) -> str:
    """내부확인 사유(왜 A/B/C를 못 뽑았나)."""
    if not 각주:
        return "각주 자체 없음(어디가 미제공)"
    if re.search(r"진로", 각주):
        return "각주에 진로 A/B/C 환산표 미노출"
    return "각주에 A/B/C 환산 정보 없음"


def refine_jinro(s2, jonghap: bool, flags: list) -> str:
    if jonghap:
        return "해당없음(종합)"
    진로 = c(s2[S2_진로선택]).replace("/", "").strip()
    if not 진로:
        return "미반영"
    각주 = c(s2[S2_각주])
    m = _P_등급.search(각주)
    if m:
        return f"A={m[1]},B={m[2]},C={m[3]}등급"
    m = _P_점.search(각주)
    if m:
        return f"A={m[1]},B={m[2]},C={m[3]}점"
    m = _P_등호.search(각주)
    if m:
        vals = [int(m[1]), int(m[2]), int(m[3])]
        pre = 각주[max(0, m.start() - 15):m.start()]
        if max(vals) > 9:                          # 등급은 1~9 → 초과면 점수
            unit = "점"
        else:
            unit = "점" if "점" in pre else "등급"  # context: '반영 점수'→점, '등급으로 변환'→등급
        return f"A={m[1]},B={m[2]},C={m[3]}{unit}"
    flags.append(f"진로내부확인:{_reason(각주)}")
    return "내부확인"
