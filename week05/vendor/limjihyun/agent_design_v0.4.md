# AI Agent 설계서: 어디가 입결 데이터 자동 수집 에이전트

> **버전**: v0.4 (POC 시행착오 반영)
> **변경 요약**:
> 1. 사전(매핑 dictionary) 부트스트랩 모드 도입 — 1회차는 LLM 100%, 사람 검토로 사전 시드
> 2. Mapper LLM 호출 재시도·백오프·격리 정책 명시
> 3. Validator에 "빈 산출 차단" 하드 가드 추가
> 4. Crawler에 멀티헤더 평면화 단계 추가 (rowspan/colspan 해석)
> 5. 학년도 모델 분리 — `page_year`(접근 시점) vs `result_year`(데이터 학년도)
> 6. URL 패턴 실측 반영 (`univDetail.do` + 진입 후 `univDetailSelection.do`)
> 7. univCode 조회 API (`/man/sch/univInfo.do`) 명시 → 대학명 자동 변환 가능
> **범위 제외**: 법적·이용약관 검토.

---

## 1. 시스템 개요

### 1.1 핵심 가치
- 인간이 수작업하던 입결 데이터 수집·전사 업무를 AI 에이전트로 자동화.
- 대학별로 다른 표 구조를 LLM의 의미 매칭 능력으로 흡수.

### 1.2 입력 / 산출물
| 구분 | 내용 |
|---|---|
| **입력** | 대학 코드(`unvCd`) 또는 대학명 리스트, 엑셀 템플릿(`어디가입결_양식.xlsx`), `mapping_dictionary.yaml`, `cell_mapping.yaml` |
| **산출물** | `outputs/{unvCd}.xlsx` (단일 시트 `수시`, 헤더 2행 + 데이터 누적), `mapped/{unvCd}.json`, `outputs/_review/{batch_id}.xlsx`, 처리 리포트 |

### 1.3 운영 정책
- **실행 빈도**: 매년 입시철 1~2회
- **대상 규모**: 1회 30~80개 대학
- **학년도 모델** (POC에서 정정):
  - `page_year` — 어디가에 진입하는 학년도 파라미터 (`searchSyr`)
  - `result_year` — 표 안에 실제로 적힌 입결의 학년도 (예: 2026, 2025)
  - **`page_year`가 입시 전이면 그 학년도 입결은 없는 것이 정상.** 표에는 직전 학년도(들)의 결과가 표시됨.
  - 정책: 매 실행은 **`page_year` 기준 직전 1개 학년도만** 수집 (예: page_year=2027 진입 시 result_year=2026만 선택).
- **모집단위 그래뉼래러티**: 어디가 표시 그대로 (정규화 없음).
- **결측 정책**: 빈칸(null) 유지.

### 1.4 설계 원칙
1. 결정론적 부분과 추론 부분 분리 — 페이지·표 추출은 Python, 의미 매칭은 LLM.
2. 사람 검토 지점 명시.
3. 원본 보존 (raw JSON + 스크린샷).
4. 회차 간 학습 — Human Checkpoint 결정이 매핑 사전에 누적.
5. **한 단계도 침묵 실패 금지** — 어떤 게이트도 빈 산출을 PASS로 흘리지 않는다.

---

## 2. 아키텍처

**런타임**: Python — Playwright + Anthropic SDK(Claude Sonnet 4.6).

```
Orchestrator (병렬도 5)
   ├─ Crawler   (Playwright + 헤더 평면화)  → raw/{code}.json
   ├─ Mapper    (사전 + Sonnet 4.6, 재시도) → mapped/{code}.json
   ├─ Validator (Python, 빈 산출 가드)      → verdict
   └─ Writer    (openpyxl, 재독 검증)       → outputs/{code}.xlsx

REVIEW 시트 ──→ 다음 회차 시작 시 사전 자동 업데이트
```

---

## 3. 에이전트별 상세

### 3.1 Orchestrator
- 대학별 루프, 병렬도 **5**, 최대 3회 재시도(페이지 진입 한정).
- 상태 로깅: `{unvCd, status, attempt, error, output_path, confidence_avg, llm_fail_ratio}`.
- 에러 분기:
  - 진입 실패 → FAILED
  - Mapper LLM 실패율 ≥ 70% → 대학 전체 REVIEW (사전 보강 또는 API 상태 점검 신호)
  - Validator REVIEW/FAIL → REVIEW

