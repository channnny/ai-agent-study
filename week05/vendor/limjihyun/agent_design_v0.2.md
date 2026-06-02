# AI Agent 설계서: 어디가 입결 데이터 자동 수집 에이전트

> **목적**: 대학어디가(adiga.kr)에서 학생부종합/학생부교과 전형의 입결 데이터를 자동 수집하여, 정해진 엑셀 템플릿에 맞춰 산출하는 AI 에이전트 시스템 설계.
>
> **버전**: v0.2 (1차 리뷰 반영)
> **작성 기준 PRD**: 어디가 입결 데이터 수집 자동화 PRD
> **범위 제외**: 법적·이용약관 검토는 본 문서의 범위 외 (별도 트랙)

---

## 1. 시스템 개요

### 1.1 핵심 가치
- 인간이 수작업하던 입결 데이터 수집·전사 업무를 AI 에이전트로 자동화.
- 대학별로 다른 표 구조를 LLM의 의미 매칭 능력으로 흡수.

### 1.2 입력 / 산출물
| 구분 | 내용 |
|---|---|
| **입력** | 대학 코드(`univCode`) 리스트, 엑셀 템플릿 파일, 매핑 사전(`mapping_dictionary.yaml`), 셀 매핑(`cell_mapping.yaml`) |
| **산출물** | 대학별 채워진 엑셀 파일(`outputs/{univCode}.xlsx`) + 전형 상세 요약(JSON) + 검증 리포트 + REVIEW 시트 |

### 1.3 운영 정책
- **실행 빈도**: 매년 입시철 1~2회
- **대상 규모**: 1회당 30~80개 대학 (수도권 주요 대학 중심)
- **연도 범위**: 매 실행은 **최신 1개 연도**만 수집 (덮어쓰기 정책)
- **모집단위 그래뉼래러티**: 어디가 페이지에 표시된 행 단위 그대로 (정규화 없음)
- **결측 정책**: 대학이 미공개한 항목은 **빈칸(null)** 유지, 별도 마킹 없음

### 1.4 설계 원칙
1. **결정론적 부분과 추론 부분을 분리** — 페이지 이동·표 추출은 Python 결정론, 의미 매칭은 LLM.
2. **사람 검토 지점을 명시적으로 둔다** — 신뢰도 낮은 매핑은 자동 통과시키지 않는다.
3. **원본 보존** — 가공 전 raw 데이터를 항상 함께 저장하여 사후 검증 가능.
4. **회차 간 학습** — Human Checkpoint 결정은 매핑 사전에 누적되어 다음 회차의 자동 통과율을 높인다.

---

## 2. 아키텍처

**런타임**: 커스텀 Python — Playwright(브라우저 자동화) + Anthropic SDK(Claude Sonnet 4.6).

```
┌─────────────────────────────────────────────────────────────┐
│                      Orchestrator                            │
│         (대학 리스트 루프, 상태 관리, 에러 처리)              │
└──────┬──────────────────────────────────────────────────────┘
       │
       ▼  대학 코드 1개씩 (병렬도 5)
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Crawler    │───▶│   Mapper    │───▶│  Validator  │
│ (Playwright)│    │ (Sonnet 4.6)│    │   (Python)  │
└─────────────┘    └─────────────┘    └──────┬──────┘
                                              │
                          ┌───────────────────┴────────┐
                          │                            │
                     PASS ▼                     REVIEW ▼
                  ┌─────────────┐         ┌──────────────────┐
                  │ Excel Writer │         │ REVIEW 시트 적재 │
                  └─────────────┘         │ (사람 검토)      │
                          │                └────────┬────────┘
                          │                         │ 승인된 결정
                          │                         ▼
                          │              ┌──────────────────┐
                          │              │ 매핑 사전 자동    │
                          │              │ 업데이트 + diff  │
                          │              └────────┬─────────┘
                          └─────────────┬─────────┘
                                        ▼
                                대학별 엑셀 산출
```

### 2.1 에이전트 구성
| 에이전트 | 책임 | 입출력 |
|---|---|---|
| **Orchestrator** | 대학 코드 루프, 캐시·재시도, 상태 로깅 | 입력: 코드 리스트 / 출력: 처리 상태 JSON |
| **Crawler** | 페이지 진입, 탭 클릭, 표 추출 | 입력: univCode / 출력: raw JSON |
| **Mapper** | 웹 용어 ↔ 표준 스키마 매핑 (Sonnet 4.6) | 입력: raw JSON / 출력: 표준 JSON + 신뢰도 |
| **Validator** | 수치 일치성, 누락 검사, 범위 검사 | 입력: 표준 JSON + raw / 출력: PASS / REVIEW / FAIL |
| **Excel Writer** | 템플릿 복제 + 셀 입력 + 재독 검증 | 입력: 표준 JSON, 템플릿 / 출력: `.xlsx` |
| **REVIEW 시트** | 신뢰도 낮은 항목을 사람 검토용 시트로 적재 | 입력: REVIEW 케이스 / 출력: 사람 결정 |

