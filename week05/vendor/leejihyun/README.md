# adiga 입시 데이터 수집 에이전트 — 프로젝트 핸드오프

> **Claude Code를 위한 진입점.** 구현 시작 전 이 README를 먼저 읽고, 그 다음 `/docs/agent_design.md`로 진행한다.

---

## 1. 이 묶음에 무엇이 있는가

```
/handoff
├── README.md                           # 이 문서. 가장 먼저 읽을 것
│
├── /docs                               # 구현 계획서 + 도메인 지식
│   ├── agent_design.md                 # 메인 계획서 (★ 핵심 문서)
│   └── /references                     # 참조 자료
│       ├── adiga-site-reference.md     # URL 패턴·HTML 구조
│       ├── normalization-dictionary.md # 표기 매핑 사전
│       ├── 00_통합_발견.md             # 8개 대학 통합 분석
│       ├── 04_고려대_분석.md
│       ├── 05_부산대_분석.md
│       ├── 06_경북대_분석.md
│       ├── 07_남서울대_분석.md
│       └── /poc                        # 참고 코드 (그대로 사용 X, 패턴만 참고)
│           ├── crawler.py
│           ├── evaluate.py
│           └── poc_parser.py
│
└── /input                              # 실행 시 사용할 입력 파일
    ├── schema_v3.yaml                  # 컬럼 스키마 정의
    ├── universities.csv                # 8개 타겟 대학 마스터
    └── 2025_어디가입결_통합본.xlsx     # 골든셋 (평가용 정답 데이터)
```

---

## 2. 파일 매니페스트 (어디서 무엇을 참조하나)

### 2.1 구현 시작 시 읽을 것

| 순서 | 파일 | 역할 |
|---|---|---|
| 1 | `README.md` (이 문서) | 전체 그림 |
| 2 | `/docs/agent_design.md` | 메인 계획서 — **여기에 모든 결정이 있음** |
| 3 | `/input/schema_v3.yaml` | 4시트 컬럼 정의 (구현 중 항상 참조) |

### 2.2 단계별로 참조할 자료

| 구현 단계 | 참조 |
|---|---|
| 폴더 구조 만들기 | `agent_design.md` §4.1 |
| CLAUDE.md 작성 | `agent_design.md` §4.2 |
| `adiga-crawler` 스킬 | `agent_design.md` §4.4 + `docs/references/adiga-site-reference.md` |
| `html-parser` 스킬 | `agent_design.md` §4.4 + `docs/references/adiga-site-reference.md` |
| `rule-mapper` 스킬 | `agent_design.md` §4.4 + `docs/references/normalization-dictionary.md` |
| `normalizer-result` 서브에이전트 | `agent_design.md` §4.5 + `input/schema_v3.yaml` |
| `normalizer-eval` 서브에이전트 | `agent_design.md` §4.5 + `docs/references/00~07_*.md` (8개 대학 도메인 지식) |
| `xlsx-builder` 스킬 | `agent_design.md` §4.4 + 골든셋 양식 참고 |
| `evaluator` 스킬 | `agent_design.md` §4.4 + `input/2025_어디가입결_통합본.xlsx` |
| 검증·실패 처리 | `agent_design.md` §3 (모든 단계 공통) |
| 완료 판정 | `agent_design.md` §7 (DoD) |

### 2.3 참고 코드 사용 정책

`/docs/references/poc/`의 코드는 **PoC 단계에서 만들어진 참고용**이다.

| 파일 | 어떻게 활용 |
|---|---|
| `crawler.py` | adiga URL 패턴, HTML 파싱 알고리즘, 골든셋 양식 변환 로직 참고 |
| `evaluate.py` | PK 정규화 규칙, 셀 일치 판정 규칙, 리포트 시트 구성 참고 |
| `poc_parser.py` | 마크다운 파싱 PoC (실제로는 BS4로 HTML 직접 파싱 권장) |