### 3.2 Crawler Agent

#### URL 패턴 (POC 실측, 2027학년도 기준)
- **진입**:
  `https://www.adiga.kr/ucp/uvt/uni/univDetail.do?searchSyr={page_year}&searchUnvCodeAllYn=true&unvCd={code}&sortNm=&sortOrder=true&unvLink=on`
- **입결 영역 이동**: 좌측 메뉴 `"평가기준 및 입시결과"` 클릭 → URL이 `univDetailSelection.do`로 자동 전환
- 파라미터명은 `unvCd` (4자리 0-패딩, 예: `0000069`=고려대[본교], `0000070`=고려대(세종))
- **대학명 → unvCd 자동 변환**: `GET /man/sch/univInfo.do?search={이름}&limit=100&sort=$relevance&...` (JSON 응답의 `UNIV_CD`)
  - 응답 예: `[{"UNIV_NM":"고려대학교[본교]","UNIV_CD":"0000069","AREA":"서울","FOND_SE":"사립",...}]`

#### 추출 단계
1. 페이지 로드(`networkidle`)
2. 부수 UI 닫기 (`closePopup`, 쿠키·자동로그아웃·공지 등)
3. "평가기준 및 입시결과" 메뉴 클릭, networkidle 대기
4. **`univName` 추출** — 자동로그아웃 팝업 헤딩이 잡히지 않도록 `대학교[/(]` 패턴 + 길이 < 40자 필터 (POC에서 h1만으로는 잘못 잡힌 사례 발생)
5. 페이지 내 모든 `<table>` 추출

#### **헤더 평면화 (POC에서 신설)**
어디가의 입결 표는 **2~3단 헤더 + rowspan/colspan**으로 만들어진다. 단순 `headers + rows`로 추출하면 LLM이 헤더 해석까지 떠안아 토큰·실패율이 모두 증가. Crawler가 다음을 책임진다:
1. `<thead>` 행과 데이터 첫 N개 행 중 **숫자 비율이 5% 미만**인 행은 헤더로 간주.
2. rowspan/colspan을 펼쳐 가상의 grid로 변환.
3. 그룹 헤더와 하위 헤더를 점 결합: `학생부등급.70%cut`, `대학별환산.총점` 등.
4. 첫 컬럼(모집단위)은 rowspan이 자주 걸려 비어 보일 수 있으므로 **위 행의 값으로 forward-fill**.

#### 예시 (고려대 Table 11)
**평면화 전 (현 Crawler):**
```
headers: ['모집단위', '학업우수']
row[0]:  ['모집인원', '경쟁률', '충원합격순위', '학생부등급', '평가에반영된교과목']
row[1]:  ['50% cut', '70% cut']
row[2]+: 실제 데이터
```
**평면화 후 (목표):**
```
flat_headers: ['모집단위', '모집인원', '경쟁률', '충원합격순위',
               '학생부등급.50%cut', '학생부등급.70%cut', '평가에반영된교과목']
admission_label_from_thead: '학업우수'   # 표가 어느 전형인지 별도 보관
data_rows: [['경영대학', 30, 4.5, 12, 2.1, 2.5, '국영수사'], ...]
```

#### 사이트 변경 감지
- 표 0개 또는 헤더 해시 변경 시 `STRUCTURE_CHANGED` 알림.
- raw 캐시 TTL **7일**, `--refresh`로 강제 재크롤.

### 3.3 Mapper Agent

#### 부트스트랩 모드 (POC에서 신설)
설계서 v0.3까지는 "1차 사전 → 2차 LLM"이라고 했으나, 사전이 빈 상태로 시작하면 100% LLM 의존이 되어 단일 장애점이 된다. 두 모드를 명시:
| 모드 | 조건 | 동작 |
|---|---|---|
| **부트스트랩** | `mapping_dictionary.yaml`이 없거나 항목 < 20 | 모든 표를 LLM에 보냄. 비용·시간 ↑, Human Checkpoint 비중 ↑ |
| **정상** | 사전 항목 ≥ 20 + 직전 회차 자동 통과율 ≥ 70% | 1차 사전 매칭(신뢰도 1.0) → 미매칭만 LLM |
- 부트스트랩 모드에서는 **첫 5개 대학을 강제 REVIEW**로 라우팅 → 사전 시드 확보 후 자동 통과율 측정.

