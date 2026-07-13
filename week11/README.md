# W11 — 전형정보 정제 프로그램 (순수 결정적)

4단계 "피드백 기반 개선·마무리". W09~W10 크롤 **통합본**(2시트 RAW)을 입력받아,
사용자 화면(교과내신계산기·교과ON·교과ON리포트)용 **정제 데이터**를 **시트3**으로 추가한다.

- 설계: [docs/superpowers/specs/2026-07-13-refine-program-design.md](docs/superpowers/specs/2026-07-13-refine-program-design.md)
- 엔진: **순수 결정적**(규칙/regex, LLM 없음). 재현성 100%.
- 정제 6종: ①N합N ②영역조합 ③교과반영영역 ④진로A/B/C 5a전형요소별 5b학년/요소별.
- 핑퐁 방지: 난케이스 `검증필요:<사유>` 플래그 + 골드셋(참고 시트3 1,353행) 회귀 대조.

## input/ (근거 자료 — 데이터랩스 핸드오프)
- `README_핸드오프.md`, `정제룰_정의서.xlsx`(룰 SSOT), `reference_전형정보_통합_정제.xlsx`(골드셋), `정제_검증샘플_4대학.xlsx`(검증노트)

## 실행 (구현 후)
```bash
../week05/.venv/bin/python scripts/refine/build.py <통합본.xlsx>   # → <통합본>_정제.xlsx
../week05/.venv/bin/python scripts/refine/validate.py             # 골드 대조 리포트
```
