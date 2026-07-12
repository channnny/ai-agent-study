"""7개 테스트 대학 재크롤(캐시 enum 사용) → test_피드백/ 산출물 재생성.

검증 수정(빈파일 헤더 템플릿 + 리포트 검증 시트) 반영 확인용.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import structured as S

ROOT = Path(__file__).resolve().parents[2]
ENUM = ROOT / "week10" / "output" / "enum"
OUT = ROOT / "week10" / "output" / "test_피드백"

SEVEN = [
    ("0002748", "가야대학교[본교]"),
    ("0000060", "경동대학교[본교]"),
    ("0000075", "광주가톨릭대학교[본교]"),
    ("0000224", "금강대학교[본교]"),
    ("0000141", "숙명여자대학교[본교]"),
    ("0000149", "연세대학교[본교]"),
    ("0000172", "조선대학교[본교]"),
]


def main():
    all_records, problem, t0 = [], [], time.time()
    for code, name in SEVEN:
        cache = ENUM / f"{code}.json"
        units = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else []
        S._log(f"{name} — enum {len(units)}건")
        if not units:
            problem.append({"unvCd": code, "대학명": name, "kind": "열거0",
                            "detail": "enum 캐시 0건 — 확인 필요"})
            continue
        recs = S.crawl_university(units, name)
        S.write_structured(recs, OUT / "대학별" / f"{name}.xlsx")
        all_records += recs
        nok = sum(r["status"] == "ok" for r in recs)
        S._log(f"{name} ✓ 성공 {nok}/{len(recs)}"
               + ("  ⚠ 0행" if nok == 0 else ""))
    S.write_report(all_records, OUT / "크롤링_리포트.xlsx", time.time() - t0, problem)
    S.write_combined(OUT)
    S._log(f"=== 7개 완료 {len(all_records)}건 / ⏱ {int(time.time()-t0)}s ===")


if __name__ == "__main__":
    main()