#### 호출 재시도·격리 (POC에서 신설)
LLM 호출은 외부 의존. 다음 정책 명시:
1. **표 단위 격리** — 한 표 실패가 다른 표·다른 대학을 망가뜨리지 않게 try/except.
2. **재시도** — `429`(rate limit), `5xx`, 네트워크 오류는 지수 백오프로 최대 3회 (1s → 4s → 16s).
3. **인증·잔액 오류** (`400 credit balance too low`, `401 invalid api key`) — **즉시 전체 중단**. 다른 대학으로 진행 X. (POC에서 크레딧 0이었는데 60개 대학을 다 돌면 비용은 0이지만 시간·로그가 낭비.)
4. **대학 단위 게이트** — 한 대학의 LLM 실패율 ≥ 70%면 그 대학 REVIEW 큐로.

#### 신뢰도 분기
- `>= 0.9` 자동 통과
- `0.6 ~ 0.9` Validator 통과 시 PASS, 실패 시 REVIEW
- `< 0.6` 무조건 REVIEW

#### 사전 자동 업데이트 (변경 없음)
- 승인된 매핑 → `mapping_dictionary.yaml` 자동 추가
- `mapping_dictionary.history/{ts}.yaml` 백업 + 1-step revert
- 동일 표현이 다른 표준 필드로 충돌 시 자동 반영 보류 + 알림

### 3.4 Validator Agent

#### 검증 룰
1. **수치 일치성** — 정규화 후 비교 (공백·콤마·단위 제거, 소수점 2자리 통일).
2. **누락** — raw에 있는데 표준이 빈 경우만 FAIL.
3. **범위** — 등급 1.0~9.0, 비율 0~100.
4. **모집단위 수 일치** — raw 행 = 표준 행.

#### 빈 산출 하드 가드 (POC에서 신설)
v0.3에서는 records 0개도 PASS로 통과해 빈 엑셀이 산출됐다. 다음 가드 추가:
1. **records == 0** → 무조건 REVIEW (verdict 룰을 통과해도 강제).
2. **records < (raw 입결 후보 표 행수 합계 × 30%)** → REVIEW. (예: raw에 입결 row가 200개 있는데 records 40개면 의심.)
3. **records가 한 admission_type만 가지면** → REVIEW. (학생부종합·학생부교과 둘 다 있는 페이지에서 한쪽만 잡힌 경우.)

#### 출력
`{verdict: PASS | REVIEW | FAIL, summary: {records, numeric_matched, off_ratio, ...}, guards_triggered: [...], issues: [...]}`.

### 3.5 Excel Writer (변경 없음)
- 템플릿 시트 `수시`, 헤더 R1·R2 보존, **R3부터 row 누적**.
- 결측은 셀 비움.
- 입력 후 재독 검증. 불일치 시 해당 대학 REVIEW 회송.
- 기존 파일 있으면 `outputs/.backup/{unvCd}_{ts}.xlsx`로 이동 (최근 5회 보존).

### 3.6 REVIEW 시트 (변경 없음)
- 트리거: 신뢰도 < 0.6, Validator REVIEW/FAIL(가드 포함), Crawler 표 0개, Writer 재독 불일치, Mapper 대학 단위 실패율 ≥ 70%.
- 위치: `outputs/_review/{batch_id}.xlsx`.
- 컬럼: `unvCd | univName | 항목 | 웹사이트 표현 | 추정 매핑 | 신뢰도 | 스크린샷 경로 | 결정 | 사람 수정값 | 비고`.

---

## 4. 표준 데이터 스키마

```yaml
university:
  unvCd: string
  univName: string
  page_year: integer            # 어디가 진입 학년도 (예: 2027)
  collected_at: datetime

records:
  - result_year: integer        # 표에 적힌 입결 학년도 (예: 2026). page_year가 입시 전이면 page_year - 1이 정상
    admission_type: "학생부종합" | "학생부교과"      # 대분류 (Validator 가드용)
    admission_name: string        # 세부 전형명 "학생부종합(학업우수)" — 엑셀 B컬럼에 기록
    recruitment_unit: string
    quota: integer | null
    competition_ratio: float | null
    fill_rank: string | integer | null

    converted_score:            # 대학별환산
      max: float | null
      avg: float | null
      cut_50: float | null
      cut_70: float | null
      cut_80: float | null
      cut_100: float | null
      total: float | null

    grade:                      # 학생부등급
      max: float | null
      avg: float | null
      cut_50: float | null
      cut_70: float | null
      cut_80: float | null
      cut_90: float | null
      min: float | null

    criteria: string | null
    reflected_subjects: string | null

meta:
  mapper_mode: "bootstrap" | "normal"
  llm_fail_ratio: float
  confidence_scores: { ... }
  source_screenshots: [ ... ]
  validator_report: { ... }
```

