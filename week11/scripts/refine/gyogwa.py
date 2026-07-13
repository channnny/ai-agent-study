"""③ 교과반영영역 — 반영교과 distinct → 국영수사과한 순."""
import re
from cols import c

_GYO_ORDER = [("국", ["국어"]), ("영", ["영어"]), ("수", ["수학"]),
              ("사", ["사회", "역사", "도덕"]), ("과", ["과학"]), ("한", ["한국사"])]


def refine_gyogwa(반영교과, jonghap: bool) -> str:
    if jonghap:
        return "해당없음(종합)"
    raw = c(반영교과)
    if not raw:
        return "미반영"
    parts = [p.strip() for p in re.split(r"[/,]", raw) if p.strip()]
    out = []
    for code, keys in _GYO_ORDER:
        for p in parts:
            if any(k in p for k in keys):
                # '한국사'는 '한'으로만(사회의 역사와 구분)
                if code == "사" and "한국사" in p and "사회" not in p:
                    continue
                out.append(code)
                break
    return "".join(dict.fromkeys(out)) or "미반영"
