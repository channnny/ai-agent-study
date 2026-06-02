# 스킬: evaluator

## 역할
에이전트가 생성한 susi_result 시트를 골든셋(2025_어디가입결_통합본.xlsx)과 비교해
PK 매칭률·셀 일치율·컬럼별 정확도를 계산하고 리포트 엑셀을 생성한다.

## 트리거
T5 엑셀 빌드 완료 후 T6 단계에서 메인 에이전트가 호출.
선택적 단계 — 실패 시 스킵.

## 입력
- `--golden`: 골든셋 엑셀 경로
- `--predicted`: 에이전트 생성 엑셀 경로
- `--out`: 리포트 출력 경로
- `--targets`: 평가 대상 대학명 리스트 (기본: 8개 타겟)
- `--sheet`: 골든셋 시트명 (기본: 수시)
- `--pred-sheet`: 에이전트 시트명 (기본: 수시 입시결과)

## 출력
`evaluation_report.xlsx` (6시트):
- summary: 전체 지표
- by_university: 대학별 PK/셀 일치율
- by_column: 컬럼별 정확도
- missing_rows: 골든셋에 있는데 에이전트가 못 찾은 행
- extra_rows: 에이전트가 생성한 잉여행
- mismatched_cells: 값이 다른 셀 목록

## 성공 기준 (DoD)
- PK 매칭률 ≥ 85%
- 셀 일치율 ≥ 90% (매칭된 행 한정)

## 의존성
```
pip install openpyxl pandas
```

## 실행 예시
```bash
python .claude/skills/evaluator/scripts/evaluate.py \\
  --golden input/2025_어디가입결_통합본.xlsx \\
  --predicted output/adiga_2027.xlsx \\
  --out output/evaluation_report.xlsx
```