---

## 5. 처리 흐름

1. **입력 로드** — 대학명/코드 리스트, 직전 회차 REVIEW 시트.
2. (대학명 입력 시) `univInfo.do`로 `unvCd` 자동 변환.
3. **대학별 루프** (병렬도 5):
   - Crawler: 페이지 진입 → 평면화 → `raw/{code}.json`
   - Mapper: 부트스트랩 또는 정상 모드 → 재시도 → `mapped/{code}.json`. 대학 단위 실패율 ≥ 70%면 REVIEW로.
   - Validator: 빈 산출 가드 + 검증 룰 → verdict
   - PASS → Writer → `outputs/{code}.xlsx`
   - REVIEW/FAIL → `outputs/_review/{batch_id}.xlsx`에 적재
4. **인증·잔액 오류** 감지 시 전체 즉시 중단 (다른 대학 진행 X).
5. 리포트 — 성공/검토/실패 건수, 신뢰도 분포, 사이트 구조 변경 알림, **LLM 실패율 분포**.

---

## 6. 리스크 대응

| 리스크 | 대응 |
|---|---|
| 대학마다 표 컬럼·명칭 상이 | 사전 + LLM 매칭 + 신뢰도 분기 |
| 새로운 표현 | REVIEW → 사전 적립 |
| 두 점수체계 혼동 (환산 vs 등급) | 표 caption + 평면화 헤더로 분류, 모호 시 REVIEW |
| 멀티헤더·rowspan 표 | Crawler 평면화 단계가 흡수 |
| 엑셀 양식 깨짐 | 헤더 보존, R3 이하만 입력, 재독 검증, 자동 백업 |
| 사이트 구조 변경 | 표 0개·헤더 해시 변경 시 즉시 알림 |
| 매핑 사전 오학습 | history 백업 + revert + 충돌 보류 |
| **LLM API 장애/잔액 부족** | 표 단위 격리, 지수 백오프 재시도, 인증·잔액 오류는 즉시 중단 |
| **빈 산출 통과** | Validator 하드 가드 3종 |
| **부트스트랩 단계 오학습** | 첫 5개 대학 강제 REVIEW |
| F(충원합격순위)·U·V 결측 | 빈칸 정책으로 흡수 |
| `page_year`에 입결이 없음 | 정상. result_year를 직전 학년도로 자동 선택 |

> **범위 외**: adiga.kr 자동화 수집의 법적·이용약관 적합성.

---

## 7. 검증 전략

- **자동**: Validator 수치 일치성 + 누락 + 범위 + **빈 산출 가드**.
- **스폿 체크**: 매 회차 무작위 N건 사람 1:1 대조.
- **누락 검증**: 입력 vs 산출 diff.
- **회귀**: raw 동일한데 표준 다르면 비결정성 의심 → 알림.

---

## 8. 운영 정책

- raw 캐시 **7일 TTL**, `--refresh`로 강제.
- 출력 백업 최근 **5회**.
- 신뢰도 평균 + LLM 실패율 트래킹 → 사전 보강·환경 점검 시점 감지.
- 대학 추가: 코드 또는 이름만 리스트에 추가 (`univInfo.do` 자동 변환).
- 새 전형 추가: Crawler에 탭, 스키마 `admission_type` 값에 추가.
- 템플릿 변경: `cell_mapping.yaml` 수정.

---

## 9. 비용·시간 추정

| 모드 | 항목 | 추정 |

|---|---|---|
| **부트스트랩** | Mapper 대학당 ~15회 LLM 호출 (사전 미사용), 호출당 3K in / 1K out (Sonnet 4.6) | ~$0.15 / 대학 |
| **정상** | Mapper 대학당 ~3회 LLM 호출 (대부분 사전 매칭) | ~$0.03 / 대학 |
| 공통 | Crawler 30~60초, Writer·Validator 5초 | |
| **1회 60개 대학 (부트스트랩)** | | ~25분, ~$9 |
| **1회 60개 대학 (정상)** | | ~20분, ~$2 |

---

## 10. POC 시행착오 기록 (v0.3 → v0.4 원인 요약)

