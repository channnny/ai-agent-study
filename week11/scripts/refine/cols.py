"""RAW 컬럼 인덱스(0-based, iter_rows values_only) + 셀 정규화 헬퍼. 공유."""
import re

PLACEHOLDER = "대학에서 입력된 정보가 없습니다."

# ── 시트1 전형일정및방법(46열) ──
S1_SEL_MODEL, S1_SEL_METHOD, S1_SEL_RATE = 14, 15, 16
S1_RB = {"학생부": 17, "수능": 18, "면접": 19, "논술": 20, "적성": 21,
         "1단계성적": 22, "실기": 23, "서류": 24, "기타": 25}
S1_CHOI_영역수, S1_CHOI_세부 = 44, 45
S1_국, S1_수, S1_영, S1_탐, S1_탐과목, S1_한 = 35, 37, 39, 40, 41, 43

# ── 시트2 전형요소(55열) ──
S2_학년공통, S2_공통비율, S2_1학년, S2_2학년, S2_3학년 = 33, 34, 35, 36, 37
S2_요소 = {"교과": 38, "출결": 39, "자격": 40, "활동": 41, "봉사": 42, "기타": 43}
S2_서류학생부, S2_반영교과, S2_진로선택, S2_각주 = 44, 49, 52, 54


def c(v) -> str:
    """셀 정규화: None/placeholder/공백 → ''."""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s == PLACEHOLDER else s


def num(v) -> str:
    """첫 정수 문자열. 없으면 ''."""
    m = re.search(r"\d+", c(v))
    return m.group(0) if m else ""
