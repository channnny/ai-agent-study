"""enum>사이트(스냅샷 시점차) 6개 대학 오늘자로 재열거+재크롤 → 통합 갱신.
크롤 후 전형을 삭제한 대학들(아주대·예원예술 등)을 현재 사이트 건수에 맞춤."""
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
    ("0000146", "아주대학교[본교]"), ("0000218", "예원예술대학교[본교]"),
    ("0000219", "예원예술대학교[제2캠퍼스]"), ("0000063", "가천대학교[본교]"),
    ("0000102", "동덕여자대학교[본교]"), ("0000032", "한국체육대학교[본교]"),
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
        S._log(f"{name} ✓ 성공 {nok}/{len(recs)} | 누적 {len(recs_all)}")
    S.write_combined(OUT)
    S._log(f"=== 6개 재크롤 완료 {len(recs_all)}건 / ⏱ {int(time.time()-t0)}s ===")


if __name__ == "__main__":
    main()
