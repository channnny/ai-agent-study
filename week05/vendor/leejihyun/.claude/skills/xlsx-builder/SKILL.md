# 스킬: xlsx-builder

## 역할
normalized/{unvCd}.json 파일들을 모아 골든셋 양식의 엑셀 워크북을 생성한다.
- 통합 워크북: `output/adiga_{year}.xlsx` (4시트 + error + summary + new_columns)
- 대학별 워크북: `output/per_university/{unvCd}.xlsx` (4시트)

## 트리거
T4 LLM 정규화 완료 후 T5 단계에서 메인 에이전트가 호출.

## 입력
- `--year`: 학년도 (예: 2027)
- `--normalized-dir`: normalized/ 디렉토리 경로
- `--per-univ-dir`: per_university/ 출력 디렉토리
- `--output`: 통합 워크북 경로
- `--schema`: schema_v3.yaml 경로
- `--errors`: 에러 로그 경로 (error 시트용)
- `--new-columns`: new_columns_proposals.json 경로 (있으면 추가)
- `--state`: run_state.json 경로

## 출력
- `output/adiga_{year}.xlsx`: 7시트 통합 워크북
- `output/per_university/{unvCd}.xlsx`: 대학별 4시트 워크북

## 성공 기준
- 통합 워크북 7시트 모두 존재
- susi_result 시트 헤더가 골든셋과 동일 (2단 헤더, 그룹 병합)

## 의존성
```
pip install openpyxl pyyaml
```

## 실행 예시
```bash
python .claude/skills/xlsx-builder/scripts/build.py \\
  --year 2027 \\
  --normalized-dir output/normalized \\
  --per-univ-dir output/per_university \\
  --output output/adiga_2027.xlsx \\
  --schema input/schema_v3.yaml \\
  --errors output/logs/error_log.json \\
  --new-columns output/logs/new_columns_proposals.json
```
