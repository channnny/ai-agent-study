"""열거0였던 9개 대학(서울대 + 분교/캠퍼스) 재열거+재크롤 → 통합 갱신.

원인: 이름검색이 autocomplete로 본교/동명 오해석 → 필터 0.
수정(enumerate_admissions): 검색버튼 클릭 + csv코드 필터 + 시그니처 종단.
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import structured as S       # noqa: E402
import enumerate_admissions as E  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "week10" / "output"
NINE = [
    ("0000019", "서울대학교[본교]"), ("0000049", "가톨릭대학교[제3캠퍼스]"),
    ("0000053", "건국대학교(글로컬)[분교]"), ("0000070", "고려대학교(세종)[분교]"),
    ("0000101", "동국대학교(WISE)[분교]"), ("0000150", "연세대학교(미래)[분교]"),
    ("0000174", "중앙대학교[제2캠퍼스]"), ("0000204", "한양대학교(ERICA)[분교]"),
    ("0003298", "국립창원대학교[제3캠퍼스]"),
]


def main():
    recs_all, t0 = [], time.time()
    for code, name in NINE:
        cache = OUT / "enum" / f"{code}.json"
        if cache.exists():
            cache.unlink()                       # 오염(0건) 캐시 삭제
        search = re.split(r"[\[\(]", name)[0].strip()
        S._log(f"{name} 재열거(검색='{search}')…")
        units = E.fetch_units(code, search, syr=S.SYR, retries=2)
        cache.write_text(json.dumps(units, ensure_ascii=False), encoding="utf-8")
        if not units:
            S._log(f"{name} ✗ 여전히 0건 — 확인 필요")
            continue
        S._log(f"{name} → {len(units)}유닛, detail 크롤…")
        recs = S.crawl_university(units, name)
        S.write_structured(recs, OUT / "대학별" / f"{name}.xlsx")
        recs_all += recs
        nok = sum(r["status"] == "ok" for r in recs)
        el = int(time.time() - t0)
        S._log(f"{name} ✓ 성공 {nok}/{len(recs)} | 누적 {len(recs_all)} | {el//60}m{el%60}s")
    S.write_combined(OUT)
    S._log(f"=== 9개 복구 완료 {len(recs_all)}건 / ⏱ {int(time.time()-t0)}s ===")


if __name__ == "__main__":
    main()
