# adiga 입시 데이터 수집 에이전트 — 구현 계획서

> **목적**: Claude Code가 이 문서를 참조하여 에이전트를 구현한다.
> **버전**: v1.0 (2026-05-18)
> **상태**: 구현 대기

---

## 1. 작업 컨텍스트

### 1.1 배경

ViveOn은 한국 대학 입시 준비 서비스를 운영한다. 매년 adiga(대입정보포털)에 공개되는 200+개 대학의 평가기준 및 입시결과 데이터를 수집해 내부 서비스에 활용해 왔으나, 지금까지는 수작업이었다. 본 에이전트는 이 수집·정규화 작업을 자동화한다.

### 1.2 목적

adiga의 모든 대학에 대해 다음 4종 데이터를 학년도 단위로 자동 수집·정규화·엑셀화한다.

- 수시 평가기준
- 수시 입시결과
- 정시 평가기준
- 정시 입시결과

### 1.3 범위

#### In Scope
- adiga 등록 일반대학 전체 (전문대 제외)
- 학년도별 파라미터화된 수집
- 부분 갱신 모드 (특정 대학만 재수집)
- 작년 골든셋 대비 정확도 자동 측정 (수시 입시결과 한정)

#### Out of Scope
- 데이터 시각화·분석 (수집과 정규화까지만)
- 실시간 모니터링 (1회성 배치 실행)
- 사용자 인터페이스 (CLI만)
- KAIST·과학기술원 (adiga에 평가기준 미등록)

### 1.4 입력

| 항목 | 형식 | 필수 | 설명 |
|---|---|---|---|
| 학년도 | int (예: 2027) | ✓ | URL의 `searchSyr` 파라미터. 2026학년도 자료는 `2027` 사용 |
| 모드 | enum (`full` / `partial`) | ✓ | 전체 수집 또는 부분 갱신 |
| unvCd 리스트 | list[str] | partial 시 | 부분 갱신 대상 대학 코드 (예: `["0000063","0000019"]`) |
| 골든셋 파일 | path | ✓ | 평가용 기준 데이터 (`2025_어디가입결_통합본.xlsx`) |
| 스키마 파일 | path | ✓ | 컬럼 정의 (`schema_v3.yaml`) |

### 1.5 출력

| 산출물 | 경로 | 형식 |
|---|---|---|
| 통합 워크북 | `/output/adiga_{year}.xlsx` | 4시트 + error + summary + new_columns 시트 |
| 대학별 워크북 | `/output/per_university/{unvCd}.xlsx` | 4시트 |
| 평가 리포트 | `/output/evaluation_report.xlsx` | susi_result 한정 골든셋 비교 |
| 검증 리포트 | `/output/validation_report.md` | 충진율, 신규 칼럼 후보 요약 |
| 에러 로그 | `/output/logs/error_log.json` | 3회 재시도 실패 대학 |
| 신규 칼럼 후보 | `/output/logs/new_columns_proposals.json` | LLM이 발견한 정형 못 한 패턴 |

### 1.6 제약조건

- 실행 환경: 로컬 PC + Python 3.11+
- 네트워크: adiga.kr 접근 가능해야 함 (사내 방화벽 확인 필요)
- adiga 페이지는 정적 HTML (Playwright 불필요, requests+BS4로 충분)
- 한 대학 페이지에 4종 데이터 모두 들어있음 (URL 1개로 충분)
- 학년도 매핑: `searchSyr=2027` → 2026학년도 평가기준 + 2025학년도 결과 표시
- LLM 호출 비용 최소화: 룰 기반 처리를 우선, LLM은 미매핑 항목·평가기준 정규화에만

### 1.7 용어 정의

| 용어 | 정의 |
|---|---|
| 대학 | adiga에 등록된 4년제 일반대학 (unvCd로 식별) |
| 전형 | 모집 전형 단위 (예: 학생부우수자 전형, 가천바람개비 전형) |
| 모집단위 | 학과 또는 학부 단위 (예: 경영학과, 의예과, AI인문대학) |
| PK | (대학, 전형, 모집단위) 3-튜플. 4개 시트 공통 키 |
| 평가기준 | 전형방법·서류평가·면접·교과 반영 방식 등 합격 조건 |
| 입시결과 | 모집인원·경쟁률·충원합격순위·등급컷 등 합격 통계 |
| 학생부등급 | 학생부 교과 성적 등급 (1~9등급, 낮을수록 우수) |
| 대학별환산 | 대학 고유 환산 공식으로 산출한 점수 |
| 컷 (cut) | 합격자의 상위 N% 지점 점수 (70컷 = 상위 70% 지점) |
| 골든셋 | 작년에 수작업으로 검증한 정답 데이터 (`2025_어디가입결_통합본.xlsx`) |
| raw_text | 정형 컬럼에 매핑되지 않은 모든 원본 텍스트를 보관하는 fallback 컬럼 |

---

## 2. 워크플로우

### 2.1 전체 흐름

