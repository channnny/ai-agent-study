"""이지현 산출물(`adiga_2027.xlsx`) → 캐노니컬 DataFrame.

구조: 4시트 워크북. 우리는 `수시 입시결과` 시트만 사용.
헤더: R2가 컬럼명. 데이터는 R3+.
컬럼은 schema_v3.yaml susi_result 정의를 따름 (29컬럼).

매핑: 컬럼명이 캐노니컬과 동일하거나 비슷한 것을 찾아 매핑.

# adapted from leejihyun/output/adiga_2027.xlsx 실측 + schema_v3.yaml
"""
from __future__ import annotations
import pandas as pd
import openpyxl
from pathlib import Path
from collections import defaultdict

from ..config import PK_COLUMNS, DATA_COLUMNS, CANONICAL_COLUMNS
from ..normalizer import Normalizer


SHEET_NAME = "수시 입시결과"

# 이지현 R2 헤더 → 캐노니컬 컬럼명
# (없으면 컬럼명 그대로 매칭 시도)
LEE_HEADER_ALIAS = {
    # 그룹 헤더 결합 (R1 group + R2 detail) — 이지현은 R2만 가짐
    # 학생부등급 그룹: '최고', '평균', '50컷', '70컷', '80컷', '90컷', '최저'
    # 대학별환산 그룹: '최고', '평균', '50컷', '70컷', '80컷', '100컷', '총점'
    # 그룹 단순 결합 시 충돌 — 그래서 R1 + R2 점결합 필요. MVP는 인덱스 기반으로 처리.
}


def load(workbook_path: Path, normalizer: Normalizer) -> dict[str, pd.DataFrame]:
    """이지현 adiga_2027.xlsx의 `수시 입시결과` 시트 → {대학명: DataFrame}."""
    if not workbook_path.exists():
        return {}

    wb = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    if SHEET_NAME not in wb.sheetnames:
        return {}
    ws = wb[SHEET_NAME]

    # R1 = 그룹 헤더 (대부분 빈 셀, 'G:M=대학별환산', 'N:T=학생부등급' 위치에만 값)
    # R2 = 세부 헤더
    rows_iter = ws.iter_rows(values_only=True)
    r1 = next(rows_iter, None)
    r2 = next(rows_iter, None)
    if not r2:
        return {}

    # R1 그룹 정보 forward-fill
    group = [None] * len(r2)
    if r1:
        cur_group = None
        for i, v in enumerate(r1):
            if v is not None and str(v).strip():
                cur_group = str(v).strip()
            group[i] = cur_group

    # R2 헤더로 컬럼 매핑 인덱스 계산
    col_to_canonical: dict[int, str] = {}
    for i, name in enumerate(r2):
        if name is None:
            continue
        nm = str(name).strip()
        g = group[i] if i < len(group) else None

        # PK
        if nm == "대학":           col_to_canonical[i] = "대학"
        elif nm == "전형":         col_to_canonical[i] = "전형"
        elif nm == "모집단위":     col_to_canonical[i] = "모집단위"
        # 단순 컬럼
        elif nm == "모집인원":     col_to_canonical[i] = "모집인원"
        elif nm == "경쟁률":       col_to_canonical[i] = "경쟁률"
        elif nm == "충원합격순위": col_to_canonical[i] = "충원합격순위"
        elif nm == "반영교과":     col_to_canonical[i] = "반영교과"
        # 그룹 + 세부 결합
        elif g == "학생부등급":
            if nm == "평균":     col_to_canonical[i] = "학생부등급_평균"
            elif nm == "50컷":   col_to_canonical[i] = "학생부등급_50컷"
            elif nm == "70컷":   col_to_canonical[i] = "학생부등급_70컷"
        elif g == "대학별환산":
            if nm == "총점":     col_to_canonical[i] = "대학별환산_총점"

    # 데이터 수집 (R3+)
    by_univ: dict[str, list[dict]] = defaultdict(list)
    for row in rows_iter:
        if not row or all(c is None for c in row):
            continue
        rec: dict = {col: None for col in CANONICAL_COLUMNS}
        for i, v in enumerate(row):
            cn = col_to_canonical.get(i)
            if cn is None:
                continue
            if cn == "전형":
                rec[cn] = normalizer.jeonghyeong(v)
            elif cn in PK_COLUMNS:
                rec[cn] = normalizer.pk(v)
            elif cn == "모집인원":
                rec[cn] = normalizer.integer(v)
            elif cn in ("경쟁률", "학생부등급_평균", "학생부등급_50컷",
                        "학생부등급_70컷", "대학별환산_총점"):
                rec[cn] = normalizer.number(v)
            elif cn == "충원합격순위":
                n = normalizer.integer(v)
                rec[cn] = n if n is not None else (normalizer.cell(v) or None)
            elif cn == "반영교과":
                rec[cn] = normalizer.reflected_subjects(v)
            else:
                rec[cn] = normalizer.cell(v)

        univ = rec.get("대학")
        if not all(rec.get(k) for k in PK_COLUMNS):
            continue
        by_univ[univ].append(rec)

    return {
        univ: pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
        for univ, rows in by_univ.items()
        if rows
    }