**원칙**: Claude Code는 새로 작성하되, 검증된 알고리즘과 규약은 그대로 가져온다. 단, 폴더 구조와 스킬/서브에이전트 분리는 `agent_design.md` §4의 새 구조를 따른다.

---

## 3. 입력 파일 상세

### 3.1 `/input/schema_v3.yaml`

- 형식: YAML
- 내용: 4시트(susi_result, susi_eval, jeongsi_result, jeongsi_eval)의 컬럼 정의 + 7종 분류 코드(enum)
- 사용처: 거의 모든 단계 (T0 로드, T3 매핑, T4 정규화, T5 빌드, T7 검증)
- **수정 가능 여부**: 신규 칼럼 후보(T4c)가 채택되면 추가 가능. 기존 컬럼 삭제 금지.

### 3.2 `/input/universities.csv`

- 형식: CSV (UTF-8)
- 내용: 8개 타겟 대학의 unvCd, 대학명, 특이사항
- 사용처: T0 준비 단계 (full 모드 시 이 리스트 전체, partial 모드 시 일부)
- **확장 방법**: 전체 200+개 대학 운영 시 추가 행 append

### 3.3 `/input/2025_어디가입결_통합본.xlsx`

- 형식: Excel (2단 헤더, 29컬럼, 21,435행)
- 내용: 작년에 수작업으로 검증한 정답 데이터 (수시 입시결과만)
- 사용처: T6 평가 단계에서 비교 기준 (susi_result 한정)
- **컬럼 구조**:
  - A~C: PK (대학·전형·모집단위)
  - D~J: ViveOn 내부 매핑 컬럼 (라벨, 바이브온_* 6개) — **평가 제외**
  - K~M: 모집정보 (모집인원·경쟁률·충원합격순위)
  - N~T: 대학별환산 그룹 (7컬럼)
  - U~AC: 학생부등급 그룹 (9컬럼)
- 학년도: 2025학년도 결과 (URL `searchSyr=2026`에 해당)

---

## 4. 도메인 지식 자료 활용

### 4.1 8개 대학 분석 노트

`/docs/references/00~07_*.md` 파일들은 8개 대학을 사전 분석한 결과다. 특히 **`normalizer-eval` 서브에이전트의 AGENT.md에서 이 노트들을 참조**해야 한다.

각 노트에서 얻을 도메인 지식:

| 노트 | 핵심 발견 |
|---|---|
| `00_통합_발견.md` | 8개 대학 통합 패턴 — 평가요소 표기 방식 5종, 면접 유형 분류 |
| `04_고려대_분석.md` | 특기자·사이버국방 등 비표준 전형, 단계별 가중치 |
| `05_부산대_분석.md` | 모집단위별 수능 응시영역 분기, 변환표준점수, 캠퍼스 분리 |
| `06_경북대_분석.md` | 영농창업·SW특별·모바일과학 등 특수전형 폭발 (enum 한계 사례) |
| `07_남서울대_분석.md` | 평가요소 2슬롯, 학업역량 미반영, 면접 문항 사전공개 |

**활용 방법**: normalizer-eval 서브에이전트가 LLM 프롬프트에 이 노트들의 핵심 패턴을 컨텍스트로 포함시킨다.

### 4.2 정규화 사전

`/docs/references/normalization-dictionary.md`는 `rule-mapper` 스킬이 직접 참조한다.

| 섹션 | 처리 위치 |
|---|---|
| §1 반영교과 표기 | rule-mapper 매핑 함수 |
| §2 학생부등급 기준 | rule-mapper 매핑 함수 |
| §3 빈 셀 표기 | html-parser (파싱 단계) |
| §4 숫자 정규화 | rule-mapper |
| §5 Boolean 표기 | rule-mapper |
| §6 전형구분 대분류 | rule-mapper (키워드 매칭) |
| §7 면접유형 | rule-mapper (키워드 매칭) |
| §8 평가표기방식 | normalizer-eval (LLM이 판단) |
| §9 캠퍼스 분리 | html-parser 또는 rule-mapper |

---

## 5. Claude Code에게 권장하는 작업 순서

