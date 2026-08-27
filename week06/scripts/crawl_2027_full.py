"""W06 — 어디가 전체(220개) searchSyr=2027(2026학년도 입결) 크롤.

crawl_adiga.py(AJAX 패치본)의 batch 로직을 재사용하되, 산출은 W06 전용 폴더로
보내 기존 week03/output(2025학년도)을 보존한다.

실행:
    cd week06 && ../week05/.venv/bin/python scripts/crawl_2027_full.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEEK03 = ROOT / "week03"
sys.path.insert(0, str(WEEK03))

import crawl_adiga as C  # noqa: E402

# 산출 경로를 W06 전용으로 교체 (week03/output 보존)
C.OUTPUT_DIR = ROOT / "week06" / "output" / "crawl_2027_full"
C.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    targets = C.load_targets(C.INPUT_FILE)  # csv는 이미 search_syr=2027
    syrs = {syr for _, syr in targets}
    batches = [targets[i:i + C.BATCH_SIZE] for i in range(0, len(targets), C.BATCH_SIZE)]
    print(f"입력: {C.INPUT_FILE.name} ({len(targets)}건), searchSyr={sorted(syrs)}")
    print(f"출력: {C.OUTPUT_DIR}")
    print(f"배치: {len(batches)}개 × {C.BATCH_SIZE}건, 동시 {C.MAX_WORKERS}\n")

    t0 = time.perf_counter()
    ok, fail = [], []
    n_rows = 0
    for i, batch in enumerate(batches, 1):
        s, f = C.run_batch(batch, i, len(batches))
        ok.extend(s)
        fail.extend(f)
        for r in s:
            n_rows += sum(x["rows"] for x in r["saved"])
        if i < len(batches):
            time.sleep(C.BATCH_DELAY)

    el = time.perf_counter() - t0
    n_with_data = sum(1 for r in ok if r["saved"])
    print("\n" + "=" * 56)
    print(f"총 소요   : {el:.0f}s")
    print(f"성공      : {len(ok)}건 (전형결과 있음 {n_with_data}건, 총 {n_rows:,}행)")
    print(f"실패      : {len(fail)}건" + (f" → {fail}" if fail else ""))
    print(f"출력      : {C.OUTPUT_DIR}")
    print("=" * 56)


if __name__ == "__main__":
    main()
