# adiga 입시 데이터 수집 에이전트

## 1. 역할

이 에이전트는 adiga(대입정보포털)에서 대학 입시 데이터를 수집·정규화·엑셀화하는 워크플로우의 **오케스트레이터**다.
직접 처리하지 않고, 스킬(Python 스크립트)과 서브에이전트(LLM 판단)에 모든 작업을 위임한다.

참조 문서:
- 전체 설계: `/docs/agent_design.md`
- 컬럼 스키마: `/input/schema_v3.yaml`
- URL/HTML 구조: `/docs/references/adiga-site-reference.md`
- 정규화 사전: `/docs/references/normalization-dictionary.md`

---

## 2. 입력 인터페이스

실행 형식:
```
python run.py --year 2027 --mode full
python run.py --year 2027 --mode partial --unvcd 0000063 0000019
python run.py --year 2027 --mode full --force   # run_state.json 무시하고 재실행
```

| 인자 | 설명 |
|---|---|
| `--year` | URL searchSyr 값 (2027 = 2026학년도 평가기준 + 2025학년도 결과) |
| `--mode` | `full` (전체) 또는 `partial` (특정 대학만) |
| `--unvcd` | partial 모드 시 대학 코드 리스트 |
| `--force` | run_state.json의 완료 상태 무시하고 재실행 |
| `--golden` | 골든셋 파일 경로 (기본: `/input/2025_어디가입결_통합본.xlsx`) |
| `--schema` | 스키마 파일 경로 (기본: `/input/schema_v3.yaml`) |
| `--workers` | 동시 크롤링 워커 수 (기본: 3) |

---

## 3. 워크플로우 실행 순서

### T0. 준비 단계
1. CLI 인자 파싱·검증
2. 골든셋 파일 존재 및 21,000+ 행 확인
3. 스키마 YAML 파싱 및 4시트 정의 확인
4. `/input/universities.csv`에서 대학 리스트 결정
5. 출력 디렉토리 생성 (`/output/`, 하위 폴더)
6. `/output/run_state.json` 로드 (없으면 빈 dict 생성)

**실패 시**: 즉시 종료 + 콘솔 에러 출력

### T1. 크롤링
스킬: `.claude/skills/adiga-crawler/scripts/crawl.py`
```
python .claude/skills/adiga-crawler/scripts/crawl.py \
  --unvcd {unvCd 리스트} \
  --year {year} \
  --workers {workers} \
  --output output/raw_html \
  --state output/run_state.json \
  --errors output/logs/error_log.json
```
**성공 기준**: HTTP 200 + HTML ≥ 10KB
**실패 시**: 3회 재시도(지수 백오프) → 스킵 + error_log.json 기록

### T2. 파싱
스킬: `.claude/skills/html-parser/scripts/parse.py`
```
python .claude/skills/html-parser/scripts/parse.py \
  --unvcd {unvCd} \
  --univ {대학명} \
  --html output/raw_html/{unvCd}.html \
  --output output/parsed/{unvCd}.json \
  --errors output/logs/error_log.json
```
**성공 기준**: 4시트 모두 최소 1행, PK 컬럼 비어있지 않음
**실패 시**: 부분 저장 + 빈 시트는 빈 리스트로 처리

### T3. 룰 기반 매핑
스킬: `.claude/skills/rule-mapper/scripts/map_columns.py`
```
python .claude/skills/rule-mapper/scripts/map_columns.py \
  --unvcd {unvCd} \
  --parsed output/parsed/{unvCd}.json \
  --schema input/schema_v3.yaml \
  --output output/mapped/{unvCd}.json
```
**성공 기준**: 행 수 손실 없음, 매핑률 ≥ 60%
**실패 시**: unmapped를 T4로 전달

### T4. LLM 정규화

#### T4a. 결과 시트 (normalizer-result 서브에이전트)
트리거: `output/mapped/{unvCd}.json`의 unmapped가 비어있지 않은 경우
```
# 서브에이전트 호출 방법:
# .claude/agents/normalizer-result/AGENT.md를 시스템 프롬프트로,
# 다음을 사용자 메시지로 전달:
# "대학 {unvCd} ({대학명})의 결과 시트 정규화를 수행하세요.
#  입력: output/mapped/{unvCd}.json
#  출력: output/normalized/{unvCd}.json (result 시트 부분)"
```
처리: Haiku 1차 → confidence < 0.7인 셀만 Sonnet 재분류

#### T4b. 평가기준 시트 (normalizer-eval 서브에이전트)
```
# .claude/agents/normalizer-eval/AGENT.md를 시스템 프롬프트로,
# 다음을 사용자 메시지로 전달:
# "대학 {unvCd} ({대학명})의 평가기준 시트 정규화를 수행하세요.
#  입력: output/mapped/{unvCd}.json
#  출력: output/normalized/{unvCd}.json (eval 시트 부분)"
```
처리: Sonnet 직접 → JSON 파싱 실패 시 Opus 에스컬레이션

