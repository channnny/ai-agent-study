"""종합전형 판별."""
from cols import c, S2_서류학생부, S2_반영교과


def is_jonghap(전형명: str, s2) -> bool:
    """종합전형이면 True. 전형명에 '종합' 또는 서류평가요소만 있고 교과반영 없음."""
    if "종합" in (전형명 or ""):
        return True
    return bool(c(s2[S2_서류학생부])) and not c(s2[S2_반영교과])