```
[T0 준비]
   │  파라미터 검증, 골든셋·스키마 로드, 대학 리스트 결정
   ▼
[T1 크롤링] ── 결정론적 (스크립트)
   │  대학별 페이지 fetch + raw HTML 저장
   │  3회 재시도, 실패 시 error 로그
   ▼
[T2 파싱] ── 결정론적 (스크립트)
   │  HTML <table> → 4시트 raw DataFrame
   │  PK 단위 행 정규화
   ▼
[T3 룰 기반 매핑] ── 결정론적 (스크립트)
   │  매핑 사전으로 컬럼 자동 채움
   │  매핑 못 한 셀은 unmapped로 표시
   ▼
[T4 LLM 정규화] ── 판단 (서브에이전트)
   │  T4a: 결과 시트 미매핑 항목 분류 (Haiku 우선)
   │  T4b: 평가기준 시트 정규화 (Sonnet 위주)
   │  T4c: 신규 칼럼 후보 제안 (Opus, 1회)
   ▼
[T5 엑셀 빌드] ── 결정론적 (스크립트)
   │  4시트 + 부가 시트 통합 워크북 + 대학별 워크북
   ▼
[T6 평가] ── 결정론적 (스크립트)
   │  susi_result만 골든셋과 비교
   │  PK 매칭률, 셀 일치율, 컬럼별 정확도
   ▼
[T7 리포트] ── 결정론적 + LLM 요약
      충진율·신규 칼럼 후보·이슈 요약
```

### 2.2 단계별 명세

#### T0. 준비

- **수행 주체**: 메인 에이전트 (CLAUDE.md)
- **입력**: CLI 인자 (year, mode, unvCd 리스트)
- **처리**:
  1. CLI 인자 파싱 및 검증
  2. 골든셋 엑셀 로드 (`2025_어디가입결_통합본.xlsx`)
  3. 스키마 YAML 로드 (`schema_v3.yaml`)
  4. 대학 마스터 리스트 결정 (mode에 따라)
  5. 출력 디렉토리 생성 (`/output/`, `/output/per_university/`, `/output/logs/`)
- **성공 기준**:
  - 골든셋 파일 존재 및 21,000+ 행 로드
  - 스키마 YAML 파싱 성공 및 4시트 정의 확인
  - 대학 리스트 비어있지 않음
- **검증 방법**: 스키마 검증 (스키마 파일 필수 키 존재 확인)
- **실패 시**: 즉시 종료 + 콘솔 에러 메시지

#### T1. 크롤링

- **수행 주체**: `adiga-crawler` 스킬
- **입력**: 대학 리스트, 학년도
- **처리**:
  1. 각 대학에 대해 URL 구성 (`https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do?menuId=PCUVTINF2000&unvCd={code}&searchSyr={year}`)
  2. requests로 GET (User-Agent 설정)
  3. raw HTML을 `/output/raw_html/{unvCd}.html`에 저장
  4. 동시 워커 3개 (adiga 서버 부하 고려)
- **성공 기준**:
  - HTTP 200 응답
  - HTML 크기 10KB 이상 (빈 페이지 방지)
  - `<title>` 태그에 대학명 포함
- **검증 방법**: 규칙 기반 (응답 크기·필수 마커 존재)
- **실패 시**:
  - 자동 재시도: 최대 3회, 지수 백오프 (2s, 4s, 8s)
  - 3회 모두 실패 → 스킵 + 로그 (`error_log.json`에 unvCd, 사유, timestamp 기록)
  - 다른 대학은 계속 진행

#### T2. 파싱

- **수행 주체**: `html-parser` 스킬
- **입력**: `/output/raw_html/{unvCd}.html`
- **처리**:
  1. BeautifulSoup으로 HTML 파싱
  2. 사이트 탭(Ⅰ.공통, Ⅱ.학생부종합, Ⅲ.학생부교과, Ⅳ.수능위주) 영역 식별
  3. 각 탭 안의 `<table>` 추출
  4. 표마다 4시트 중 어디에 속하는지 분류:
     - "Q 1. 2026학년도 전형별 주요사항" 영역 → 평가기준 (susi_eval / jeongsi_eval)
     - "Q 2. 2025학년도 전형 결과" 영역 → 입시결과 (susi_result / jeongsi_result)
     - 탭 Ⅱ·Ⅲ → 수시, 탭 Ⅳ → 정시
  5. PK 단위 행 변환 (대학 × 전형 × 모집단위)
  6. 4시트별 raw DataFrame 생성
  7. `/output/parsed/{unvCd}.json` 저장
- **성공 기준**:
  - 4시트 모두 최소 1행 이상 (평가기준은 전 모집단위 일괄일 수도 있어 1행 OK)
  - PK 컬럼 (대학·전형·모집단위) 비어있지 않음
- **검증 방법**: 스키마 검증 (PK 컬럼 존재 + 빈 값 0건)
- **실패 시**:
  - 자동 재시도 없음 (결정론적 처리)
  - 시트별 결과를 부분적으로라도 저장
  - 빈 시트는 빈 DataFrame으로 처리 (다음 단계가 알아서 대응)
  - error 로그에 "어느 시트가 비었는지" 기록

