"""과소열거 11개 대학(사이트건수 vs enum 대조로 특정) 재열거+재크롤 → 통합 갱신.
recover_campuses.py와 동일 로직, 대상만 다름."""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import structured as S       # noqa: E402
import enumerate_admissions as E  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "week10" / "output"
TARGETS = [
    ("0003363", "강원대학교[제3캠퍼스]"), ("0000082", "단국대학교[본교]"),
    ("0000004", "강원대학교[제2캠퍼스]"), ("0003364", "강원대학교[제4캠퍼스]"),
    ("0000024", "전남대학교[제2캠퍼스]"), ("0000058", "경기대학교[제2캠퍼스]"),
    ("0000056", "경기대학교[본교]"), ("0003297", "국립창원대학교[제2캠퍼스]"),
    ("0000148", "안양대학교[제2캠퍼스]"), ("0000048", "가톨릭대학교[제2캠퍼스]"),
    ("0000025", "전북대학교[본교]"),
]


def main():
    recs_all, t0 = [], time.time()
    for code, name in TARGETS:
        cache = OUT / "enum" / f"{code}.json"
        old = len(json.loads(cache.read_text(encoding="utf-8"))) if cache.exists() else 0
        if cache.exists():
            cache.unlink()
        search = re.split(r"[\[\(]", name)[0].strip()
        units = E.fetch_units(code, search, syr=S.SYR, retries=2)
        cache.write_text(json.dumps(units, ensure_ascii=False), encoding="utf-8")
        S._log(f"{name} 재열거 {old}→{len(units)}유닛, 크롤…")
        if not units:
            continue
        recs = S.crawl_university(units, name)
        S.write_structured(recs, OUT / "대학별" / f"{name}.xlsx")
        recs_all += recs
        nok = sum(r["status"] == "ok" for r in recs)
        el = int(time.time() - t0)
        S._log(f"{name} ✓ 성공 {nok}/{len(recs)} | 누적 {len(recs_all)} | {el//60}m{el%60}s")
    S.write_combined(OUT)
    S._log(f"=== 11개 재복구 완료 {len(recs_all)}건 / ⏱ {int(time.time()-t0)}s ===")


if __name__ == "__main__":
    main()
