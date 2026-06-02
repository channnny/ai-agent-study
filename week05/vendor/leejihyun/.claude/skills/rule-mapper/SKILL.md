# 스킬: rule-mapper

## 역할
파싱된 raw JSON(T2 출력)에 정규화 사전과 스키마를 적용해
정형 컬럼에 값을 채우고, 매핑 못 한 항목은 unmapped로 분리한다.

## 트리거
T2 파싱 완료 후 T3 단계에서 메인 에이전트가 대학별로 호출.

## 입력
- `--unvcd`: 대학 코드
- `--parsed`: parsed/{unvCd}.json 경로
- `--schema`: schema_v3.yaml 경로
- `--output`: mapped/{unvCd}.json 경로

## 출력
`{output}` JSON 형식:
```json
{
  "susi_result": {
    "mapped": [{row}, ...],
    "unmapped": [{"대학": "...", "전형": "...", "모집단위": "...", "raw_text": "...", "field": "..."}, ...]
  },
  "susi_eval": {...},
  "jeongsi_result": {...},
  "jeongsi_eval": {...}
}
```

## 성공 기준
- 행 수 손실 없음 (T2 출력과 동일한 행 수)
- 전체 평균 매핑률 ≥ 60%

## 의존성
```
pip install pyyaml
```

## 실행 예시
```bash
python .claude/skills/rule-mapper/scripts/map_columns.py \
  --unvcd 0000063 \
  --parsed output/parsed/0000063.json \
  --schema input/schema_v3.yaml \
  --output output/mapped/0000063.json
```

## 참조
- `/docs/references/normalization-dictionary.md`: 표기 정규화 규칙
