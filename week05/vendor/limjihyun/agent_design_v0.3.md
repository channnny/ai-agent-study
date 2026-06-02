# AI Agent 설계서: 어디가 입결 데이터 자동 수집 에이전트

> **버전**: v0.3 (실제 엑셀 템플릿 반영)
> **변경 요약**: 실제 템플릿(`어디가입결_양식.xlsx`) 구조에 맞춰 스키마 확장(대학별환산·학생부등급 2개 점수체계), Writer 행 누적 정책 수정, `cell_mapping.yaml` 초안 추가.
> **범위 제외**: 법적·이용약관 검토는 본 문서 범위 외.

---

## 1. 시스템 개요

### 1.1 핵심 가치
- 인간이 수작업하던 입결 데이터 수집·전사 업무를 AI 에이전트로 자동화.
- 대학별로 다른 표 구조를 LLM의 의미 매칭 능력으로 흡수.

### 1.2 입력 / 산출물
| 구분 | 내용 |
|---|---|
| **입력** | 대학 코드(`univCode`) 리스트, 엑셀 템플릿(`어디가입결_양식.xlsx`), `mapping_dictionary.yaml`, `cell_mapping.yaml` |
| **산출물** | `outputs/{univCode}.xlsx` (단일 시트 `수시`, 헤더 2행 + 데이터 누적), `mapped/{univCode}.json`, `outputs/_review/{batch_id}.xlsx`, 처리 리포트 |

### 1.3 운영 정책
- **실행 빈도**: 매년 입시철 1~2회
- **대상 규모**: 1회 30~80개 대학
- **연도 범위**: 매 실행 최신 1개 연도 (덮어쓰기 + 자동 백업)
- **모집단위 그래뉼래러티**: 어디가 표시 그대로 (정규화 없음)
- **결측 정책**: 빈칸(null) 유지

### 1.4 설계 원칙
1. 결정론적 부분과 추론 부분 분리 — 페이지·표 추출은 Python, 의미 매칭은 LLM.
2. 사람 검토 지점 명시.
3. 원본 보존 (raw JSON + 스크린샷).
4. 회차 간 학습 — Human Checkpoint 결정이 매핑 사전에 누적.

---

## 2. 아키텍처

**런타임**: Python — Playwright + Anthropic SDK(Claude Sonnet 4.6).

```
Orchestrator (병렬도 5)
   ├─ Crawler   (Playwright)         → raw/{code}.json
   ├─ Mapper    (사전 + Sonnet 4.6)   → mapped/{code}.json
   ├─ Validator (Python)              → verdict
   └─ Writer    (openpyxl)            → outputs/{code}.xlsx

REVIEW 시트 ──→ 다음 회차 시작 시 사전 자동 업데이트
```

---

## 3. 에이전트별 상세

### 3.1 Orchestrator
- 대학별 루프, 병렬도 **5**, 최대 3회 재시도.
- 상태 로깅: `{univCode, status, attempt, error, output_path, confidence_avg}`.
- 에러 분기: 진입 실패 → FAILED, 신뢰도 < 0.6 → REVIEW, Validator FAIL → REVIEW.

### 3.2 Crawler Agent
- URL (검증된 패턴, 2027학년도 기준):
  - 진입: `https://www.adiga.kr/ucp/uvt/uni/univDetail.do?searchSyr={year}&searchUnvCodeAllYn=true&unvCd={code}&sortNm=&sortOrder=true&unvLink=on`
  - 입결 영역 이동: 좌측 메뉴 "평가기준 및 입시결과" 클릭 → `univDetailSelection.do`로 자동 전환
  - 파라미터명은 `unvCd` (4자리 0-패딩, 예: `0000069`=고려대[본교])
  - univCode 조회 API: `GET /man/sch/univInfo.do?search={이름}&limit=100&sort=$relevance&...` (JSON 응답의 `UNIV_CD`)
- 단계:
  1. 페이지 로드(`networkidle`)
  2. 부수 UI(쿠키·공지 팝업) 닫기 — selector 사전 등록
  3. "평가기준 및 입시결과" 메뉴 클릭
  4. **학생부종합전형** 탭 → 모든 `<table>` 추출
  5. **학생부교과전형** 탭 → 동일
  6. 페이지네이션/"더보기" 전개
  7. 표를 `{caption, headers, rows}`로 저장 + 스크린샷
