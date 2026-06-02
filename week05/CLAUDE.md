# Claude Code 작업 규칙

이 폴더는 회사 AI 에이전트 학습 동아리의 5주차 폴더입니다.

## 5주차 성격

5주차는 **3인(유찬·이지현·임지현) 어디가 크롤러 출력 vs 골든셋 정확도 비교 프로그램** 구현 주차.
W04에서 결정: "25학년도 전형 결과를 가지고, 크롤링 → 정확도 체크할 수 있는 기능 구현하기".

## 작업 원칙

- **scope**: 골든셋(`2025_수시_입시결과_통합본.xlsx`, 173 대학, 23,959행)이 진실원.
- **수시 결과만**, 정시·평가기준은 W06+.
- **DoD**: PK 매칭률 ≥ 85%, 셀 일치율 ≥ 90% (이지현 설계 기준).
- **API 비용 0원**: 이지현은 Claude Code(`--skip-llm` 또는 Pro 구독), 유찬은 LLM 미사용, 임지현은 기존 zip 산출물 사용 (본인 개인 키 보호).
- **3인 통합 리포트** (`output/evaluation_report_*.xlsx` 6시트, 사람별 컬럼 확장).
- **사람 판단 필요 항목은 `mismatched_cells.비고` 컬럼**에 정규화 후에도 동치 가능성을 표시.

## 디렉토리 구조

```
week05/
  src/                       # 평가 프로그램
    config.py                # 경로·임계치
    normalizer.py            # 9섹션 사전 → MVP 4섹션 적용
    adapters/                # 사람별 출력 → 캐노니컬 DataFrame
      golden.py / yuchan.py / leejihyun.py / limjihyun.py
    matcher.py               # PK 정규화·조인·셀 비교
    reporter.py              # 6시트 엑셀 출력
    cli.py                   # python -m src.cli
  input/                     # 정답·사전·대학 리스트
  vendor/<person>/           # 사람별 크롤러 산출물 (read-only)
  output/                    # 평가 리포트 산출
  tests/                     # pytest (normalizer + matcher 단위)
```

## 실행

```bash
# 1) 데이터 준비 (한 번만)
.venv/bin/python -m src.cli   # 즉시 가능, 0단계 완료 상태

# 2) 평가
.venv/bin/python -m src.cli
# → output/evaluation_report_<ts>.xlsx 6시트 (summary/by_university/by_column/missing/extra/mismatched)
```

## MVP 한계 (W06+ 개선 대상)

- 유찬 크롤러 raw 출력에서 "단과대학+모집단위" 패턴(경북대 등)의 복잡 테이블은 스킵 → 단순 패턴(가천대 등)만 파싱. by_university에서 status=fail로 표시됨.
- 9섹션 정규화 사전 중 MVP는 4섹션만 적용 (NULL·숫자·반영교과·전형구분 일부).
- 골든셋 vs 사람 사이 **실제 전형 카테고리 분류 차이** (예: 골든 "특성화고교(종합)" vs 이지현 "특성화고교")는 정규화로 해결 불가 — 회의에서 합의 필요.
