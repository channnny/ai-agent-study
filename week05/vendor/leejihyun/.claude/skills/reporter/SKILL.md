# 스킬: reporter

## 역할
모든 산출물을 취합해 충진율·이슈 요약·신규 컬럼 후보를 담은 validation_report.md를 생성한다.

## 트리거
T6 평가 완료 후 T7 단계에서 메인 에이전트가 호출.
선택적 단계 — 실패 시 스킵.

## 입력
- `--normalized-dir`: normalized/ 디렉토리
- `--schema`: schema_v3.yaml 경로
- `--eval-report`: evaluation_report.xlsx 경로 (없으면 생략)
- `--errors`: error_log.json 경로
- `--new-columns`: new_columns_proposals.json 경로
- `--out`: validation_report.md 출력 경로

## 출력
`validation_report.md` (섹션):
1. 실행 요약
2. 시트별 충진율 표
3. 평가 결과 요약 (골든셋 비교)
4. 신규 컬럼 후보
5. 이슈 및 권고사항

## 의존성
```
pip install openpyxl pyyaml
```

## 실행 예시
```bash
python .claude/skills/reporter/scripts/report.py \\
  --normalized-dir output/normalized \\
  --schema input/schema_v3.yaml \\
  --eval-report output/evaluation_report.xlsx \\
  --errors output/logs/error_log.json \\
  --new-columns output/logs/new_columns_proposals.json \\
  --out output/validation_report.md
```
