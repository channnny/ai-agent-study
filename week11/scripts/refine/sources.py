"""[원본] 직렬화 컬럼 생성 (RAW → 사람이 추적 가능한 원본 문자열)."""
from cols import (c, S1_CHOI_세부, S1_SEL_MODEL, S1_SEL_RATE, S1_RB,
                  S2_진로선택, S2_각주, S2_학년공통, S2_공통비율, S2_요소)


def raw_choi(s1) -> str:
    return c(s1[S1_CHOI_세부])


def raw_jinro(s2) -> str:
    return f"진로선택: {c(s2[S2_진로선택])} / 반영방법각주: {c(s2[S2_각주])}".strip()


def raw_ratio(s1, s2) -> str:
    rb = " ".join(f"{k}={c(s1[i])}" for k, i in S1_RB.items() if c(s1[i]))
    yr = f"학년공통={c(s2[S2_학년공통])} 공통비율={c(s2[S2_공통비율])}"
    el = " ".join(f"{k}={c(s2[i])}" for k, i in S2_요소.items() if c(s2[i]))
    return f"선발모형={c(s1[S1_SEL_MODEL])} 선발비율={c(s1[S1_SEL_RATE])} | 반영비율: {rb} || 학년/요소: {yr} {el}"