---

## 3. 에이전트별 상세 명세

### 3.1 Orchestrator
- **역할**: 대학 코드 리스트를 순회하며 Crawler → Mapper → Validator → Writer를 호출. 실패 시 재시도(최대 3회) 및 상태 로깅.
- **병렬도**: 5 (사이트 부하 vs 처리 시간 균형, 추후 캘리브레이션)
- **상태 관리**: 대학별 `{univCode, status, attempt, error, output_path, confidence_avg}` 저장.
- **에러 핸들링**:
  - 페이지 진입 실패 → 2회 재시도 후 `FAILED` 마킹, 건너뜀
  - 매핑 신뢰도 < 0.6 → `REVIEW_QUEUE`
  - Validator FAIL → `REVIEW_QUEUE`

### 3.2 Crawler Agent
- **역할**: 어디가 대학 상세 페이지에서 학생부종합·학생부교과 탭의 모든 표를 raw로 추출.
- **단계**:
  1. URL: `https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000&univCode={code}`
  2. 페이지 로드 + 네트워크 idle 대기
  3. **부수 UI 처리**: 쿠키·공지 팝업이 있으면 닫기 (selector 사전 등록)
  4. "평가기준 및 입시결과" 메뉴 클릭
  5. 학생부종합전형 탭 클릭 → 모든 `<table>` 추출
  6. 학생부교과전형 탭 클릭 → 동일 추출
  7. **페이지네이션 / "더보기"** 존재 시 모두 전개 후 추출
  8. 각 표를 `{caption, headers, rows}`로 raw JSON 저장 + 스크린샷 저장
- **사이트 변경 감지**:
  - 표 0개 추출 또는 예상 탭 selector 미존재 시 즉시 `STRUCTURE_CHANGED` 알림 발행
  - 표 헤더 세트의 해시를 회차별로 비교, 직전 회차와 다르면 워닝
- **Playwright 도구**:
  - `page.goto(url, wait_until="networkidle")`
  - `page.get_by_text(...)`, `page.locator(...).click()`
  - `page.locator("table").all()` → 구조화 파싱
- **출력 예시**:
```json
{
  "univCode": "0000010",
  "univName": "OO대학교",
  "year": 2026,
  "crawled_at": "2026-05-13T10:00:00+09:00",
  "tabs": {
    "jonghap": {
      "summary_tables": [{ "caption": "전형별 주요사항", "headers": [...], "rows": [...] }],
      "result_tables":  [{ "caption": "입시결과",         "headers": [...], "rows": [...] }],
      "screenshot_path": "out/raw/0000010/jonghap.png",
      "headers_hash": "sha256:..."
    },
    "gyogwa": { ... }
  }
}
```

### 3.3 Mapper Agent
- **역할**: raw JSON을 표준 스키마로 변환. Claude Sonnet 4.6 호출.
- **로직**:
  1. 표의 caption + headers로 표의 의미를 분류 (전형별 주요사항 vs 입시결과).
  2. 각 row를 표준 스키마 필드와 매핑.
  3. **매핑 단계**:
     - **1차**: `mapping_dictionary.yaml` 직접 매칭 (신뢰도 1.0)
     - **2차**: 직접 매칭 실패 시 LLM 호출 (신뢰도 0.6~0.9)
- **매핑 사전(샘플)**:
  | 웹사이트 표현 | 표준 필드 |
  |---|---|
  | "70% 컷", "70%컷", "상위 70%" | `cutoff_70` |
  | "최종등록자 평균", "평균 등급" | `avg_grade` |
  | "모집단위" | `recruitment_unit` |
  | "전형방법" | `evaluation_method` |
- **신뢰도 분기**:
  - `>= 0.9` → 자동 통과
  - `0.6 ~ 0.9` → Validator 통과 시 PASS, 실패 시 REVIEW
  - `< 0.6` → 무조건 REVIEW
