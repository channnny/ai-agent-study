# Claude Code 실습 프롬프트

아래 내용을 Claude Code 세션에 그대로 붙여넣어 실습합니다.

```text
이 프로젝트는 AI 에이전트 학습 동아리의 1주차 개발자 실습입니다.

먼저 현재 디렉터리의 CLAUDE.md를 읽고 작업 규칙을 이해해줘.

그 다음 input/sample-admission-raw.md 파일을 읽고 아래 결과물을 만들어줘.

1. output/sample-admission-summary.md
   - 사람이 검수하기 쉬운 줄글 Markdown으로 작성
   - 대학/학과별 한 문단 요약
   - 확인 필요 사항
   - 사람 검수 체크리스트
   - 다음 주차로 넘길 질문 포함

2. output/sample-admission-summary.json
   - DB 입력 가능성을 고려한 구조화 JSON
   - university, department, admissionType, quota, selectionMethod, minimumRequirement, documents, notes, summary, needsReview 필드 포함
   - 불명확한 내용은 needsReview에 넣기
   - 원본에 없는 내용은 추측하지 않기

3. logs/claude-session-note.md
   - 네가 수행한 작업 요약
   - 생성/수정한 파일 목록
   - 사람이 확인해야 할 점
   - 다음 주차 질문 정리

중요:
- 원본에 없는 경쟁률, 합격선, 내신 등급 등은 절대 만들지 마.
- `없음`과 `확인 불가`를 구분해.
- Markdown 결과와 JSON 결과가 서로 일치해야 해.
```