| # | POC에서 드러난 문제 | v0.4 반영 |
|---|---|---|
| 1 | 사전이 빈 상태 → 100% LLM 의존 → 단일 장애점 | §3.3 부트스트랩 모드, 첫 5개 강제 REVIEW |
| 2 | LLM 호출 실패 시 재시도·격리 정책 부재 | §3.3 재시도, §3.1 대학 단위 게이트, §5 즉시 중단 |
| 3 | Validator가 records=0을 PASS로 처리 | §3.4 빈 산출 하드 가드 3종 |
| 4 | Crawler가 멀티헤더 표를 평면화하지 못함 | §3.2 헤더 평면화 단계 신설 |
| 5 | URL이 `univView.do`가 아니라 `univDetail.do`였고, 클릭 후 `univDetailSelection.do`로 전환 | §3.2 URL 패턴 정정 |
| 6 | `unvCd` 매핑 수단이 없었음 | §3.2 `univInfo.do` API 명시 |
| 7 | `univName`을 h1으로 잡으니 자동로그아웃 팝업 헤딩이 잡힘 | §3.2 셀렉터 필터 보강 |
| 8 | 학년도 의미 모호 (page vs result) | §1.3, §4 스키마에 분리 |
| 9 | `univName`이 우상단 인기검색·자동완성 영역에서 잘못 잡힘 (1위 검색어가 박힘) | §3.2 추출 정책 3단화: 제외 셀렉터(`#autoComplet, [class*=popular], [class*=popup]`) + 메인 컨텐츠 영역 한정 + 입력 시 `univ_name_hint` + 코드 fallback 사전 |
| 10 | Anthropic SDK가 "credit balance too low"를 `AuthenticationError`로 분류 (400/401만으로 부족) | §3.3 fatal 분류에 `AuthenticationError`, `PermissionDeniedError`, `NotFoundError` 추가 — 즉시 LLM disable |
| 11 | 사전 28개 키만으로 235 records 100% 매핑 성공 (LLM 0회) — Crawler 평면화가 정확하면 LLM 없이도 가능 | §3.3 "정상 모드 전환 조건(사전 ≥ 20)" 임계값 실측으로 검증됨 |
| 12 | (정답본 대조) 전형을 "학생부종합"으로 뭉뚱그려 (학업우수)/(계열적합)/(고른기회) 구분 안 됨 | Mapper에 `admission_name = "{type}({thead_label})"` 신설, cell_mapping B를 admission_name으로 |
| 13 | (정답본 대조) "최종등록자 환산점수"를 `converted_score.avg`로 매칭 → 환산 50/70컷이 평균칸에 (0% 일치) | 사전에서 `환산점수.50% cut→cut_50`, `70% cut→cut_70`로 정정, avg 매핑 삭제 |
| 14 | (정답본 대조) 기준(U) 컬럼 비어 있었음 | Mapper `_detect_criteria`: 헤더에 "최종등록자" 있으면 기준="최종등록자" (정답본 100% 일치) |
| 15 | (정답본 대조) 충원 1건 불일치(화공생명공학과) | **내 오류 아님** — 어디가 원문이 빈칸, 정답본이 외부 보충. 어디가 기준 추출은 정확 |

---

## 10-1. 정답본(2025_어디가입결_통합본) 대비 정확도 — 고려대 235행

| 컬럼 | 1차 | 2차(수정 후) | 비고 |
|---|---|---|---|
| 행 매칭 | 235/235 | 235/235 | (모집단위·모집인원·경쟁률) 키 |
| 전형명 세분화 | ✗ | ✓ | 정답본 분포(61/60/57/57)와 동일 |
| 모집인원·경쟁률 | 100% | 100% | |
| 학생부등급 50/70컷 | 100% | 100% | |
| 환산총점 | 100% | 100% | |
| 환산평균 | 0% (오입력) | 정정(둘 다 비움) | 환산 cut을 cut_50/cut_70으로 |
| 기준(U) | 0% | 100% | "최종등록자" |
| 충원합격순위 | 99.5% | 99.5% | 잔여 1건은 어디가 원문 빈칸 |

**정답본과 의도적으로 다른 부분 (트레이드오프):**
- **환산 cut_50/cut_70**: 정답본은 비웠으나, 양식에 칸이 있어 데이터 보존 차원에서 채움. 필요 시 비우도록 정책 선택 가능.
- **반영교과 표기**: 어디가 원문 "전체교과" 유지 (정답본은 "전교과"로 축약). 표기 정규화는 미적용.
- **바이브온_* 내부코드** (대학/전형/모집단위 코드): 정답본엔 있으나 미구현 — 별도 마스터 코드 매핑 스코프.