- 사이트 변경 감지: 표 0개 또는 헤더 해시 변경 시 `STRUCTURE_CHANGED` 알림.
- raw 캐시 TTL **7일**, `--refresh`로 강제 재크롤.

### 3.3 Mapper Agent
- 1차: `mapping_dictionary.yaml` 직접 매칭 (신뢰도 1.0)
- 2차: Sonnet 4.6 호출 (신뢰도 0.6~0.9)
- 분기:
  - `>= 0.9` 자동 통과
  - `0.6 ~ 0.9` Validator 통과 시 PASS, 실패 시 REVIEW
  - `< 0.6` 무조건 REVIEW
- **사전 자동 업데이트** + 안전장치:
  - REVIEW 시트 승인분 → `mapping_dictionary.yaml`에 자동 반영
  - 반영 직전 `mapping_dictionary.history/{ts}.yaml` 백업 → 1-step revert 가능
  - 동일 표현이 다른 표준 필드로 충돌 시 자동 반영 보류 + 알림

### 3.4 Validator Agent
- **수치 일치성**: 정규화 후 비교 (공백·콤마·단위 제거, 소수점 2자리 통일).
- **누락**: raw에 있는데 표준이 빈 경우만 FAIL. raw에도 없으면 정상 결측.
- **범위**: 등급 1.0~9.0, 비율 0~100.
- **모집단위 수 일치**: raw 행 = 표준 행.
- 출력: `{verdict, issues, evidence}`.

### 3.5 Excel Writer
- **템플릿 구조** (`어디가입결_양식.xlsx`, 시트 `수시`):
  - R1: 그룹 헤더 (`G1:M1=대학별환산`, `N1:T1=학생부등급` 병합)
  - R2: 컬럼명 22개
  - R3 이하: 데이터 영역 (비어 있음)
- **입력 정책**:
  - 헤더(R1·R2) **절대 수정 금지**, 병합 영역 보존
  - **R3부터 row 누적**: `(전형 × 모집단위)` 가지수만큼 행 추가 (행 삽입 API가 아닌 단순 `ws.cell(row, col).value = ...`)
  - 결측은 빈 셀, 명시적 "N/A" 안 씀
  - 입력 직후 **재독 검증** — 불일치 시 해당 대학 REVIEW 회송
- **자동 백업**: 기존 `outputs/{univCode}.xlsx` 있으면 `outputs/.backup/{univCode}_{ts}.xlsx`로 이동 (최근 5회 보존).

### 3.6 REVIEW 시트
- 트리거: 신뢰도 < 0.6, Validator REVIEW/FAIL, 표 0개 추출, Writer 재독 불일치.
- 위치: `outputs/_review/{batch_id}.xlsx`.
- 컬럼: `univCode | univName | 항목 | 웹사이트 표현 | 추정 매핑 | 신뢰도 | 스크린샷 경로 | 결정 | 사람 수정값 | 비고`.
- 검토 후 동일 파일에 결정(`승인/수정/스킵`) 기재 → 다음 회차 시작 시 자동 반영.

---

## 4. 표준 데이터 스키마

엑셀 템플릿과 1:1 매칭. **대학별환산·학생부등급 2개 점수체계를 별도 보관**, 어느 한쪽만 공개돼도 다른쪽은 null.

```yaml
university:
  univCode: string
  univName: string
  year: integer
  collected_at: datetime

# 한 항목 = 한 row (전형 × 모집단위 가지수만큼)
records:
  - admission_type: "학생부종합" | "학생부교과"   # 컬럼 B
    recruitment_unit: string                       # C
    quota: integer | null                          # D
    competition_ratio: float | null                # E
    fill_rank: string | integer | null             # F 충원합격순위

    converted_score:                               # G~M 대학별환산
      max: float | null                            # G 최고
      avg: float | null                            # H 평균
      cut_50: float | null                         # I 50컷
      cut_70: float | null                         # J 70컷
      cut_80: float | null                         # K 80컷
      cut_100: float | null                        # L 100컷
      total: float | null                          # M 총점

    grade:                                         # N~T 학생부등급
      max: float | null                            # N 최고
      avg: float | null                            # O 평균
      cut_50: float | null                         # P 50컷
      cut_70: float | null                         # Q 70컷
      cut_80: float | null                         # R 80컷
      cut_90: float | null                         # S 90컷
      min: float | null                            # T 최저

    criteria: string | null                        # U 기준 (텍스트 발췌)
    reflected_subjects: string | null              # V 반영교과 (텍스트 발췌)

meta:
  confidence_scores: { ... }
  source_screenshots: [ ... ]
  validator_report: { ... }
```