```
[1단계] 환경 준비
  - /handoff 내용을 프로젝트 루트로 복사
  - schema_v3.yaml과 universities.csv를 그대로 /input/에 둠
  - 골든셋 엑셀도 /input/에 둠

[2단계] 핵심 문서 읽기
  - docs/agent_design.md 전체 통독
  - schema_v3.yaml 구조 파악
  - 8개 대학 분석 노트 중 00_통합_발견.md 통독

[3단계] 폴더 구조 생성
  - agent_design.md §4.1 그대로 생성
  - CLAUDE.md, AGENT.md, SKILL.md는 빈 파일로 먼저 생성

[4단계] 스킬 우선 구현 (결정론적, 검증 쉬움)
  - 순서: adiga-crawler → html-parser → rule-mapper → xlsx-builder → evaluator → reporter
  - 각 스킬마다 단독 테스트 (PoC 코드의 알고리즘 참고)

[5단계] 서브에이전트 구현 (LLM 판단)
  - normalizer-result (Haiku 우선 라우팅)
  - normalizer-eval (Sonnet, 8개 대학 도메인 지식 포함)

[6단계] CLAUDE.md 메인 오케스트레이션 구현
  - agent_design.md §4.2 섹션 가이드 따름
  - T0~T7 워크플로우 호출

[7단계] 8개 대학으로 end-to-end 테스트
  - DoD 조건 확인 (agent_design.md §7)
  - 평가 리포트의 PK 매칭률 ≥ 85% 확인

[8단계] 200+ 대학 본격 실행
  - 부분 갱신 모드 검증
  - run_state.json 기반 재개 검증
```

---

## 6. 의문이 생기면

| 질문 유형 | 참조 |
|---|---|
| "왜 이렇게 결정했나" | `agent_design.md` §1.1 (시작 시점 가정과 검증) — 가능하면 본 문서의 결정을 그대로 따를 것 |
| "이 단계에서 무엇을 해야 하나" | `agent_design.md` §2 (단계별 명세) |
| "성공 기준은 무엇인가" | `agent_design.md` §3.1 (검증 매트릭스) |
| "실패하면 어떻게 하나" | `agent_design.md` §3.2 (실패 처리 정책) |
| "파일을 어디 저장하나" | `agent_design.md` §4.8 (산출물 파일 형식) |
| "LLM은 언제 부르나" | `agent_design.md` §4.6 (판단 vs 코드 역할 분리) |
| "스킬과 서브에이전트 차이" | `agent_design.md` §4.4, §4.5 |
| "이 표기는 어떻게 정규화하나" | `docs/references/normalization-dictionary.md` |
| "adiga 페이지 구조" | `docs/references/adiga-site-reference.md` |
| "평가기준 표기 다양성" | `docs/references/00_통합_발견.md` 외 |

명시되지 않은 사항은 `agent_design.md`의 설계 원칙(판단/코드 분리, 검증 패턴, 실패 처리)에 비추어 판단한다.

---

## 7. 변경 이력 추적

이 핸드오프 묶음은 v1.0이다. Claude Code가 구현 중 발견한 다음 사항은 별도 문서에 기록하고 PM 검토 후 본 묶음을 업데이트한다:

| 발견 유형 | 기록 위치 |
|---|---|
| schema에 없는 새 컬럼 패턴 | `/output/logs/new_columns_proposals.json` |
| 정규화 사전에 없는 새 표기 | `/output/logs/new_normalizations.json` |
| adiga 사이트 구조 변경 | `/output/logs/site_changes.json` |
| 본 계획서의 가정이 틀린 케이스 | `/docs/agent_design_addendum.md` (신규 파일) |

---

*이 묶음은 Claude Code의 자율적 구현을 돕기 위해 설계되었다. 본문에 등장하는 모든 규약·임계치·구조는 그대로 따라야 한다. 모호한 부분이 있으면 본 문서의 §6 매핑을 따라 정확한 참조 위치를 찾는다.*
