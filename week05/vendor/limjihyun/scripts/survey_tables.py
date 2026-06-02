"""여러 대학 크롤링 후 입결 후보 표 구조를 덤프해 예외 케이스 파악."""
import json
from agent.crawler import crawl

SAMPLES = {
    "0000052": "건국대학교",
    "0000056": "경기대학교",
    "0000100": "동국대학교",
    "0000063": "가천대학교",
    "0000151": "영남대학교",
    "0000102": "동덕여자대학교",
    "0000072": "가톨릭관동대학교",
}

KW = ["모집인원", "경쟁률", "충원합격순위", "학생부등급", "최종등록자", "환산", "백분위", "수능"]

for code, name in SAMPLES.items():
    try:
        raw = crawl(code, univ_name_hint=name)
    except Exception as e:
        print(f"\n### {name} ({code}) — CRAWL FAILED: {e}")
        continue
    cands = []
    for t in raw["tables"]:
        blob = " ".join(str(h) for h in t["flat_headers"])
        score = sum(1 for k in KW if k in blob)
        if score >= 2 and t["data_row_count"] >= 3:
            cands.append(t)
    print(f"\n### {raw['univName']} ({code}) — 표 {raw['table_count']}개, 입결후보 {len(cands)}개")
    for t in cands:
        print(f"  [T{t['idx']}] thead={t.get('thead_label','')!r} rows={t['data_row_count']}")
        print(f"       headers: {t['flat_headers']}")
        if t['data_rows']:
            print(f"       data[0]: {t['data_rows'][0]}")
