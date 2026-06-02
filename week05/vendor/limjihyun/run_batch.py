"""여러 대학 배치 실행 + 정답본 대조 리포트."""
import sys
import openpyxl
from collections import Counter, defaultdict
from agent.crawler import crawl
from agent.mapper import map_raw
from agent.validator import validate
from agent.writer import write

SAMPLES = {
    "0000052": "건국대학교", "0000056": "경기대학교", "0000100": "동국대학교",
    "0000063": "가천대학교", "0000151": "영남대학교", "0000102": "동덕여자대학교",
    "0000072": "가톨릭관동대학교", "0000069": "고려대학교",
}
ANSWER = "/Users/vibeon/Downloads/2025_어디가입결_통합본 (1).xlsx"
# 정답본 대학명(통합본 A컬럼) — 어디가 univName과 매칭
ANSWER_NAME = {
    "0000052": "건국대학교", "0000056": "경기대학교", "0000100": "동국대학교",
    "0000063": "가천대학교", "0000151": "영남대학교", "0000102": "동덕여자대학교",
    "0000072": "가톨릭관동대학교", "0000069": "고려대학교",
}


def run_one(code):
    crawl(code, univ_name_hint=SAMPLES.get(code))
    m = map_raw(code)
    v = validate(code)
    out = write(code)
    return m, v, out


def norm(x):
    if x is None or x == "":
        return None
    try:
        return round(float(str(x).replace(",", "")), 2)
    except (ValueError, TypeError):
        return str(x).strip()


def load_answer():
    wb = openpyxl.load_workbook(ANSWER, read_only=True, data_only=True)
    ws = wb["수시"]
    by_univ = defaultdict(dict)
    for row in ws.iter_rows(min_row=3, values_only=True):
        u = row[0]
        if not u:
            continue
        key = (str(row[2]).strip(), norm(row[10]), norm(row[11]))  # 모집단위,모집인원,경쟁률
        by_univ[u][key] = {
            "충원": norm(row[12]), "환산총점": norm(row[19]),
            "등급50": norm(row[22]), "등급70": norm(row[23]),
            "등급90": norm(row[25]), "등급평균": norm(row[21]),
        }
    return by_univ


def compare(code, answer_by_univ):
    aname = ANSWER_NAME[code]
    ans = answer_by_univ.get(aname, {})
    wb = openpyxl.load_workbook(f"outputs/{code}.xlsx", data_only=True)
    ws = wb["수시"]
    mine = []
    for r in range(3, ws.max_row + 1):
        if not ws.cell(row=r, column=1).value:
            continue
        mine.append({
            "모집단위": str(ws.cell(row=r, column=3).value).strip(),
            "모집인원": norm(ws.cell(row=r, column=4).value),
            "경쟁률": norm(ws.cell(row=r, column=5).value),
            "충원": norm(ws.cell(row=r, column=6).value),
            "환산총점": norm(ws.cell(row=r, column=13).value),
            "등급50": norm(ws.cell(row=r, column=16).value),
            "등급70": norm(ws.cell(row=r, column=17).value),
            "등급90": norm(ws.cell(row=r, column=19).value),
            "등급평균": norm(ws.cell(row=r, column=15).value),
        })
    matched = 0
    fields = defaultdict(lambda: [0, 0])
    for m in mine:
        key = (m["모집단위"], m["모집인원"], m["경쟁률"])
        if key in ans:
            matched += 1
            a = ans[key]
            for f in ("충원", "환산총점", "등급50", "등급70", "등급90", "등급평균"):
                if m[f] is not None or a[f] is not None:
                    fields[f][1] += 1
                    if m[f] == a[f]:
                        fields[f][0] += 1
    return {
        "ans_rows": len(ans), "mine_rows": len(mine), "matched": matched,
        "fields": {f: (ok, tot) for f, (ok, tot) in fields.items()},
    }


if __name__ == "__main__":
    codes = sys.argv[1:] or list(SAMPLES.keys())
    answer = load_answer()
    print("=" * 70)
    for code in codes:
        try:
            m, v, _ = run_one(code)
        except Exception as e:
            print(f"\n[{code} {SAMPLES.get(code)}] 실행 실패: {type(e).__name__}: {e}")
            continue
        cmp = compare(code, answer)
        nm = m.get("univName", "")
        types = Counter(r["admission_name"] for r in m["records"])
        print(f"\n### {nm} ({code})")
        print(f"  records={len(m['records'])}, verdict={v['verdict']}, 정답행={cmp['ans_rows']}, 매칭={cmp['matched']}/{cmp['mine_rows']}")
        print(f"  전형: {dict(types)}")
        fstr = " ".join(f"{f}={ok}/{tot}" for f, (ok, tot) in cmp["fields"].items())
        print(f"  필드일치: {fstr}")
    print("\n" + "=" * 70)