#### T3. 룰 기반 매핑

- **수행 주체**: `rule-mapper` 스킬
- **입력**: `/output/parsed/{unvCd}.json`, `schema_v3.yaml`
- **처리**:
  1. 각 시트의 컬럼을 schema 컬럼명으로 매핑
  2. 표기 정규화 사전 적용:
     - "전 과목" / "전체" → "전교과"
     - "1단계 100%(3배수)" → 1단계_배수=3, 1단계_요소비율="100"
     - "있음", "적용", "○" → True (boolean 컬럼)
  3. 매핑 못 한 셀은 unmapped 리스트에 보관
  4. 데이터공개수준 자동 판정 (전 컬럼 채움률 기준)
  5. `/output/mapped/{unvCd}.json` 저장 (mapped + unmapped)
- **성공 기준**:
  - 시트별 PK 행 손실 없음 (T2 → T3에서 행 수 동일)
  - 정형 컬럼 매핑률 ≥ 60% (전체 평균)
- **검증 방법**: 규칙 기반 (행 수 비교, 매핑률 임계치)
- **실패 시**:
  - 매핑률 < 60%인 시트는 unmapped를 그대로 LLM 단계로 넘김
  - 행 수 손실 발생 시 error 로그 + 사람 검토 플래그

#### T4. LLM 정규화

- **수행 주체**: 서브에이전트 (시트 종류별로 다른 에이전트)
- **트리거 조건**: T3 unmapped 리스트가 비어있지 않음

##### T4a. 결과 시트 정규화 (`normalizer-result`)

- **대상**: susi_result, jeongsi_result
- **입력**: unmapped 셀들 (대학·전형·모집단위 + raw_text)
- **처리**:
  1. 1차: Haiku 4.5로 배치 분류 (대학당 1회)
  2. confidence 점수 동봉 요청
  3. confidence < 0.7인 셀만 Sonnet 4.6로 재분류
- **출력**: 컬럼별 값 할당 결과
- **성공 기준**:
  - 모든 unmapped 셀에 대해 분류 결과 또는 "분류 불가" 라벨
  - confidence ≥ 0.5인 결과만 채택
- **검증 방법**: LLM 자기 검증 (confidence 점수)
- **실패 시**:
  - LLM 응답 파싱 실패 → 자동 재시도 2회
  - 재시도 실패 → 해당 셀은 raw_text에 그대로 보관

##### T4b. 평가기준 시트 정규화 (`normalizer-eval`)

- **대상**: susi_eval, jeongsi_eval
- **입력**: 평가기준 raw_text (대부분 평가기준 시트의 데이터는 비정형 텍스트)
- **처리**:
  1. Sonnet 4.6로 직접 처리 (Haiku로는 어려운 도메인)
  2. 시트별 seed_columns 안내 + 표 원본 텍스트 입력
  3. JSON 응답 요청 (컬럼명 → 값)
  4. 분류 코드(enum) 일치 여부 검증
- **출력**: 정형 컬럼 값 + 잔여 raw_text
- **성공 기준**:
  - seed_columns 중 최소 50% 채움
  - enum 컬럼 값은 분류 코드에 포함되거나 명시적 "기타"
- **검증 방법**: 스키마 검증 (enum 값 일치 확인) + LLM 자기 검증 (confidence)
- **실패 시**:
  - JSON 파싱 실패 → Opus 4.7로 에스컬레이션 (1회)
  - 그래도 실패 → seed_columns는 비우고 raw_text에 원본 텍스트 전부 보관

##### T4c. 신규 칼럼 후보 제안 (`schema-proposer`)

- **트리거 조건**: 모든 대학의 T4a/T4b 완료 후 1회만
- **수행 주체**: 메인 에이전트가 Opus 4.7 직접 호출
- **입력**: 모든 시트의 raw_text를 모아 클러스터링한 결과
- **처리**:
  1. 시트별 raw_text 50개 이상 누적된 경우만 분석
  2. 반복 패턴 식별 (예: "학폭 감점 -X점"이 여러 대학에서 등장)
  3. 신규 컬럼 후보 JSON 생성 (이름, 예상 타입, 등장 빈도, 샘플 값)
- **출력**: `/output/logs/new_columns_proposals.json`
- **성공 기준**: 최소 1개 이상 후보 제안 (없으면 "추가 필요 없음" 명시)
- **검증 방법**: 사람 검토 (PM이 schema_v3.yaml 업데이트 여부 결정)
- **실패 시**: 스킵 + 로그 (선택적 단계, 전체 흐름에 영향 없음)

#### T5. 엑셀 빌드

- **수행 주체**: `xlsx-builder` 스킬
- **입력**: `/output/normalized/{unvCd}.json` (모든 대학)
- **처리**:
  1. 대학별 워크북 4시트 생성 → `/output/per_university/{unvCd}.xlsx`
  2. 통합 워크북 생성:
     - 시트 1~4: susi_result, susi_eval, jeongsi_result, jeongsi_eval
     - 시트 5: error (실패 대학 목록)
     - 시트 6: summary (충진율 등)
     - 시트 7: new_columns (T4c 결과)
  3. 골든셋과 동일한 2단 헤더 양식 적용 (susi_result 시트)
  4. 컬럼 너비·서식 적용
