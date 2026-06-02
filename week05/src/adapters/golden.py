"""골든셋(`2025_수시_입시결과_통합본.xlsx`) → 캐노니컬 DataFrame.

구조: Sheet1, 1 헤더 행, 47컬럼. 데이터는 R2부터.

PK 매핑:
  - 대학   ← 대학명         (col 3)
  - 전형   ← 전형명         (col 8)
  - 모집단위 ← 모집단위     (col 6)

DATA 매핑:
  - 모집인원         ← 모집인원        (col 7)
  - 경쟁률           ← 경쟁률          (col 19)
  - 충원합격순위     ← 예비번호(충원인원) (col 18)
  - 학생부등급_평균   ← 내신 입결_평균   (col 24)
  - 학생부등급_50컷   ← 내신 입결_50컷   (col 25)
  - 학생부등급_70컷   ← 내신 입결_70컷   (col 26)
  - 대학별환산_총점   ← (없음 — 골든셋에 총점 컬럼 부재) → None
  - 반영교과          ← 내신 입결_교과등급 산출방법_정제 (col 34)

# adapted from leejihyun/evaluate.py + 골든셋 헤더 실측
"""
from __future__ import annotations
import pandas as pd
import openpyxl
from pathlib import Path
from collections import defaultdict

from ..config import PK_COLUMNS, DATA_COLUMNS, CANONICAL_COLUMNS
from ..normalizer import Normalizer


# 골든셋 컬럼 인덱스 → 캐노니컬 컬럼명
GOLDEN_COL_MAP = {
    3: "대학",
    8: "전형",
    6: "모집단위",
    7: "모집인원",
    19: "경쟁률",
    18: "충원합격순위",
    24: "학생부등급_평균",
    25: "학생부등급_50컷",
    26: "학생부등급_70컷",
    # 36 (교과환산점수_교과_최고)~41 — MVP에선 미사용 (총점 컬럼 부재)
    34: "반영교과",
}


def load(golden_path: Path, normalizer: Normalizer) -> dict[str, pd.DataFrame]:
    """골든셋 → {대학명: DataFrame}."""
    wb = openpyxl.load_workbook(golden_path, read_only=True, data_only=True)
    ws = wb.active

    # 대학별 행 수집
    by_univ: dict[str, list[dict]] = defaultdict(list)
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or all(c is None for c in row):
            continue
        univ_name = row[3]
        if not univ_name:
            continue
        univ_name = str(univ_name).strip()

        rec: dict = {}
        for idx, canonical_col in GOLDEN_COL_MAP.items():
            if idx >= len(row):
                continue
            v = row[idx]
            if canonical_col == "전형":
                rec[canonical_col] = normalizer.jeonghyeong(v)
            elif canonical_col in PK_COLUMNS:
                rec[canonical_col] = normalizer.pk(v)
            elif canonical_col == "모집인원":
                rec[canonical_col] = normalizer.integer(v)
            elif canonical_col == "경쟁률":
                rec[canonical_col] = normalizer.number(v)
            elif canonical_col == "충원합격순위":
                # int 변환 시도, 실패 시 str 보존 (예: "0", "ALL")
                n = normalizer.integer(v)
                rec[canonical_col] = n if n is not None else (normalizer.cell(v) or None)
            elif canonical_col.startswith("학생부등급_"):
                rec[canonical_col] = normalizer.number(v)
            elif canonical_col == "반영교과":
                rec[canonical_col] = normalizer.reflected_subjects(v)
            else:
                rec[canonical_col] = normalizer.cell(v)

        # 대학별환산_총점은 골든셋에 없음 — None
        rec.setdefault("대학별환산_총점", None)

        # PK 결측 행은 제외
        if not all(rec.get(k) for k in PK_COLUMNS):
            continue

        by_univ[univ_name].append(rec)

    # DataFrame 변환
    return {
        univ: pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
        for univ, rows in by_univ.items()
        if rows
    }
