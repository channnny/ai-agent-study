"""W05 정확도 비교 프로그램 — 경로·임계치 상수.

PK 매칭률 ≥ 85%, 셀 일치율 ≥ 90% — DoD (이지현 handoff-analysis §5.1).
"""
from __future__ import annotations
from pathlib import Path

# ──────────────────────────────────────────────────────────────
# 경로
# ──────────────────────────────────────────────────────────────
WEEK5 = Path(__file__).resolve().parent.parent  # week05/
ROOT = WEEK5.parent                              # repo root

INPUT_DIR  = WEEK5 / "input"
OUTPUT_DIR = WEEK5 / "output"
VENDOR_DIR = WEEK5 / "vendor"
LOGS_DIR   = OUTPUT_DIR / "logs"

GOLDEN_PATH        = INPUT_DIR / "golden_2025_susi.xlsx"
UNIVERSITIES_PATH  = INPUT_DIR / "universities_golden.csv"
NORMALIZATION_PATH = INPUT_DIR / "normalization-dictionary.yaml"

# 사람별 산출물 위치
YUCHAN_OUTPUT_DIR     = VENDOR_DIR / "yuchan" / "output"   # week03/output 미러
LEE_OUTPUT_WORKBOOK   = VENDOR_DIR / "leejihyun" / "output" / "adiga_2027.xlsx"
LIM_OUTPUTS_DIR       = VENDOR_DIR / "limjihyun" / "outputs"

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
# PK: (대학, 전형, 모집단위) 3-튜플 — 이지현 schema_v3.yaml과 일치
PK_COLUMNS = ["대학", "전형", "모집단위"]

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

CANONICAL_COLUMNS = PK_COLUMNS + DATA_COLUMNS

# ──────────────────────────────────────────────────────────────
# 사람 식별
# ──────────────────────────────────────────────────────────────
PERSONS = ["yuchan", "lee", "lim"]
PERSON_KOR = {"yuchan": "유찬", "lee": "이지현", "lim": "임지현"}