- **성공 기준**:
  - 모든 워크북에 4시트 존재 (빈 시트라도)
  - susi_result 시트의 헤더가 골든셋과 동일 (29컬럼, 그룹 헤더 N1:T1, U1:AC1 병합)
- **검증 방법**: 스키마 검증 (헤더 일치 + 시트 수)
- **실패 시**: 자동 재시도 없음, 빌드 에러는 치명적 → 즉시 종료

#### T6. 평가

- **수행 주체**: `evaluator` 스킬
- **트리거 조건**: T5 완료 + 골든셋 파일 존재
- **입력**: 골든셋 엑셀, T5 출력 엑셀
- **처리**:
  1. 두 엑셀의 susi_result 시트 로드
  2. 8개 타겟 대학으로 필터링 (가천·서울·제주·연세·고려·부산·경북·남서울)
  3. PK 정규화 후 매칭
  4. 메트릭 계산: PK 매칭률, 셀 일치율, 컬럼별 정확도, 잉여행률
  5. 리포트 엑셀 생성 (6시트: summary, by_university, by_column, missing_rows, extra_rows, mismatched_cells)
- **출력**: `/output/evaluation_report.xlsx`
- **성공 기준**:
  - 리포트 6시트 모두 생성
  - 메트릭 모두 0 이상 (NaN 없음)
- **검증 방법**: 규칙 기반 (시트 수, 메트릭 범위)
- **실패 시**: 스킵 + 로그 (평가는 선택적, 전체 흐름 영향 없음)

#### T7. 리포트

- **수행 주체**: 메인 에이전트 + LLM 요약 (Haiku)
- **입력**: T5, T6 출력 + error 로그 + new_columns 후보
- **처리**:
  1. 충진율 계산: 시트·컬럼별 채움 비율
  2. 작년 골든셋 대비 변화 요약 (충진율 증감, 신규 컬럼 후보 등)
  3. Haiku로 자연어 요약 생성
  4. Markdown 리포트 작성
- **출력**: `/output/validation_report.md`
- **성공 기준**: 리포트 파일 생성됨, 모든 섹션 채워짐
- **검증 방법**: LLM 자기 검증 (요약이 모든 섹션을 다루는지)
- **실패 시**: 스킵 + 로그

### 2.3 상태 전이도

```
대학별 상태 관리:
  pending → fetching → fetched → parsing → parsed
                          ↓ (3회 실패)
                       error

  parsed → mapping → mapped → normalizing → normalized
                                  ↓ (LLM 실패)
                               error_partial (raw_text만 보관)

  normalized → exported → evaluated (susi_result만) → done
```

전체 상태 전이 메타 정보는 `/output/run_state.json`에 기록한다. 재실행 시 이 파일을 참고해 완료된 대학은 스킵 (단, `--force` 옵션 시 무시).

---

## 3. 검증 및 실패 처리 종합

### 3.1 단계별 검증 매트릭스

| 단계 | 검증 유형 | 성공 기준 | 실패 처리 |
|---|---|---|---|
| T0 준비 | 스키마 검증 | 파일 존재 + 필수 키 | 즉시 종료 |
| T1 크롤링 | 규칙 기반 | HTTP 200 + HTML 크기 ≥ 10KB | 자동 재시도(3회) → 스킵+로그 |
| T2 파싱 | 스키마 검증 | PK 컬럼 비어있지 않음 | 시트 단위 부분 저장 |
| T3 룰 매핑 | 규칙 기반 | 매핑률 ≥ 60% | unmapped를 T4로 |
| T4a 결과 LLM | LLM 자기 검증 | confidence ≥ 0.5 | Sonnet 에스컬레이션 → raw_text 보관 |
| T4b 평가 LLM | 스키마 + LLM 자기 검증 | seed 50% 채움 + enum 일치 | Opus 에스컬레이션 → raw_text 보관 |
| T4c 신규 칼럼 | 사람 검토 | 후보 JSON 생성됨 | 스킵+로그 |
| T5 엑셀 | 스키마 검증 | 4시트 + 헤더 일치 | 즉시 종료 |
| T6 평가 | 규칙 기반 | 6시트 생성됨 | 스킵+로그 |
| T7 리포트 | LLM 자기 검증 | 모든 섹션 채움 | 스킵+로그 |

### 3.2 실패 처리 정책

| 정책 | 적용 단계 |
|---|---|
| **자동 재시도** | T1 (네트워크 일시 실패), T4 (LLM 응답 파싱 실패) |
| **에스컬레이션** | T4a (Haiku → Sonnet), T4b (Sonnet → Opus) |
| **스킵 + 로그** | T4c, T6, T7 (선택적 단계) |
| **즉시 종료** | T0 (입력 검증), T5 (출력 빌드 실패) |
| **부분 저장** | T2 (시트 단위 부분 결과 보존) |

