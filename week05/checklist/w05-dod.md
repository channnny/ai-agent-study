# W05 DoD 체크리스트

## 0단계 · 데이터 준비

- [x] 이지현 zip 추출 (`vendor/leejihyun/`, .env 격리)
- [x] 임지현 zip 추출 (`vendor/limjihyun/`, .env 격리)
- [x] 골든셋 사본 (`input/golden_2025_susi.xlsx`)
- [x] 173개 대학 추출 → `input/universities_golden.csv`
- [x] 정규화 사전 yaml화 (`input/normalization-dictionary.yaml`)
- [x] 유찬 크롤러 173대학 실행 (150개 디렉토리 생성, 23개 결과 없음)
- [x] 이지현 `run.py --skip-llm` 173대학 실행 (157개 대학 출력)
- [x] 임지현 zip 안의 8대학 outputs 배치

## 1단계 · src/ 구현

- [x] `config.py` (캐노니컬 스키마, 임계치)
- [x] `normalizer.py` (9섹션 사전 → 4섹션 적용 + PK·전형 정규화)
- [x] `adapters/golden.py`
- [x] `adapters/yuchan.py` (단순 패턴, 복잡 패턴 스킵)
- [x] `adapters/leejihyun.py` (4시트 → 수시 입시결과만)
- [x] `adapters/limjihyun.py` (단일 수시 시트)
- [x] `matcher.py` (PK 조인 + 셀 비교)
- [x] `reporter.py` (6시트 엑셀)
- [x] `cli.py` (`python -m src.cli`)

## 2단계 · 검증

- [x] pytest 33 case 통과 (`tests/test_normalizer.py`, `test_matcher.py`)
- [x] end-to-end 실행 성공 (3인 평가 → 6시트 리포트)
- [x] 회귀: 이지현 결과 측정 (PK 41% — 100% 이상 일치 보장은 불가, 출처 vs 출처 비교라 다른 의미)

## 산출물 검증

- [x] `output/evaluation_report_<ts>.xlsx` 6시트 모두 채워짐
- [x] summary 시트에 3인 PK/Cell 비교 가능
- [x] mismatched_cells `비고` 컬럼에 차이 유형 표시 (콤마 차이, 근접값, null 비대칭 등)
- [x] missing_rows / extra_rows 분리되어 PK 누락·여분 분석 가능

## W05 마무리

- [ ] W05 회의에서 리포트 화면 공유
- [ ] 회의 결과 → `docs/meeting-notes.md` 기록
- [ ] W06 개선 사항 정리:
  - [ ] 유찬 어댑터 — 복잡 패턴(단과대학+모집단위) 지원
  - [ ] 정규화 사전 — 나머지 5섹션 적용
  - [ ] 전형 카테고리 분류 차이 해소 (3인 합의 후 사전 보강)
  - [ ] 정시·평가기준 시트 확장

## 비대상 (W06+)

- 임지현 크롤러 재실행 (API 키 이슈)
- 골든셋 자체의 학년도/소스 정정 (외부 권한)
- 220+ 대학 확장 (이미 173 골든셋 전체 커버 중)