**T4 완료 후**: normalized 파일이 없으면 mapped 파일을 그대로 복사

#### T4c. 신규 컬럼 후보 (모든 대학 완료 후 1회)
```
# 모든 normalized/{unvCd}.json의 raw_text 집계 후
# Opus 4.7로 반복 패턴 분석
# 출력: output/logs/new_columns_proposals.json
```

### T5. 엑셀 빌드
스킬: `.claude/skills/xlsx-builder/scripts/build.py`
```
python .claude/skills/xlsx-builder/scripts/build.py \
  --year {year} \
  --normalized-dir output/normalized \
  --per-univ-dir output/per_university \
  --output output/adiga_{year}.xlsx \
  --schema input/schema_v3.yaml \
  --errors output/logs/error_log.json \
  --new-columns output/logs/new_columns_proposals.json
```
**성공 기준**: 4시트 존재, susi_result 헤더가 골든셋과 동일
**실패 시**: 즉시 종료 (치명적)

### T6. 평가
스킬: `.claude/skills/evaluator/scripts/evaluate.py`
```
python .claude/skills/evaluator/scripts/evaluate.py \
  --golden input/2025_어디가입결_통합본.xlsx \
  --predicted output/adiga_{year}.xlsx \
  --out output/evaluation_report.xlsx
```
**실패 시**: 스킵 + 로그 (선택적 단계)

### T7. 리포트
스킬: `.claude/skills/reporter/scripts/report.py`
```
python .claude/skills/reporter/scripts/report.py \
  --normalized-dir output/normalized \
  --schema input/schema_v3.yaml \
  --eval-report output/evaluation_report.xlsx \
  --errors output/logs/error_log.json \
  --new-columns output/logs/new_columns_proposals.json \
  --out output/validation_report.md
```
**실패 시**: 스킵 + 로그

---

## 4. 상태 관리

`/output/run_state.json` 형식:
```json
{
  "0000063": {
    "status": "done",
    "last_updated": "2026-05-19T10:00:00",
    "errors": []
  }
}
```

상태값: `pending` → `fetching` → `fetched` → `parsing` → `parsed` → `mapping` → `mapped` → `normalizing` → `normalized` → `exported` → `done`
오류 상태: `error_fetch` / `error_parse` / `error_partial`

**재실행 규칙**:
- `status == "done"` → `--force` 없으면 스킵
- `status == "error_fetch"` → T1부터 재시도
- `status == "error_partial"` → T4부터 재시도

---

## 5. 스킬 vs 서브에이전트

| 구분 | 대상 | 특징 |
|---|---|---|
| 스킬 (Python 스크립트) | T1, T2, T3, T5, T6, T7 | 결정론적, bash로 실행 |
| 서브에이전트 (LLM) | T4a, T4b, T4c | 판단 필요, 파일 경로로 입력·출력 |

서브에이전트 호출 시:
- AGENT.md를 시스템 프롬프트로 전달
- 입력 파일 경로를 메시지에 명시
- 출력 파일 경로를 메시지에 명시
- 완료 후 파일 존재 여부로 성공 판정

---

## 6. 에러 처리 정책

| 정책 | 적용 단계 |
|---|---|
| 자동 재시도 (최대 3회) | T1 네트워크 오류 |
| Haiku → Sonnet 에스컬레이션 | T4a confidence < 0.7 |
| Sonnet → Opus 에스컬레이션 | T4b JSON 파싱 실패 |
| 스킵 + 로그 | T4c, T6, T7 |
| 즉시 종료 | T0 입력 검증 실패, T5 빌드 실패 |
| 부분 저장 | T2 시트 단위 |

LLM 호출 비용 통제:
- 한 대학당 LLM 호출 최대 5회 (초과 시 경고)
- raw_text 길이 상한 8000자 (초과 시 truncate)

---

## 7. 로깅 규약

- 모든 단계 시작·종료: 콘솔 출력 (`[T1 크롤링] 시작: 8개 대학`)
- 에러: `/output/logs/error_log.json` (JSON 배열 append)
- 진행 상태: `/output/run_state.json` (단계별 즉시 갱신)

에러 로그 항목 형식:
```json
{
  "unvCd": "0000063",
  "university": "가천대학교",
  "stage": "T1",
  "error": "ConnectionError: ...",
  "timestamp": "2026-05-19T10:00:00"
}
```

---

## 8. 완료 판정 (DoD)

- 8개 타겟 대학 4시트 모두 추출
- susi_result PK 매칭률 ≥ 85%
- susi_result 셀 일치율 ≥ 90% (매칭 행 한정)
- 평가기준 시트 seed 컬럼 평균 채움률 ≥ 50%
- error 시트에 정당한 사유 외 실패 없음
