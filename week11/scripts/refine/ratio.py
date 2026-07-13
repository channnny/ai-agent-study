"""5a 전형요소별비율 / 5b 학년별·요소별비율."""
from cols import (c, num, S1_SEL_MODEL, S1_SEL_RATE, S1_RB,
                  S2_요소, S2_학년공통, S2_공통비율, S2_1학년, S2_2학년, S2_3학년)


def _decompose_hakbu(hakbu_val: str, s2, flags: list) -> list:
    """교과전형 학생부 → 요소별(교과/출결/…) 분해. 학생부=100이면 요소 그대로."""
    elems = [(lbl, num(s2[idx])) for lbl, idx in S2_요소.items() if num(s2[idx])]
    if not elems:
        return [f"교과{hakbu_val}"]
    if hakbu_val == "100":
        return [f"{lbl}{v}" for lbl, v in elems]
    if len(elems) > 1:
        flags.append("5a학생부분해")
    return [f"교과{hakbu_val}"]


def _ratio_components(cells: dict, s2, jonghap: bool, flags: list) -> str:
    comps = []
    for name, val in cells.items():
        v = num(val)
        if not v:
            continue
        if name == "학생부":
            comps.append(f"서류{v}") if jonghap else comps.extend(_decompose_hakbu(v, s2, flags))
        elif name == "1단계성적":
            comps.append(f"1단계{v}")
        else:
            comps.append(f"{name}{v}")
    return "+".join(comps)


def refine_5a(s1, s2, jonghap: bool, flags: list) -> str:
    model = c(s1[S1_SEL_MODEL])
    if not model:
        return "해당없음(종합)" if jonghap else "미반영"
    if "단계" not in model:
        cells = {k: s1[i] for k, i in S1_RB.items()}
        body = _ratio_components(cells, s2, jonghap, flags)
        return f"[일괄]{body}" if body else "검증필요:5a빈값"
    # 단계별: 각 반영비율 컬럼을 ' / '로 분할
    rates = c(s1[S1_SEL_RATE]).split("/")
    n_stage = max(len([x for x in rates if x.strip()]), 2)
    stage_cells = {k: c(s1[i]).split("/") for k, i in S1_RB.items()}
    out = []
    for st in range(n_stage):
        cells = {k: (vals[st] if st < len(vals) else "") for k, vals in stage_cells.items()}
        body = _ratio_components(cells, s2, jonghap, flags)
        if st == 0:
            mult = num(rates[0]) if rates else ""
            baesu = str(int(int(mult) / 100)) if mult and int(mult) % 100 == 0 else ""
            head = f"[1단계({baesu}배수)]" if baesu else "[1단계]"
        else:
            head = f"[{st+1}단계]"
        out.append(head + (body or "검증필요"))
    if any("검증필요" in o for o in out):
        flags.append("5a단계별")
    return ";".join(out)


def refine_5b(s2, jonghap: bool, flags: list) -> str:
    if jonghap:
        return "해당없음(종합)"
    공통 = num(s2[S2_공통비율])
    if c(s2[S2_학년공통]) or 공통:
        year = f"전학년공통{공통 or '100'}"
    else:
        ys = [(y, num(s2[i])) for y, i in [("1학년", S2_1학년), ("2학년", S2_2학년), ("3학년", S2_3학년)] if num(s2[i])]
        year = "·".join(f"{y}{v}" for y, v in ys)
    elems = [(lbl, num(s2[idx])) for lbl, idx in S2_요소.items() if num(s2[idx])]
    if not year and not elems:
        return "미반영"
    esum = sum(int(v) for _, v in elems)
    if elems and esum != 100:
        flags.append(f"5b합{esum}")
    elem_s = "+".join(f"{lbl}{v}" for lbl, v in elems)
    return f"[학년]{year} [요소]{elem_s}".strip()