### 3.3 LLM 호출 비용 통제

| 룰 | 적용 위치 |
|---|---|
| Haiku 1차 → confidence < 0.7만 Sonnet 재시도 | T4a |
| 평가기준 시트는 Sonnet 직접 (Haiku 스킵) | T4b |
| Opus는 schema-proposer 단일 호출만 | T4c |
| 한 대학의 LLM 호출 총 횟수 상한: 5회 (초과 시 경고) | T4a + T4b 합산 |
| 시트별 raw_text 길이 상한: 8000자 (초과 시 truncate + 경고) | T4b 입력 |

---

## 4. 구현 스펙

### 4.1 폴더 구조

```
/project-root
├── CLAUDE.md                         # 메인 에이전트 지침
├── /.claude
│   ├── /skills
│   │   ├── /adiga-crawler
│   │   │   ├── SKILL.md
│   │   │   ├── /scripts
│   │   │   │   └── crawl.py          # 페이지 fetch + 재시도
│   │   │   └── /references
│   │   │       └── adiga-url-patterns.md
│   │   ├── /html-parser
│   │   │   ├── SKILL.md
│   │   │   ├── /scripts
│   │   │   │   └── parse.py          # HTML → DataFrame
│   │   │   └── /references
│   │   │       └── adiga-html-structure.md
│   │   ├── /rule-mapper
│   │   │   ├── SKILL.md
│   │   │   ├── /scripts
│   │   │   │   └── map_columns.py    # 룰 + 매핑 사전
│   │   │   └── /references
│   │   │       └── normalization-dictionary.md
│   │   ├── /xlsx-builder
│   │   │   ├── SKILL.md
│   │   │   └── /scripts
│   │   │       └── build.py          # 4시트 엑셀 빌드
│   │   ├── /evaluator
│   │   │   ├── SKILL.md
│   │   │   └── /scripts
│   │   │       └── evaluate.py       # 골든셋 비교
│   │   └── /reporter
│   │       ├── SKILL.md
│   │       └── /scripts
│   │           └── report.py         # 충진율, 검증 리포트
│   └── /agents
│       ├── /normalizer-result
│       │   └── AGENT.md              # 결과 시트 LLM 정규화
│       └── /normalizer-eval
│           └── AGENT.md              # 평가기준 시트 LLM 정규화
├── /input
│   ├── 2025_어디가입결_통합본.xlsx    # 골든셋
│   └── schema_v3.yaml                # 컬럼 스키마
├── /output
│   ├── /raw_html/{unvCd}.html
│   ├── /parsed/{unvCd}.json
│   ├── /mapped/{unvCd}.json
│   ├── /normalized/{unvCd}.json
│   ├── /per_university/{unvCd}.xlsx
│   ├── adiga_{year}.xlsx
│   ├── evaluation_report.xlsx
│   ├── validation_report.md
│   ├── run_state.json
│   └── /logs
│       ├── error_log.json
│       └── new_columns_proposals.json
└── /docs
    ├── agent_design.md                # 본 문서
    └── references/                    # 8개 대학 분석 노트 등
```

### 4.2 CLAUDE.md 핵심 섹션 (메인 에이전트 지침)

CLAUDE.md는 다음 섹션을 가진다:

1. **역할 정의**
   - 본 에이전트는 adiga 입시 데이터 수집 워크플로우의 오케스트레이터
   - 의사결정만 담당, 실제 처리는 스킬과 서브에이전트에 위임

2. **입력 인터페이스**
   - CLI 인자 파싱 규약
   - `--year`, `--mode {full,partial}`, `--unvcd ...`, `--force` 등

3. **워크플로우 실행 순서**
   - T0 → T1 → T2 → T3 → T4 → T5 → T6 → T7
   - 각 단계의 트리거 조건, 의존성, 호출 대상

4. **상태 관리**
   - `/output/run_state.json` 읽기/쓰기 규약
   - 재실행 시 완료된 대학 스킵 룰

5. **스킬·서브에이전트 호출 패턴**
   - 스킬: 결정론적 처리, 입력 → 출력만
   - 서브에이전트: LLM 판단이 필요한 경우만

6. **에러 처리 정책**
   - 각 단계의 실패 처리 (재시도 / 에스컬레이션 / 스킵 / 종료)

7. **로깅 규약**
   - 모든 단계 시작·종료를 콘솔에 출력
   - 에러는 `/output/logs/`에 JSON으로

8. **참조 문서**
   - schema_v3.yaml 위치
   - 본 설계서 위치 (`/docs/agent_design.md`)

### 4.3 에이전트 구조

#### 선택: 서브에이전트 분리

**이유**:
- 평가기준 시트 정규화(T4b)는 입시 도메인 지식이 많이 필요 → AGENT.md에 도메인 지식 풍부히 담음
- 결과 시트 정규화(T4a)는 비교적 룰에 가까움 → 다른 도메인 지식 필요
- 메인 에이전트가 항상 두 도메인 지식을 다 들고 있으면 컨텍스트 비효율

