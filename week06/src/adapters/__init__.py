"""사람별 산출물 → 캐노니컬 DataFrame 변환 어댑터.

공통 시그니처: `def load(...) -> dict[str, pd.DataFrame]`
key=대학명, value=PK 3컬럼 + DATA_COLUMNS 컬럼을 가진 DataFrame.
"""