---

## 5. 처리 흐름

1. 입력 로드 — 코드 리스트 + 직전 회차 REVIEW 시트 (있으면 사전 자동 업데이트 선행)
2. 대학별 루프 (병렬도 5):
   - Crawler → `raw/{code}.json`
   - Mapper → `mapped/{code}.json`
   - Validator → verdict
   - PASS → Writer → `outputs/{code}.xlsx`
   - REVIEW/FAIL → `outputs/_review/{batch_id}.xlsx`에 적재
3. 리포트 — 성공/검토/실패 건수, 신뢰도 분포, 사이트 구조 변경 알림.

---

## 6. 리스크 대응

| 리스크 | 대응 |
|---|---|
| 대학마다 표 컬럼·명칭 상이 | 사전 + LLM 매칭 + 신뢰도 분기 |
| 새로운 표현 | REVIEW → 사전 적립 |
| 두 점수체계 혼동 (환산 vs 등급) | 표 caption + 헤더로 분류, 모호 시 REVIEW |
| 엑셀 양식 깨짐 | 헤더 보존, R3 이하만 입력, 재독 검증, 자동 백업 |
| 사이트 구조 변경 | 표 0개·헤더 해시 변경 시 즉시 알림 |
| 매핑 사전 오학습 | history 백업 + revert + 충돌 보류 |
| F(충원합격순위)·U·V 결측 | 빈칸 정책으로 흡수 |

> **범위 외**: adiga.kr 자동화 수집의 법적·이용약관 적합성.

---

## 7. 검증 전략

- **자동**: Validator 수치 일치성 + 누락 + 범위 룰.
- **스폿 체크**: 매 회차 무작위 N건 사람 1:1 대조.
- **누락 검증**: 입력 vs 산출 diff.
- **회귀**: raw 동일한데 표준 다르면 비결정성 의심 → 알림.

---

## 8. 운영 정책

- raw 캐시 **7일 TTL**, `--refresh`로 강제.
- 출력 백업 최근 **5회**.
- 신뢰도 평균 트래킹 → 사전 보강 시점 감지.
- 대학 추가: 코드만 리스트에 추가.
- 새 전형 추가: Crawler에 탭, 스키마 `admission_type` 값에 추가.
- 템플릿 변경: `cell_mapping.yaml` 수정.

---

## 9. 비용·시간 추정

| 항목 | 가정 | 추정 |
|---|---|---|
| Crawler 대학당 | 클릭 4~6회, 표 6~10개 | 30~60초 |
| Mapper 대학당 | 대학당 ~15회 호출 (필드 ↑), 호출당 3K in / 1K out (Sonnet 4.6) | ~$0.15 |
| Writer·Validator | 로컬 | 5초 |
| **1회 실행 (60개 대학, 병렬도 5)** | | **~20분, ~$9** |

> 사전 매칭률 상승 시 LLM 호출 비율 감소 → 회차 비용 절감.

---

## 10. 미정 항목

- [x] ~~엑셀 템플릿 검토~~ — v0.3에서 반영, `cell_mapping.yaml` 초안 완성
- [ ] 매핑 사전 초기 버전 — 5~10개 대학 샘플 분석 기반 작성
- [ ] 신뢰도 임계값(0.9 / 0.6) — POC 데이터로 캘리브레이션
- [ ] 병렬도(5) — 실제 사이트 응답 확인 후 조정
- [ ] 사이트 변경 알림 채널 — Slack / 이메일 / 로컬 로그
- [ ] U(기준)·V(반영교과) 추출 셀렉터 — 어디가 페이지 상의 위치 확인 후 Crawler에 보강
