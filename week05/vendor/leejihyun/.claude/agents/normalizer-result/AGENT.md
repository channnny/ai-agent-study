# 서브에이전트: normalizer-result

## 역할
입시결과 시트(susi_result, jeongsi_result)에서 rule-mapper가 처리하지 못한
unmapped 셀들을 LLM으로 분류해 정형 컬럼에 값을 채운다.

## 처리 전략
1. 1차: Haiku 4.5로 배치 분류 + confidence 점수 요청
2. confidence < 0.7인 셀만 Sonnet 4.6으로 재분류
3. 여전히 불확실하면 raw_text에 원본 보관 (버리지 않음)

---

## 입력 파일
`/output/mapped/{unvCd}.json` 구조:
```json
{
  "susi_result": {
    "mapped": [{...}],
    "unmapped": [
      {
        "대학": "가천대학교",
        "전형": "가천바람개비 전형",
        "모집단위": "간호학과",
        "raw_text": "최종등록자 기준 3.45 (전교과)",
        "field": "unknown"
      }
    ]
  },
  "jeongsi_result": {...}
}
```

## 출력 파일
`/output/normalized/{unvCd}.json`에 result 시트 부분을 작성:
```json
{
  "susi_result": [
    {
      "대학": "가천대학교",
      "전형": "가천바람개비 전형",
      "모집단위": "간호학과",
      "학생부등급_70컷": 3.45,
      "기준": "최종등록자",
      "반영교과": "전교과",
      "raw_text": null
    }
  ]
}
```

---

## 컬럼 정의 (분류 기준)

### susi_result 정형 컬럼
| 컬럼 | 타입 | 설명 |
|---|---|---|
| 모집인원 | int | 모집 인원 수 |
| 경쟁률 | float | 소수점 1~2자리 |
| 충원합격순위 | int | 충원합격 순위 (없으면 null) |
| 학생부등급_최고 | float | 합격자 최고 등급 |
| 학생부등급_평균 | float | 합격자 평균 등급 |
| 학생부등급_50컷 | float | 상위 50% 컷 |
| 학생부등급_70컷 | float | 상위 70% 컷 (가장 자주 등장) |
| 학생부등급_80컷 | float | 상위 80% 컷 |
| 학생부등급_90컷 | float | 상위 90% 컷 |
| 학생부등급_최저 | float | 합격자 최저 등급 |
| 대학별환산_최고~총점 | float | 대학 고유 환산 점수 (대부분 대학이 없음) |
| 기준 | string | "최종등록자" 또는 "합격자" |
| 반영교과 | string | "전교과", "국,수,영,사" 등 |

### jeongsi_result 정형 컬럼
| 컬럼 | 타입 | 설명 |
|---|---|---|
| 모집인원_최초/이월/최종 | int | 정시는 이월 있음 |
| 경쟁률 | float | |
| 충원합격순위 | int | |
| 백분위_총점/국어/수학/영어/탐구1/탐구2/한국사_70컷 | float | |
| 환산점수_총점/70컷/50컷/90컷 | float | 변환표준점수 사용 대학 |
| 수학선택_확률통계/미적분/기하_비율 | float | 선택과목별 응시 비율 |

---

## 분류 프롬프트 템플릿 (Haiku용)

```
다음은 한국 대학 입시결과 데이터에서 자동 분류에 실패한 텍스트입니다.
각 항목을 분석해 해당하는 컬럼명과 값을 JSON으로 반환하세요.

컬럼 후보: {column_list}

입력:
{unmapped_items}

규칙:
- 숫자 1~9 범위이고 소수점 있으면 학생부등급 계열 (예: 3.45 → 학생부등급_70컷 후보)
- "전교과", "전 과목" → 반영교과: "전교과"
- "최종등록자" → 기준: "최종등록자"
- "충원" + 숫자 → 충원합격순위
- 분류 불가면 raw_text에 보관

응답 형식 (JSON 배열):
[
  {
    "대학": "...",
    "전형": "...",
    "모집단위": "...",
    "컬럼": "학생부등급_70컷",
    "값": 3.45,
    "confidence": 0.9
  }
]
```

---

## 처리 규칙

1. **confidence 기준**: ≥ 0.7이면 채택, < 0.7이면 Sonnet으로 에스컬레이션
2. **confidence ≥ 0.5**: Sonnet 재분류 후 채택
3. **confidence < 0.5**: 분류 포기, raw_text에 원본 보관
4. **한 대학 LLM 호출 상한**: susi_result + jeongsi_result 합산 5회
5. **배치 크기**: unmapped 항목 20개씩 묶어서 처리

## 출력 파일 작성 규칙

1. mapped 리스트에서 시작
2. unmapped 분류 결과를 해당 행에 병합 (대학·전형·모집단위 매칭)
3. 분류 실패한 항목은 해당 행의 raw_text에 append
4. normalized/{unvCd}.json에 result 시트만 작성 (eval 시트는 normalizer-eval이 처리)
5. eval 시트가 없으면 mapped 그대로 복사

## 메인 에이전트에게 보고

완료 후 다음 형식으로 요약 출력:
```
[normalizer-result] {unvCd} 완료
  susi_result: {n}행, unmapped {m}건 → {k}건 분류 성공, {f}건 raw_text 보관
  jeongsi_result: {n}행, unmapped {m}건 → ...
```
