"""최저 세부내용 공란(골든셋엔 값 존재) 대학 재크롤.
대상: 강원대[본교]·경상국립대[본교]·전남대[본교] — 2026-08-25 재수집."""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import structured as S            # noqa: E402
import enumerate_admissions as E  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "output"
TARGETS = [
    ("0000003", "강원대학교[본교]"),
    ("0000007", "경상국립대학교[본교]"),
    ("0000023", "전남대학교[본교]"),
]


def main():
    t0, total = time.time(), 0
    for code, name in TARGETS:
        cache = OUT / "enum" / f"{code}.json"
        old = len(json.loads(cache.read_text(encoding="utf-8"))) if cache.exists() else 0
        if cache.exists():
            cache.unlink()
        units = E.fetch_units(code, re.split(r"[\[\(]", name)[0].strip(), syr=S.SYR, retries=2)
        cache.write_text(json.dumps(units, ensure_ascii=False), encoding="utf-8")
        S._log(f"{name} 재열거 {old}→{len(units)}유닛, 크롤…")
        if not units:
            continue
        recs = S.crawl_university(units, name)
        S.write_structured(recs, OUT / "대학별" / f"{name}.xlsx")
        nok = sum(r["status"] == "ok" for r in recs)
        total += nok
        S._log(f"{name} ✓ 성공 {nok}/{len(recs)}")
    S.write_combined(OUT)
    S._log(f"=== 3개 재크롤 완료 성공 {total}건 / ⏱ {int(time.time()-t0)}s ===")


if __name__ == "__main__":
    main()
