"""유찬 산출물(`week03/output/{unvCd}_{대학}/<탭>_전형결과.xlsx`) → 캐노니컬 DataFrame.

크롤러가 다단 헤더(rowspan/colspan)를 평면화하므로, 각 시트는 1행 평면 헤더 +
데이터 구조다. 첫 컬럼은 "전형"(크롤러가 삽입), 그 뒤에 모집단위/모집인원/… 가 온다.

평면 헤더 예:
  [전형, 모집단위, 모집인원, 경쟁률, 충원 합격 순위,
   최종등록자 교과성적 학생부등급 70% cut, … 90% cut]
경북대(복잡)도 평면화됨:
  [전형, 단과대학, 모집단위, 지원 및 등록 현황 모집 인원, … 입학자 학생부 등급 평균/50%/70%]

# adapted from week03/crawl_adiga.py 평면화 출력 실측
"""
from __future__ import annotations
import pandas as pd
import openpyxl
from pathlib import Path
from collections import defaultdict

from ..config import PK_COLUMNS, CANONICAL_COLUMNS, GROUP_LABEL_COL
from ..normalizer import Normalizer


def _match_canonical(header: str) -> str | None:
    """평면 헤더 텍스트 → 캐노니컬 컬럼명. 일치 안 되면 None.

    우선순위가 중요(긴 패턴 먼저) — 예: '학생부등급 70%'는 70컷, '평균'은 평균.
    """
    if not header:
        return None
    h = str(header).strip().replace(" ", "")  # 공백 제거 ("7 0%"→"70%", "모집 인원"→"모집인원")

    # 학생부 등급 컷 (등급/교과성적 맥락 + 컷 지표)
    is_grade = ("등급" in h) or ("교과성적" in h)
    if is_grade:
        if "50%" in h or "50컷" in h:
            return "학생부등급_50컷"
        if "70%" in h or "70컷" in h:
            return "학생부등급_70컷"
        if "평균" in h:
            return "학생부등급_평균"
        # 90%/85% 등은 캐노니컬에 없음 → 무시

    # 모집인원 (지원인원·입학인원과 구분: '모집'+'인원', '지원'/'입학' 제외)
    if "모집인원" in h and "지원" not in h and "입학" not in h:
        return "모집인원"

    # 경쟁률 (실질/최초/지원 변형 제외 — 순수 경쟁률만)
    if "경쟁률" in h and not any(x in h for x in ("실질", "최초", "지원")):
        return "경쟁률"

    # 충원/추합 순위
    if ("충원" in h and "순위" in h) or "충원합격" in h or ("추합" in h and ("번호" in h or "순위" in h)):
        return "충원합격순위"

    # 반영교과
    if ("반영" in h and "교과" in h) or "교과목" in h:
        return "반영교과"

    return None


def _parse_flat_table(ws, unv_cd: str, university: str, normalizer: Normalizer) -> list[dict]:
    """평면화된 시트 1개 파싱. R1=평면 헤더, R2+=데이터. col0='전형'."""
    rows_iter = ws.iter_rows(values_only=True)
    header = next(rows_iter, None)
    if not header:
        return []

    # 헤더 → 컬럼 인덱스 매핑
    col_map: dict[int, str] = {}
    jeonghyeong_col = None
    moljip_col = None
    for i, h in enumerate(header):
        if h is None:
            continue
        hs = str(h).strip()
        if hs == "전형":
            jeonghyeong_col = i
            continue
        if hs == "모집단위":
            moljip_col = i
            col_map[i] = "모집단위"
            continue
        cn = _match_canonical(hs)
        if cn and cn not in col_map.values():  # 첫 매칭 우선(중복 헤더 방지)
            col_map[i] = cn

    # 모집단위 컬럼이 없으면 신뢰 불가 → 스킵
    if moljip_col is None:
        return []

    records = []
    for row in rows_iter:
        if not row or all(c is None for c in row):
            continue
        rec: dict = {c: None for c in CANONICAL_COLUMNS}
        rec["unvCd"] = unv_cd
        rec["대학"] = university
        if jeonghyeong_col is not None and jeonghyeong_col < len(row):
            rec["전형"] = normalizer.jeonghyeong(row[jeonghyeong_col])

        for i, v in enumerate(row):
            cn = col_map.get(i)
            if cn is None:
                continue
            if cn == "모집단위":
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

        if not all(rec.get(k) for k in PK_COLUMNS):
            continue
        records.append(rec)
    return records


def load(output_root: Path, normalizer: Normalizer) -> dict[str, pd.DataFrame]:
    """`week03/output/{unvCd}_{대학명}/*.xlsx` 전체 → {unvCd: DataFrame}.

    크롤러가 헤더를 평면화하므로 모든 표를 _parse_flat_table로 처리.
    """
    by_univ: dict[str, list[dict]] = defaultdict(list)

    if not output_root.exists():
        return {}

    for univ_dir in sorted(output_root.iterdir()):
        if not univ_dir.is_dir():
            continue
        folder = univ_dir.name
        if "_" in folder:
            unv_cd, univ_name = folder.split("_", 1)
        else:
            unv_cd, univ_name = folder, folder

        for xlsx in sorted(univ_dir.glob("*.xlsx")):
            # 골든셋은 수시(susi)만 → 정시(수능위주) 탭은 비교 대상 아님, 제외
            if "수능위주" in xlsx.name:
                continue
            try:
                wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
            except Exception:
                continue
            for sn in wb.sheetnames:
                recs = _parse_flat_table(wb[sn], unv_cd, univ_name, normalizer)
                if recs:
                    by_univ[unv_cd].extend(recs)

    return {
        unv_cd: pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
        for unv_cd, rows in by_univ.items()
        if rows
    }
