"""W06 3인 크롤러 통합 — 경로·임계치 상수.

W05의 3인(유찬·이지현·임지현) 산출물을 하나의 통합 데이터셋으로 병합해
커버리지·셀 충진율·셀 일치율을 동시에 극대화한다.
입력 데이터(골든·사전·vendor)는 W05 것을 그대로 재사용하고, 산출만 week06/output.

PK 매칭률은 전형명 변동으로 참고 지표(W05 회의 결정). 평가 기준 = 셀 일치율 ≥ 90%.
"""
from __future__ import annotations
from pathlib import Path

# ──────────────────────────────────────────────────────────────
# 경로 — 입력은 W05 재사용, 출력은 W06
# ──────────────────────────────────────────────────────────────
WEEK6 = Path(__file__).resolve().parent.parent   # week06/
ROOT = WEEK6.parent                              # repo root
WEEK5 = ROOT / "week05"                            # 입력 데이터 재사용처

INPUT_DIR  = WEEK5 / "input"                       # 골든·사전 (W05)
VENDOR_DIR = WEEK5 / "vendor"                      # 3인 산출물 (W05)
OUTPUT_DIR = WEEK6 / "output"                      # 산출은 W06
LOGS_DIR   = OUTPUT_DIR / "logs"

GOLDEN_PATH        = INPUT_DIR / "golden_2025_eodiga.xlsx"
UNIVERSITIES_PATH  = INPUT_DIR / "universities_golden.csv"
NORMALIZATION_PATH = INPUT_DIR / "normalization-dictionary.yaml"

# 사람별 산출물 위치
YUCHAN_OUTPUT_DIR     = VENDOR_DIR / "yuchan" / "output"   # week03/output 미러 ({unvCd}_{대학명}/ 폴더)
LEE_PER_UNIV_DIR      = VENDOR_DIR / "leejihyun" / "output" / "per_university"  # {unvCd}.xlsx
LIM_OUTPUTS_DIR       = VENDOR_DIR / "limjihyun" / "outputs"  # {unvCd}.xlsx

# 유찬 크롤러 실제 위치 (week03/output)
YUCHAN_ACTUAL_OUTPUT  = ROOT / "week03" / "output"

# ──────────────────────────────────────────────────────────────
# DoD 임계치
# ──────────────────────────────────────────────────────────────
PK_MATCH_THRESHOLD   = 0.85
CELL_MATCH_THRESHOLD = 0.90

# ──────────────────────────────────────────────────────────────
# 캐노니컬 스키마 (MVP — 모든 사람 출력 공통 부분만)
# ──────────────────────────────────────────────────────────────
# PK: (대학, 전형, 모집단위) — 새 골든셋(어디가입결_통합본)은 unvCd가 없고
#     대학명만 있다. 새 골든·유찬 둘 다 어디가 기반이라 대학명이 직접 일치.
PK_COLUMNS = ["대학", "전형", "모집단위"]

# 대학 그룹핑 키 (어댑터가 반환하는 dict의 key) = 대학명
GROUP_KEY = "대학"
# 표시용 대학명 컬럼 = PK의 대학 그 자체
GROUP_LABEL_COL = "대학"

# 데이터 컬럼 (전부 nullable. float은 NaN 허용)
DATA_COLUMNS = [
    "모집인원",            # int
    "경쟁률",              # float
    "충원합격순위",        # int|str (e.g. "0", "1", "ALL")
    "학생부등급_평균",     # float
    "학생부등급_50컷",     # float
    "학생부등급_70컷",     # float
    "대학별환산_총점",     # float
    "반영교과",            # str (전교과 등)
]

# 캐노니컬 컬럼: PK(대학·전형·모집단위) + 데이터 (대학명이 PK에 포함됨)
CANONICAL_COLUMNS = PK_COLUMNS + DATA_COLUMNS

# ──────────────────────────────────────────────────────────────
# 사람 식별
# ──────────────────────────────────────────────────────────────
PERSONS = ["yuchan", "lee", "lim"]
PERSON_KOR = {"yuchan": "유찬", "lee": "이지현", "lim": "임지현", "merged": "🔷통합"}

# 통합 데이터의 셀 선택 우선순위 (다수결 동률 시 충진율·정확도 높은 순)
MERGE_PRIORITY = ["lim", "lee", "yuchan"]