- **사전 자동 업데이트**:
  - REVIEW에서 사람이 승인한 매핑은 다음 실행 전 자동으로 `mapping_dictionary.yaml`에 추가
  - **안전장치**: 사전 업데이트 시 git 커밋 단위로 diff 저장, `mapping_dictionary.history/{timestamp}.yaml`에 백업 → 오학습 시 1-step revert 가능
  - 동일 표현이 충돌(서로 다른 표준 필드로 승인) 시 자동 반영 보류 + 알림

### 3.4 Validator Agent
- **역할**: 매핑된 표준 데이터가 원본과 일치하는지, 누락은 없는지, 비정상 값은 없는지 검사.
- **검증 룰**:
  1. **수치 일치성** — 표준 JSON의 모든 수치가 raw JSON에 존재하는지.
     - 정규화 후 비교: 공백·콤마·"등급" 등 단위 토큰 제거, 소수점 2자리로 통일(예: "2.5" ≡ "2.50").
     - 매칭 실패 1건이라도 있으면 REVIEW.
  2. **누락 검사** — 필수 필드(모집단위, 70%컷, 평균 등) 중 raw에는 있는데 표준에서 빈 경우만 FAIL. (raw에도 없으면 정상 결측, 빈칸 유지)
  3. **범위 검사** — 등급 1.0~9.0, 비율 0~100. 벗어나면 REVIEW.
  4. **모집단위 수 일치** — raw 행 수 = 표준 행 수.
- **출력**: `{verdict: PASS | REVIEW | FAIL, issues: [...], evidence: [...]}`

### 3.5 Excel Writer
- **역할**: 엑셀 템플릿 복제 후, 표준 데이터를 정해진 셀에 입력.
- **로직**:
  1. 템플릿을 `outputs/{univCode}.xlsx`로 복제. **기존 파일은 `outputs/.backup/{univCode}_{timestamp}.xlsx`로 자동 이동.**
  2. `cell_mapping.yaml` 로드 → 시트별·셀 단위 매핑.
  3. 모집단위 행 수에 맞춰 데이터 입력 (병합셀·수식 보존).
  4. **재독 검증**: 입력 직후 파일을 다시 열어 입력값과 일치 확인.
     - 일치 → 완료
     - 불일치 → 해당 대학을 `REVIEW_QUEUE`로 회송 + 상세 로그
- **양식 보호 규칙**:
  - 셀 직접 입력만, 행 추가/삭제 금지
  - 수식 셀에는 쓰지 않음 (셀 좌표 검사)
  - 병합셀은 좌상단 셀에만 입력

### 3.6 REVIEW 시트 (Human Checkpoint)
- **트리거 조건**:
  - Mapper 신뢰도 < 0.6
  - Validator verdict = REVIEW 또는 FAIL
  - Crawler가 표 0개 추출 (사이트 변경 가능성)
  - Writer 재독 검증 불일치
- **구현**: 별도 `outputs/_review/{batch_id}.xlsx` 단일 파일.
  - 시트 컬럼: `univCode | univName | 항목 | 웹사이트 표현 | 추정 매핑 | 신뢰도 | 스크린샷 경로 | [승인/수정/스킵] | 사람 수정값 | 비고`
  - 검토 후 동일 파일 저장 → 다음 회차 시작 시 Orchestrator가 읽어 처리
- **승인된 결정 → 매핑 사전 자동 반영** (§3.3 안전장치 적용)

---

## 4. 표준 데이터 스키마

```yaml
university:
  univCode: string
  univName: string
  year: integer            # 수집 대상 연도 (예: 2026)
  collected_at: datetime

jonghap:    # 학생부종합전형
  summary:
    - recruitment_unit: string      # 모집단위 (어디가 표기 그대로)
      evaluation_method: string     # 전형방법
      quota: integer | null         # 모집인원
      stages: string | null         # 단계별 평가
  results:
    - recruitment_unit: string
      avg_grade: float | null       # 평균 등급 (미공개 시 null)
      cutoff_70: float | null       # 70% 컷
      cutoff_50: float | null
      competition_ratio: float | null

gyogwa:     # 학생부교과전형 (동일 구조)
  summary: [...]
  results: [...]

meta:
  confidence_scores: { ... }        # 필드별 신뢰도
  source_screenshots: [ ... ]
  validator_report: { ... }
```

> 실제 필드는 엑셀 템플릿의 컬럼과 1:1 매칭되도록 확정 필요 (§9).

---

## 5. 처리 흐름 (End-to-End)

