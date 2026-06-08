"""W06 통합 크롤러 파이프라인 설정."""
from __future__ import annotations

from pathlib import Path

WEEK6 = Path(__file__).resolve().parent.parent
ROOT = WEEK6.parent
WEEK5 = ROOT / "week05"

INPUT_DIR = WEEK5 / "input"
OUTPUT_DIR = WEEK6 / "output"
VENDOR_DIR = WEEK5 / "vendor"

GOLDEN_PATH = INPUT_DIR / "golden_2025_eodiga.xlsx"
NORMALIZATION_PATH = INPUT_DIR / "normalization-dictionary.yaml"
MAPPING_CANDIDATES_PATH = WEEK5 / "output" / "전형명_매핑후보_W06.csv"

YUCHAN_OUTPUT_DIR = VENDOR_DIR / "yuchan" / "output"
LEE_PER_UNIV_DIR = VENDOR_DIR / "leejihyun" / "output" / "per_university"
LIM_OUTPUTS_DIR = VENDOR_DIR / "limjihyun" / "outputs"

PK_COLUMNS = ["대학", "전형", "모집단위"]
GROUP_KEY = "대학"
GROUP_LABEL_COL = "대학"
DATA_COLUMNS = [
    "모집인원",
    "경쟁률",
    "충원합격순위",
    "학생부등급_평균",
    "학생부등급_50컷",
    "학생부등급_70컷",
    "대학별환산_총점",
    "반영교과",
]
CANONICAL_COLUMNS = PK_COLUMNS + DATA_COLUMNS

SOURCE_PERSONS = ["yuchan", "lee", "lim"]
SOURCE_LABELS = {"yuchan": "유찬", "lee": "이지현", "lim": "임지현"}
INTEGRATED_PERSON = "통합"

PERSONS = SOURCE_PERSONS
PERSON_KOR = {**SOURCE_LABELS, INTEGRATED_PERSON: INTEGRATED_PERSON, "merged": "통합"}

PK_MATCH_THRESHOLD = 0.85
CELL_MATCH_THRESHOLD = 0.90