**구조**:
- 메인 (CLAUDE.md): 오케스트레이션, 워크플로우 진행, 상태 관리
- 서브 1 (normalizer-result): 결과 시트 LLM 정규화 전용
- 서브 2 (normalizer-eval): 평가기준 시트 LLM 정규화 전용
- 서브 간 직접 호출 금지, 항상 메인 통해 조율

### 4.4 스킬 카탈로그

| 스킬명 | 역할 | 트리거 조건 | 입력 | 출력 |
|---|---|---|---|---|
| `adiga-crawler` | 페이지 fetch + 재시도 | T1 단계 | unvCd, year | `/output/raw_html/{unvCd}.html` |
| `html-parser` | HTML → 4시트 raw DataFrame | T2 단계 | raw_html | `/output/parsed/{unvCd}.json` |
| `rule-mapper` | 룰 기반 컬럼 매핑 | T3 단계 | parsed.json + schema.yaml | `/output/mapped/{unvCd}.json` |
| `xlsx-builder` | 4시트 엑셀 빌드 | T5 단계 | normalized.json (전체) | 통합 + 대학별 워크북 |
| `evaluator` | 골든셋 비교 | T6 단계 (susi_result 한정) | 골든셋 + predicted | `/output/evaluation_report.xlsx` |
| `reporter` | 검증 리포트 생성 | T7 단계 | 전체 산출물 | `/output/validation_report.md` |

각 스킬의 SKILL.md에는 다음을 명시:
- 트리거 키워드 (예: "adiga 페이지를 받아야 한다")
- 입력·출력 스키마
- 의존성 (requests, beautifulsoup4 등)
- 사용 예시

### 4.5 서브에이전트 카탈로그

#### normalizer-result (AGENT.md)

| 항목 | 내용 |
|---|---|
| 역할 | 입시결과 시트(susi_result, jeongsi_result)의 unmapped 셀을 LLM으로 분류 |
| 트리거 | 메인 에이전트가 T4a 단계에서 호출 |
| 입력 | `/output/mapped/{unvCd}.json` 중 unmapped 부분 |
| 처리 | 1차 Haiku → confidence < 0.7 셀만 Sonnet |
| 출력 | `/output/normalized/{unvCd}.json`의 result 시트 부분 |
| 도메인 지식 | 입시결과 컬럼 정의, 학생부등급 vs 대학별환산 차이, 컷(70/90 등) 의미 |
| 참조 스킬 | 없음 (LLM 호출만) |
| 데이터 전달 | 파일 경로로 전달 (`/output/mapped/{unvCd}.json`) |

#### normalizer-eval (AGENT.md)

| 항목 | 내용 |
|---|---|
| 역할 | 평가기준 시트(susi_eval, jeongsi_eval) raw_text를 LLM으로 정형화 |
| 트리거 | 메인 에이전트가 T4b 단계에서 호출 |
| 입력 | `/output/mapped/{unvCd}.json` 중 eval 시트 부분 |
| 처리 | Sonnet 직접 → JSON 파싱 실패 시 Opus 에스컬레이션 |
| 출력 | `/output/normalized/{unvCd}.json`의 eval 시트 부분 |
| 도메인 지식 | 평가요소 표기방식 다양성(비율/등급/점수/정성), 면접 유형, 수능최저 패턴, 8개 대학 사전 분석 결과 |
| 참조 스킬 | 없음 (LLM 호출만) |
| 데이터 전달 | 파일 경로로 전달 |

### 4.6 판단 vs 코드 역할 분리

| 에이전트가 직접 판단 | 스크립트(스킬)가 처리 |
|---|---|
| 미매핑 raw_text → 어느 컬럼? (T4a) | HTTP fetch, HTML 파싱 (T1, T2) |
| 평가기준 텍스트 → 정형 컬럼 분해 (T4b) | 매핑 사전 적용 (T3) |
| 신규 칼럼 후보 발견 (T4c) | 엑셀 빌드, 헤더 병합 (T5) |
| 충진율 변화 요약 (T7) | 충진율 계산 (T7 전반부) |
| | PK 매칭, 셀 일치 판정 (T6) |
| | 재시도, 백오프 (T1) |

원칙: **결정 가능한 것은 모두 코드로, 판단·생성·해석이 필요한 것만 LLM으로.**

### 4.7 데이터 전달 패턴

| 데이터 | 방식 | 경로/규약 |
|---|---|---|
| 대학 리스트 | 파일 (CSV) | `/input/universities.csv` |
| raw HTML | 파일 | `/output/raw_html/{unvCd}.html` |
| 파싱 결과 | 파일 (JSON) | `/output/parsed/{unvCd}.json` |
| 매핑 결과 | 파일 (JSON) | `/output/mapped/{unvCd}.json` |
| 정규화 결과 | 파일 (JSON) | `/output/normalized/{unvCd}.json` |
| 진행 상태 | 파일 (JSON) | `/output/run_state.json` |
| LLM 입력 데이터 | 프롬프트 인라인 | unmapped 셀 / raw_text 직접 삽입 |
| 스킬 호출 결과 | 표준 출력 + 파일 | stdout 요약 + 파일 산출물 |

