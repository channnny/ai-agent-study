"""3인(유찬·이지현·임지현) 크롤러 출력 → 통합 1개 데이터셋.

목표: 누락 없이 최대한 많은 데이터. 극대화 전략
  - 커버리지: 행(PK=대학·전형·모집단위) 합집합 → 한 명이라도 긁으면 포함
  - 충진율:   같은 행에서 셀별로 '값 있는 것' 채택 → 한 명이라도 값 있으면 채움
  - 일치율:   여러 명 값이 다르면 다수결(2:1), 동률이면 충진율 높은 순(임지현>이지현>유찬)

골든셋을 보지 않고 병합하므로 평가의 독립성이 유지된다(치팅 아님).
"""
from __future__ import annotations
import pandas as pd
from collections import defaultdict, Counter

from .config import PK_COLUMNS, DATA_COLUMNS, CANONICAL_COLUMNS, GROUP_LABEL_COL
from .matcher import _is_empty

# 셀 값 동률 시 우선순위 (충진율 높은 순). 키 = adapters dict의 사람 라벨.
PRIORITY = ["lim", "lee", "yuchan"]


def _pick_cell(values: list, persons: list):
    """후보 셀 값들 중 최종값 선택.

    1) None/빈 값 제외
    2) 남은 값 다수결(최빈)
    3) 동률이면 PRIORITY 순(임지현>이지현>유찬)
    """
    cands = [(p, v) for p, v in zip(persons, values) if not _is_empty(v)]
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0][1]
    # 다수결: 값을 문자열 키로 집계
    cnt = Counter(str(v) for _, v in cands)
    top = cnt.most_common()
    max_n = top[0][1]
    winners = {k for k, n in top if n == max_n}
    if len(winners) == 1:
        # 유일 최빈값 → 그 값 그대로(원본 타입 보존)
        key = top[0][0]
        for _, v in cands:
            if str(v) == key:
                return v
    # 동률 → 우선순위 높은 사람의 값
    for pr in PRIORITY:
        for p, v in cands:
            if p == pr:
                return v
    return cands[0][1]


def merge_persons(person_data: dict[str, dict[str, pd.DataFrame]]) -> dict[str, pd.DataFrame]:
    """{사람라벨: {대학: df}} → {대학: 통합 df}.

    person_data 예: {"yuchan": {...}, "lee": {...}, "lim": {...}}
    """
    persons = list(person_data.keys())
    all_univ = set()
    for d in person_data.values():
        all_univ |= set(d.keys())

    merged: dict[str, pd.DataFrame] = {}
    for univ in all_univ:
        # 이 대학에 대해 각 사람의 PK→row 인덱스
        per_person_rows: dict[str, dict[tuple, dict]] = {}
        for p in persons:
            df = person_data[p].get(univ)
            if df is None or df.empty:
                continue
            idx = df.set_index(PK_COLUMNS)
            idx = idx[~idx.index.duplicated(keep="first")]
            per_person_rows[p] = {pk: row for pk, row in idx.iterrows()}

        if not per_person_rows:
            continue

        # PK 합집합
        all_pk = set()
        for rows in per_person_rows.values():
            all_pk |= set(rows.keys())

        out_rows = []
        for pk in all_pk:
            rec = {c: None for c in CANONICAL_COLUMNS}
            rec["대학"], rec["전형"], rec["모집단위"] = pk
            # 각 데이터 컬럼: 그 PK를 가진 사람들의 값 모아 선택
            havers = [p for p in persons if p in per_person_rows and pk in per_person_rows[p]]
            for col in DATA_COLUMNS:
                vals = [per_person_rows[p][pk].get(col) for p in havers]
                rec[col] = _pick_cell(vals, havers)
            out_rows.append(rec)

        if out_rows:
            merged[univ] = pd.DataFrame(out_rows, columns=CANONICAL_COLUMNS)

    return merged
