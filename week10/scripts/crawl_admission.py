"""W09 — 전형정보(전형일정및방법 / 전형요소) 크롤러.

흐름:
  ① 열거(Playwright, enumerate_admissions.fetch_units): 대학 → 전형×모집단위 tuple
     (어디가 목록은 세션상태형 AJAX라 requests 불가 → 진짜 브라우저로 워밍).
  ② tuple별 detail/element 페이지를 requests GET(무세션·URL+코드) → 파싱.
  ③ 대학별 2탭 워크북(전형일정및방법/전형요소) + 통합본.

열거 결과는 output/enum/<대학>.json에 캐시. tuple별 파싱은 .progress에 캐시(이어받기).
"""
import csv
import json
import pickle
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import net  # noqa: E402
import enumerate_admissions as E  # noqa: E402
import parse_schedule as S  # noqa: E402
import parse_element as EL  # noqa: E402
import write_excel as W  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "week10" / "output"
ENUM_DIR = OUT / "enum"
PROGRESS = OUT / ".progress"
DETAIL_URL = "https://www.adiga.kr/ucp/prc/uni/admssUnivDetail.do"
ELEMENT_URL = "https://www.adiga.kr/ucp/prc/uni/admssUnivDetailElement.do"
SYR = "2027"
WORKERS = 6

# 이번 주 타깃: 가천대만. (code, 검색명, 표시명)
TARGETS = [("0000063", "가천대학교", "가천대학교[본교]")]


def _names() -> dict:
    f = ROOT / "week03" / "input" / "target_universities.csv"
    with open(f, encoding="utf-8") as fh:
        return {r["unv_cd"].strip(): r["univ_name"].strip() for r in csv.DictReader(fh)}


def _enumerate(unv_cd: str, search_name: str) -> list[dict]:
    """열거 tuple 로드(캐시) 또는 Playwright 수집."""
    cache = ENUM_DIR / f"{unv_cd}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    units = E.fetch_units(unv_cd, search_name, syr=SYR)
    ENUM_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(units, ensure_ascii=False), encoding="utf-8")
    return units


def _detail_params(u: dict) -> dict:
    return {
        "user": "", "cnrtYear": "2026", "unvSeCd": "10",
        "menuId": "PCPRCINF2000", "searchSyr": SYR,
        **{k: u[k] for k in E.PARAM_KEYS},
    }


def _crawl_tuple(u: dict, 대학명: str) -> tuple:
    """단일 (전형×모집단위) → (sched_rows, elem_rows). 캐시 이어받기."""
    key = f"{u['comScsbjtCd']}_{u['ruCd']}_{u['ruSn']}_{u['slcnTypeCd']}_{u['slcnCd']}"
    pf = PROGRESS / f"{u['unvCd']}_{key}.pkl"
    if pf.exists():
        return pickle.loads(pf.read_bytes())

    params = _detail_params(u)
    전형명 = u.get("전형명", "")
    # 전형일정 및 방법
    hs = net._request("GET", DETAIL_URL, params=params).text
    sched = S.parse(hs, 대학명=대학명, 전형명=전형명)
    # 열거 단계 학과명으로 모집단위 보강(detail selectionInfo가 비면)
    for r in sched:
        if not r.get("모집단위명"):
            r["모집단위명"] = u.get("학과명", "")
    # 전형요소 (빈 전형이면 [] — 정상)
    eparams = {k: v for k, v in params.items() if k not in ("user", "cnrtYear", "unvSeCd")}
    eparams["admssInfoTabYn"] = ""
    he = net._request("GET", ELEMENT_URL, params=eparams).text
    elem = EL.parse(he, 대학명=대학명, 전형명=전형명)

    PROGRESS.mkdir(parents=True, exist_ok=True)
    out = (sched, elem)
    pf.write_bytes(pickle.dumps(out))
    return out


def crawl_university(unv_cd: str, search_name: str, 대학명: str) -> tuple:
    units = _enumerate(unv_cd, search_name)
    print(f"  · {대학명}: 전형×모집단위 {len(units)}건 — detail/element 크롤 시작", flush=True)
    sched_all, elem_all = [], []
    done = [0]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(_crawl_tuple, u, 대학명): u for u in units}
        for fut in as_completed(futs):
            u = futs[fut]
            done[0] += 1
            try:
                sched, elem = fut.result()
                sched_all += sched
                elem_all += elem
            except Exception as e:
                print(f"    ✗ {u.get('학과명','')}/{u.get('전형명','')[:20]}: {type(e).__name__}: {e}", flush=True)
            if done[0] % 50 == 0:
                print(f"    … {done[0]}/{len(units)}", flush=True)
    return sched_all, elem_all


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    targets = TARGETS
    print(f"=== 전형정보 크롤 — 대상 {len(targets)}개 대학 (동시 {WORKERS}) ===\n")
    t0 = time.time()
    per_univ = []
    for unv_cd, search_name, 대학명 in targets:
        sched, elem = crawl_university(unv_cd, search_name, 대학명)
        W.write_university(OUT / "대학별" / f"{대학명}.xlsx", sched, elem)
        per_univ.append((대학명, sched, elem))
        print(f"  ✓ {대학명}: 전형일정 {len(sched)}행 / 전형요소 {len(elem)}행", flush=True)
    W.write_combined(OUT / "전형정보_통합.xlsx", per_univ)
    m, s = divmod(int(time.time() - t0), 60)
    print(f"\n✓ 통합본 → {OUT/'전형정보_통합.xlsx'}\n⏱ {m}분 {s}초")


if __name__ == "__main__":
    main()