규약:
- 중간 산출물은 항상 파일로 (재실행·디버그 가능)
- 프롬프트 인라인은 5KB 미만일 때만
- JSON 인코딩은 UTF-8, ensure_ascii=False

### 4.8 산출물 파일 형식

| 파일 | 형식 | 스키마 |
|---|---|---|
| `parsed/{unvCd}.json` | JSON | `{sheet_name: [row1, row2, ...]}` |
| `mapped/{unvCd}.json` | JSON | `{sheet_name: {"mapped": [...], "unmapped": [...]}}` |
| `normalized/{unvCd}.json` | JSON | `{sheet_name: [completed_row1, ...]}` |
| `adiga_{year}.xlsx` | XLSX | 7시트, 골든셋 양식 |
| `per_university/{unvCd}.xlsx` | XLSX | 4시트 |
| `evaluation_report.xlsx` | XLSX | 6시트 (summary, by_university, by_column, missing, extra, mismatched) |
| `validation_report.md` | Markdown | 섹션: 요약·충진율·신규컬럼·이슈 |
| `error_log.json` | JSON | `[{unvCd, university, stage, error, timestamp}, ...]` |
| `new_columns_proposals.json` | JSON | `[{sheet, candidate_name, type, frequency, samples}, ...]` |
| `run_state.json` | JSON | `{unvCd: {status, last_updated, errors}}` |

### 4.9 schema_v3.yaml 구조

```yaml
version: 3
primary_key:
  required: [대학, 전형, 모집단위]
  optional_disambiguator: [캠퍼스, 군]
classification_codes:
  전형구분_대분류: [...]      # 6종
  평가표기방식: [...]         # 7종
  면접유형: [...]            # 6종
  수능최저유무: [...]         # 3종
  수능_활용지표: [...]        # 4종
  데이터공개수준: [...]       # 4종
sheets:
  susi_result:
    column_groups: [...]
    columns: [...]            # 28개
  susi_eval:
    seed_columns: [...]       # 30개
    extension_columns: [...]  # 6개
    fallback: [raw_text]
  jeongsi_result: ...
  jeongsi_eval: ...
```

상세 정의는 별도 파일 `/input/schema_v3.yaml`. 본 설계서에서는 구조만 참조.

---

## 5. 참고 자료

### 5.1 기존 코드 (구현 참고용, 그대로 사용 금지)

다음 파일들은 PoC 단계에서 만들어진 참고 코드다. Claude Code는 새로 작성하되 아래 패턴을 참고할 수 있다.

| 파일 | 참고 가치 |
|---|---|
| `crawler.py` (PoC) | adiga URL 패턴, HTML 표 파싱 로직, 골든셋 양식 변환 |
| `evaluate.py` (PoC) | PK 정규화 규칙, 셀 일치 판정 규칙, 리포트 시트 구성 |
| `schema_v3.yaml` (확정) | **그대로 사용 가능** (구현 시 입력 파일) |

### 5.2 도메인 지식 (8개 대학 사전 분석)

대학별 데이터 다양성 분석 결과는 별도 노트로 보관:
- `/docs/references/00_통합_발견.md`
- `/docs/references/04_고려대_분석.md`
- `/docs/references/05_부산대_분석.md`
- `/docs/references/06_경북대_분석.md`
- `/docs/references/07_남서울대_분석.md`

normalizer-eval 서브에이전트의 AGENT.md에서 이 노트들을 참조하도록 한다.

### 5.3 외부 자료

- adiga 메인: https://www.adiga.kr/man/inf/mainView.do?menuId=PCMANINF1000
- adiga 대학 상세 URL 패턴: `https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do?menuId=PCUVTINF2000&unvCd={code}&searchSyr={year}`
- 8개 타겟 대학 unvCd:
  - 가천대 `0000063`
  - 서울대 `0000019`
  - 제주대 `0000027`
  - 연세대 `0000149`
  - 고려대 `0000069`
  - 부산대 `0000014`
  - 경북대 `0000005`
  - 남서울대 `0000245`

---

## 6. 구현 우선순위 (Claude Code 작업 순서 권장)

