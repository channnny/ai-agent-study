# Claude Code 작업 규칙

이 프로젝트는 회사 AI 에이전트 학습 동아리의 1주차 개발자 실습 프로젝트입니다.

## 프로젝트 목적

입학 전형 원본 데이터를 읽고, 사람이 검수하기 쉬운 줄글 형태와 DB 입력 준비용 JSON 형태로 정리합니다.

## 작업 원칙

- 원본에 없는 내용은 절대 추측하지 않습니다.
- 불명확한 내용은 `확인 필요`로 표시합니다.
- 결과물은 사람이 검수하기 쉬워야 합니다.
- 모집인원, 전형방법, 수능최저학력기준, 제출서류는 반드시 확인합니다.
- Markdown 결과와 JSON 결과의 내용은 서로 일치해야 합니다.
- JSON에는 DB 입력 가능성을 고려해 명확한 필드명을 사용합니다.
- 작업 후 로그 파일에 수행 내용, 변경 파일, 검수 포인트, 다음 질문을 남깁니다.

## Markdown 출력 형식

`output/sample-admission-summary.md`는 아래 형식을 따릅니다.

```md
# 입학 전형 데이터 정제 결과

## 1. 요약 결과

### A대학교 소프트웨어학부

...

### B대학교 컴퓨터공학과

...

## 2. 확인 필요 사항

...

## 3. 사람 검수 체크리스트

- [ ] 모집인원 확인
- [ ] 전형방법 확인
- [ ] 수능최저학력기준 확인
- [ ] 제출서류 확인
- [ ] 원본에 없는 내용이 추가되지 않았는지 확인
```

## JSON 출력 형식

`output/sample-admission-summary.json`은 아래 구조를 따릅니다.

```json
{
  "sourceFile": "input/sample-admission-raw.md",
  "generatedAt": "2026-04-30",
  "items": [
    {
      "university": "",
      "department": "",
      "admissionType": "",
      "quota": null,
      "selectionMethod": [],
      "minimumRequirement": "",
      "documents": [],
      "notes": [],
      "summary": "",
      "needsReview": []
    }
  ],
  "globalReviewPoints": []
}
```

## 금지 사항

- 원본에 없는 경쟁률, 입결, 합격선, 내신 등급을 임의로 생성하지 않습니다.
- `없음`과 `확인 불가`를 혼동하지 않습니다.
- JSON에 Markdown 문법을 섞지 않습니다.
- 불명확한 항목을 빈 문자열로 방치하지 않습니다.