---

## 10-2. 멀티 대학 검증 (8개 대학, 양식 다양성 대응)

대학마다 입결 양식이 달라, 정답본 189개 대학을 5가지 양식 유형으로 분류하고 유형별 대표 8개를 검증했다.

**검증된 표 예외 케이스 (코드 커버):**
1. 컷 표기 변형(`50% cut`/`50 cut`/`50%cut`/공백구분) → `_norm` + `_CUT_RE` 정규식
2. 컷 종류(50/70/80/90/100, 평균/최고/최저) → 규칙 기반 `_match_column`
3. 종합/교과 판별 — thead 명시 > 평가반영·**지원자 분포도→종합** > 환산→교과 > 등급만→교과
4. 정시·전형방법 표 제외(`총점(수능)`·`백분위`·`선발방법`)
5. **분포도 표 + 컷 표 분리** → `_merge_records`로 (전형,모집단위) 병합 (영남대 종합 64행 복구)
6. **소수인원 안내문구**("선발인원 3명 이하 공개")의 숫자 오추출 → `_parse_num(strict=True)`로 차단
7. 미공개 `0.00` 표기 → 등급/환산 0은 결측 처리
8. 모집인원 "6이내"·충원 "통합" → 관대/엄격 파싱 분리
9. 전형명 부가설명·범례 오염 → `_clean_label`

**정답본 대조 결과 (매칭행 정확도):**

| 대학 | 양식 특징 | 매칭/records | 정확도 |
|---|---|---|---|
| 건국대 | 등급+환산 | 75/75 | 100% |
| 고려대 | 등급 위주 | 235/235 | 99.5% |
| 가천대 | 70·90컷, 환산없음 | 285/285 | 100% |
| 동국대 | 등급평균만 | 135/139 | 100% |
| 동덕여대 | 혼합 | 62/62 | 100% |
| 영남대 | 종합 분포도+교과 환산 | 332/332 | 99.4% |
| 가톨릭관동대 | 소수인원 0표기 | 102/154 | ~99%(매칭행) |
| 경기대 | 분포도+컷 분리·캠퍼스 | 140/162 | 충원·환산 100% |

**경기대 정밀 분석 (추가 수정):**
- `_clean_label` 버그 — "기회균형**선발**전형"의 "선발"을 부가설명으로 오인해 괄호 삭제 → "학생부종합"으로 뭉개짐. 트리거에서 `선발`·`반영` 제외하여 수정.
- `_is_candidate` 임계값 `data_row_count >= 3` → `>= 1`로 완화. SW우수자전형(1행) 등 소수 전형 복구. **가천대 285·영남대 332·동덕여대 62로 모두 100% 매칭** 개선.
- 경기대 기회균형 등급 18건은 **어디가 원문(공공안전 2.71)과 정답본(3.79)이 다름** — 우리 추출이 어디가에 정확, 정답본 행 밀림 의심.

**남은 한계 (정답본이 어디가와 다름 — 우리 오류 아님):**
- 경기대 기초생활수급자등(18행)은 어디가에 입결 표 없음(반영교과 설명만), 사회배려·농어촌은 어디가 모집단위가 정답본보다 적음 → 정답본 외부 보충.
- 캠퍼스 분리 대학은 본교 unvCd만으론 분교/제2캠 누락.
- 정답본이 거른 소수인원 미공개 행을 우리는 생성 → 매칭 키 어긋남(데이터는 어디가 충실).
- Validator off_ratio 임계값 0.20이 동국대(0.21)에서 과민 REVIEW → 캘리브레이션 필요.

---

## 11. 미정 항목

- [ ] 매핑 사전 초기 버전 — 부트스트랩 모드의 첫 5개 대학 산출로 자동 시드
- [ ] 신뢰도 임계값(0.9 / 0.6) — POC 데이터로 캘리브레이션
- [ ] 병렬도(5) — 실제 사이트 응답 확인 후 조정
- [ ] 사이트 변경 알림 채널 — Slack / 이메일 / 로컬 로그
- [ ] U(기준)·V(반영교과) 추출 셀렉터 — 입결 표 옆 메타 영역 확인 후 보강