| 순서 | 작업 | 의존 | 검증 방법 |
|---|---|---|---|
| 1 | `/input/schema_v3.yaml` 배치 | - | 파일 존재 |
| 2 | CLAUDE.md 메인 지침 작성 | 1 | 섹션 누락 없음 |
| 3 | `adiga-crawler` 스킬 + 스크립트 | 2 | 8개 대학 fetch 성공 |
| 4 | `html-parser` 스킬 + 스크립트 | 3 | 4시트 raw 추출 성공 |
| 5 | `rule-mapper` 스킬 + 스크립트 | 4 | 매핑률 60% 이상 |
| 6 | `xlsx-builder` 스킬 + 스크립트 | 5 | 골든셋과 동일 헤더 |
| 7 | `evaluator` 스킬 + 스크립트 | 6 | PoC 결과 재현 (가천대 76% PK 매칭) |
| 8 | `normalizer-result` 서브에이전트 | 5, 6 | Haiku → Sonnet 에스컬레이션 작동 |
| 9 | `normalizer-eval` 서브에이전트 | 5, 6 | seed 50% 채움 |
| 10 | `reporter` 스킬 | 7, 8, 9 | 리포트 생성 |
| 11 | end-to-end 통합 테스트 | 1~10 | 8개 대학 전체 실행 성공 |
| 12 | 200+ 대학 본격 실행 | 11 | 95% 이상 대학에서 4시트 모두 생성 |

각 단계는 다음 단계로 넘어가기 전에 검증을 통과해야 한다.

---

## 7. 완료 정의 (Definition of Done)

본 에이전트가 **완성됐다**고 선언할 수 있는 조건:

| 조건 | 확인 방법 |
|---|---|
| 8개 타겟 대학에서 4시트 모두 데이터 추출됨 | `/output/per_university/`에 8개 파일, 각 4시트 |
| susi_result 골든셋 비교 PK 매칭률 ≥ 85% | `evaluation_report.xlsx` summary 시트 |
| susi_result 셀 일치율 ≥ 90% (매칭된 행 한정) | 동일 |
| 평가기준 시트 seed 컬럼 평균 채움률 ≥ 50% | `validation_report.md` |
| error 시트에 정당한 사유 외 실패 없음 | `error_log.json` |
| 부분 갱신 모드 동작 검증 (1개 대학만 재수집) | 수동 테스트 |
| 200+ 개 대학 전체 실행 시 95% 이상 정상 완료 | `run_state.json` 집계 |

---

## 8. 알려진 위험과 대응

| 위험 | 영향 | 대응 |
|---|---|---|
| adiga 사이트 구조 변경 | T2 파싱 전면 실패 | 파싱 실패율 임계치(10%) 알림, html-parser 스킬에서 규칙 분리 보관 |
| LLM 응답 비결정성 | 같은 입력에 다른 결과 | confidence + 자기 검증으로 흡수, raw_text 항상 보관 |
| 대학마다 너무 다른 평가 표기 | 정형 컬럼 채움률 낮음 | extension_columns로 흡수, 못 잡으면 raw_text |
| 골든셋 데이터 자체의 학년도 매핑 모호성 | 평가 결과 왜곡 | 학년도 명시(searchSyr=2027 → 2025년 결과), 골든셋 메타 별도 기록 |
| 200+ 대학 처리 시간 길어짐 | 운영 부담 | 동시 워커, 부분 갱신 모드, run_state 기반 재개 |

---

## 부록. 참조 정보

### A. 골든셋 8개 대학 행수 (susi_result 기준)

| 대학 | 행수 | 비고 |
|---|---:|---|
| 가천대학교 | 285 | 대학별환산 0% |
| 서울대학교 | 210 | 대학별환산 0% |
| 제주대학교 | 315 | |
| 연세대학교 | 216 | |
| 고려대학교 | 235 | 충원합격순위 81% |
| 부산대학교 | 239 | |
| 경북대학교 | 160 | 대학별환산 0% |
| 남서울대학교 | 174 | 대학별환산 82% |

총 1,824행 (PK 중복 제거 후).

### B. 검증 임계치 한눈에

| 지표 | 임계치 | 출처 |
|---|---|---|
| T1 HTML 크기 | ≥ 10KB | 빈 페이지 방지 |
| T3 룰 매핑률 | ≥ 60% | 평균 기준 |
| T4a confidence | ≥ 0.7 → 채택, < 0.7 → 에스컬레이션 | LLM 정확도 균형점 |
| T4b seed 채움률 | ≥ 50% | 정형화 가능 비율 추정 |
| T6 PK 매칭률 | ≥ 85% | DoD |
| T6 셀 일치율 | ≥ 90% | DoD |
| 파싱 실패율 알림 | > 10% | 사이트 변경 감지 |
| 한 대학 LLM 호출 상한 | 5회 | 비용 통제 |
| 시트별 raw_text 입력 상한 | 8000자 | 프롬프트 크기 통제 |

### C. URL 패턴 참고

```
https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do
  ?menuId=PCUVTINF2000
  &unvCd={code}        # 7자리 zero-padded ID
  &searchSyr={year}    # URL의 학년도 = 실제 학년도 + 1
```

학년도 매핑 예시:
- `searchSyr=2027` → 2026학년도 평가기준 + 2025학년도 결과
- `searchSyr=2026` → 2025학년도 평가기준 + 2024학년도 결과

---

*이 문서는 Claude Code의 구현 참조용이다. 본문에 등장하는 모든 임계치·구조·규약은 Claude Code가 그대로 따른다. 구현 중 발견되는 모호한 부분은 본 문서에 명시된 원칙(판단 vs 코드 분리, 검증 패턴, 실패 처리)에 비추어 결정한다.*
