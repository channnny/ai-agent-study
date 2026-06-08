# Claude Code 작업 규칙

이 폴더는 회사 AI 에이전트 학습 동아리의 **6주차** 폴더입니다.

## 6주차 성격

6주차는 **W05의 3인(유찬·이지현·임지현) 어디가 크롤러 출력을 하나로 통합**하는 주차.
- W05는 3인을 *각각* 골든셋과 비교(정확도 평가)했다.
- W06은 3인을 *병합*해 **커버리지·셀 충진율·셀 일치율을 동시에 극대화**한다.
- 목표: **누락되는 데이터 없이 최대한 많은 데이터를 모으는 것.**

## 통합 전략 (`src/merger.py`)

| 지표 | 병합 규칙 |
|---|---|
| **커버리지** | 행(PK=대학·전형·모집단위) **합집합** — 한 명이라도 긁은 행은 모두 포함 |
| **충진율** | 같은 행에서 셀별로 **값 있는 것** 채택. 소스 내 PK 중복은 **best_row(최다충진)** |
| **일치율** | 값이 갈리면 **항목별 신뢰도 우선(trust)**. 반올림 허용 합의 인정. `--strategy`로 전략 변경 |

- **골든셋 값은 병합에 절대 쓰지 않는다** → 평가 독립성 유지(치팅 아님).
- 신뢰도는 W05 평가의 **항목별(8개) 셀 일치율 집계만** 사용(골든 개별 셀 미참조).
- 셀 충돌은 `통합계보(lineage)`로 추적 (후보값·채택출처).
- **claude↔codex 교차 학습**: codex에서 best_row·반올림합의·trust-first 흡수, claude는
  반영교과 과목집합 정규화로 더 확장 → 두 구현 모두 초과. 상세 `docs/design.md` §4.

## 작업 원칙 (W05 계승)

- **scope**: 골든셋(`golden_2025_eodiga.xlsx`)이 진실원. 수시 결과만.
- **평가 기준 = 셀 일치율 ≥ 90%** (PK는 전형명 변동으로 참고 지표).
- **입력 데이터는 W05 재사용**: `config.py`의 `INPUT_DIR`·`VENDOR_DIR`가 `../week05`를 가리킴. 산출만 `week06/output`.
- **API 비용 0원**: 크롤러 재실행 없이 W05 vendor 산출물만 병합.

## 디렉토리 구조

```
week06/
  CLAUDE.md
  README.md
  docs/design.md            # 통합 설계·결과
  src/
    config.py               # 경로(W05 재사용)·임계치·MERGE_PRIORITY
    merger.py               # ★ 3인 → 통합 (행 합집합 + 셀 다수결)
    normalizer.py           # W05 계승
    adapters/               # golden/yuchan/leejihyun/limjihyun (W05 계승)
    matcher.py              # 평가(셀 일치율·충진율) (W05 계승)
    reporter.py             # 7시트 리포트 + 통합 데이터셋 출력
    cli.py                  # python -m src.cli
  output/
    evaluation_report_week06.xlsx    # 통합 vs 3인 비교 (7시트)
    integrated_crawler_week06.xlsx   # 통합 canonical 데이터 + 계보 (2시트)
```

## 실행

```bash
cd week06
# 최초 1회 venv 준비 (pandas/openpyxl/pyyaml/pytest)
python3 -m venv .venv && .venv/bin/pip install pandas openpyxl pyyaml pytest

.venv/bin/python -m src.cli \
  --report-name evaluation_report_week06.xlsx \
  --integrated-name integrated_crawler_week06.xlsx
# 옵션: --no-raw (리포트에 통합본만)

# 테스트
.venv/bin/python -m pytest tests/ -q
```

> 입력 데이터(`week05/input`·`week05/vendor`)는 W05 산출물을 재사용한다. 이 워크트리에는
> vendor 크롤러 출력이 함께 복사되어 있어 단독 실행 가능.

## W06 결과 (요약, 교차 학습 후)

| | 커버리지 | 셀 일치율 | 충진율 | 비교셀(절대량) | 정답셀≈ |
|---|---|---|---|---|---|
| **🔷통합** | **100.0%** | **96.8%** | 93.3% | **82,842** | **80,204** |
| 유찬 | 100.0% | 97.2% | 84.2% | 66,133 | 64,270 |
| 이지현 | 97.8% | 95.7% | 93.1% | 74,535 | 71,324 |
| 임지현 | 98.2% | 97.2% | 94.7% | 79,425 | 77,199 |

→ 통합은 단일 크롤러 최대치(임지현 79,425셀/77,199정답)를 상회하는 **82,842 비교셀 / ~80,204 정답셀**을 커버리지 100%로 수집 = "누락 없이 최다 데이터" 달성.
→ 통합 셀 일치율 **94.2%(v1) → 96.8%**: codex 학습(best_row·반올림합의·trust)과 claude 반영교과 정규화로 두 구현 모두 초과(codex 통합 95.53%).

## 한계 (W07+ 후속)

- 반영교과 잔여 ~25%: 골든 트랙상세 vs 크롤러 `전교과` 요약, 종합전형 `미기재`↔`서류평가`, 서술형 주석 — 정보량 차이라 사람 검수/파싱 정제 영역.
- 신뢰도 가중은 같은 골든 평가라 미세 낙관편향 가능 → `--strategy consensus`(골든 미참조, 96.2%)를 보수적 하한선으로 병행.
- 전형명 분류 차이(PK 격차)는 데이터랩스 전형명 표준 합의 후 해소.
