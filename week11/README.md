# W11 — 전형정보 정제 프로그램 (순수 결정적)

4단계 "피드백 기반 개선·마무리". W09~W10 크롤 **통합본**(2시트 RAW)을 입력받아,
사용자 화면(교과내신계산기·교과ON·교과ON리포트)용 **정제 데이터**를 **시트3**으로 추가한다.

- 설계: [docs/superpowers/specs/2026-07-13-refine-program-design.md](docs/superpowers/specs/2026-07-13-refine-program-design.md)
- 엔진: **순수 결정적**(규칙/regex, LLM 없음). 재현성 100%.
- 정제 6종: ①N합N ②영역조합 ③교과반영영역 ④진로A/B/C 5a전형요소별 5b학년/요소별.
- 핑퐁 방지: 난케이스 `검증필요:<사유>` 플래그 + 골드셋(참고 시트3 1,353행) 회귀 대조.

## input/ (근거 자료 — 데이터랩스 핸드오프)
- `README_핸드오프.md`, `정제룰_정의서.xlsx`(룰 SSOT), `reference_전형정보_통합_정제.xlsx`(골드셋), `정제_검증샘플_4대학.xlsx`(검증노트)

## 실행

```bash
# 정제 — 통합본 2시트 RAW → 시트3 '정제' 추가 (인자 생략 시 week10 test 통합본)
../week05/.venv/bin/python scripts/refine/build.py ../week10/output/전형정보_통합.xlsx
```

```bash
# 검토필요 시트 — 사람 확인이 필요한 셀만 추출
../week05/.venv/bin/python scripts/refine/review.py output/전형정보_통합_정제.xlsx
```

```bash
# 검토필요 + 골든셋 정합성 통합 리포트 (3시트)
../week05/.venv/bin/python scripts/refine/report.py output/전형정보_통합_정제.xlsx --out=output/정제_검토필요_정합성검증.xlsx
```

```bash
# 눈검수용 랜덤 샘플 ([원본]↔[정제] 나란히, 시드 고정)
../week05/.venv/bin/python scripts/refine/sample_review.py --n=30 --seed=11
```

```bash
# 단위 테스트 (pytest 불필요)
python3 tests/test_refine.py
```

> `report.py`의 기본 출력 경로(`DEF_OUT`)는 로컬 Downloads 경로로 하드코딩돼 있다 — `--out=` 로 지정할 것.

## 결과 (현재)

| 항목 | 값 |
|---|---|
| `output/전형정보_통합_정제.xlsx` | RAW 2시트 + **정제 시트** 48,367행 × 18열 |
| `output/검토필요.xlsx` | **216건** (사유·해결책 컬럼 포함) |
| `output/정제검수_샘플.xlsx` | 눈검수용 stratified 샘플 |
| 단위 테스트 | 6/6 PASS (`tests/test_refine.py`) |

검토필요는 7,510건 → 225건 → **216건**으로 축소 (진로 A/B/C 범용 파싱, 내부확인 케이스 제외, 최저 '등급이 N 이내' 패턴 추가).