1. **입력 로드** — `univ_codes.csv`, 직전 회차의 검토 완료된 REVIEW 시트 (있으면 사전 자동 업데이트)
2. **대학별 루프** (병렬도 5):
   - Crawler가 페이지 진입·표 추출 → `raw/{code}.json` 저장
   - Mapper가 raw → 표준 변환 → `mapped/{code}.json` 저장
   - Validator 검증 → verdict 부여
   - PASS → Writer → `outputs/{code}.xlsx`
   - REVIEW/FAIL → REVIEW 시트 적재
3. **최종 리포트 생성** — 성공/검토/실패 건수, 신뢰도 분포, 사이트 구조 변경 알림.

---

## 6. 리스크 대응

| 리스크 | 대응 |
|---|---|
| 대학마다 표 컬럼·명칭 상이 | 매핑 사전 + LLM 의미 매칭 + 신뢰도 기반 분기 |
| 새로운 표현 등장 | 신뢰도 낮게 책정 → REVIEW → 사전에 적립 |
| 엑셀 양식 깨짐 | 행 추가 금지, 수식 셀 보호, 재독 검증, 자동 백업 |
| 사이트 구조 변경 | 표 0개 추출·헤더 해시 변경 시 즉시 알림 |
| 페이지 로딩 지연 | 명시적 wait, 3회 재시도, 실패 시 격리 |
| 매핑 사전 오학습 | diff 저장 + history 백업으로 1-step revert |
| 동일 표현 충돌 매핑 | 자동 반영 보류 + 알림, 사람이 충돌 해소 |

> **범위 외**: adiga.kr 자동화 수집의 법적·이용약관 적합성은 본 설계서 범위 외 (PM이 별도 트랙으로 검토).

---

## 7. 검증 전략

### 7.1 데이터 정확성
- Validator의 수치 일치성 룰로 자동 보장.
- 무작위 샘플 N건은 매 회차 사람이 페이지 vs 엑셀 1:1 스폿 체크.

### 7.2 누락 검증
- Orchestrator가 입력 리스트 vs 산출 파일 목록 diff → 누락 0건 확인.
- 산출 안 된 대학은 사유(타임아웃/표 없음/검증실패)와 함께 리포트.

### 7.3 회귀 검증
- 동일 코드 재실행 시 결과 동일성 확인 (raw 캐시 적중 케이스).
- raw가 변했는데 표준이 같다면 정상, raw 동일한데 표준이 다르면 비결정성 의심 → 알림.

---

## 8. 운영 정책

- **대학 추가**: 코드만 리스트에 추가. 신규 표 형식은 자동 REVIEW로 빠짐.
- **새 전형 추가** (예: 논술): Crawler에 탭, 스키마에 섹션 추가.
- **엑셀 템플릿 변경**: `cell_mapping.yaml`만 수정.
- **raw 캐시 정책**: TTL **7일**. 7일 이내 raw가 있으면 Crawler 스킵, 이상이면 재크롤. `--refresh` 플래그로 강제 재크롤.
- **로그·관측**: 대학별 신뢰도 평균 트래킹 → 매핑 사전 보강 필요 시점 감지.
- **출력 백업**: `outputs/.backup/{univCode}_{timestamp}.xlsx`로 자동 보존 (최근 5회).

---

## 9. 비용·시간 추정 (대략)

| 항목 | 가정 | 추정 |
|---|---|---|
| Crawler 대학당 시간 | 페이지 4~6회 클릭, 표 6~10개 추출 | 30~60초 |
| Mapper LLM 호출 | 대학당 ~10회 호출, 호출당 입력 3K / 출력 1K 토큰 (Sonnet 4.6) | 대학당 ~$0.1 |
| Validator + Writer | 로컬 처리 | 대학당 5초 |
| **1회 실행 (60개 대학, 병렬도 5)** | | **~15분, ~$6** |

> Mapper 비용은 매핑 사전이 커질수록 LLM 호출 비율이 감소하여 회차마다 절감.

---

## 10. 미정 항목 (다음 미팅에서 확정)

- [ ] 엑셀 템플릿 실제 파일 검토 — 병합·수식 영역 식별, `cell_mapping.yaml` 작성
- [ ] 표준 스키마 필드 최종 확정 — 템플릿 컬럼과 1:1 매칭
- [ ] 매핑 사전 초기 버전 — 우선 5~10개 대학 샘플 분석 기반
- [ ] 신뢰도 임계값(0.9 / 0.6) — POC 데이터로 캘리브레이션
- [ ] 병렬도(5) — 실제 사이트 응답·차단 정책 확인 후 조정
- [ ] 사이트 변경 알림 채널 — Slack / 이메일 / 로컬 로그 중 선택
