# 스킬: html-parser

## 역할
adiga 페이지 raw HTML을 BeautifulSoup으로 파싱해 4시트 raw DataFrame을 JSON으로 저장한다.
탭(Ⅱ.학생부종합, Ⅲ.학생부교과, Ⅳ.수능위주)과 섹션(Q1 평가기준, Q2 결과)을 식별해
4개 시트(susi_eval, susi_result, jeongsi_eval, jeongsi_result)로 분류한다.

## 트리거
T1 크롤링 완료 후 T2 파싱 단계에서 메인 에이전트가 대학별로 호출.

## 입력
- `--unvcd`: 대학 코드
- `--univ`: 대학명
- `--html`: raw HTML 파일 경로
- `--output`: 파싱 결과 JSON 경로
- `--errors`: 에러 로그 경로

## 출력
`{output}` JSON 형식:
```json
{
  "susi_result": [{"대학": "...", "전형": "...", "모집단위": "...", "모집인원": 30, ...}],
  "susi_eval":   [{"대학": "...", "전형": "...", "모집단위": "...", "raw_text": "..."}],
  "jeongsi_result": [...],
  "jeongsi_eval":   [...]
}
```

## 성공 기준
- 4시트 모두 최소 1행 이상 (평가기준은 전 모집단위 일괄도 OK)
- PK 컬럼(대학·전형·모집단위) 비어있지 않음

## 의존성
```
pip install beautifulsoup4 lxml
```

## 실행 예시
```bash
python .claude/skills/html-parser/scripts/parse.py \
  --unvcd 0000063 \
  --univ 가천대학교 \
  --html output/raw_html/0000063.html \
  --output output/parsed/0000063.json
```

## 참조
- `/docs/references/adiga-site-reference.md`: HTML 구조 패턴
- `references/adiga-html-structure.md`: 내부 참조 (이 스킬 디렉토리)
