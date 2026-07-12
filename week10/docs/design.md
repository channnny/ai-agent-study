# W09 — 전형정보 크롤링 초안 (설계서)

작성일: 2026-06-30 · 9주차 스터디 · 개발자 송유찬

## 1. 목표

데이터랩스 정제용 **raw 데이터 확보**. 어디가 "전형정보"에서 **모든 대학 × 모든 전형**의
전형일정·방법·전형요소를 크롤해 첨부 샘플(`가천대.xlsx`) 포맷으로 출력.

- 이번 주는 **초안 + 샘플 5개 대학**. 전량은 후속.
- **5주차 방법론 계승**: requests + BeautifulSoup 파싱, openpyxl 다단 병합헤더, resume 캐시,
  병렬, 블로킹 대비(지연·브라우저헤더·서킷브레이커). week06 크롤러 인프라 재사용.
- 정제·해석 없음(raw only). 정제는 데이터랩스가 스킬+루프로 진행.

## 2. 대상 · 엔드포인트

진입: 전형정보 (`admssUnivView.do?menuId=PCPRCINF2000`)

| 단계 | 엔드포인트 | 용도 |
|---|---|---|
| 열거 | `admssUnivDetailLstAjax.do` (POST) | 대학 → 전형 목록 HTML 프래그먼트(전형별 파라미터 포함) |
| 탭1 | `admssUnivDetail.do` (GET) | 전형일정 및 방법 |
| 탭2 | `admssUnivDetailElement.do` (GET) | 전형요소 |

전형별 파라미터: `unvCd·comScsbjtCd·slcnGroupCd·rcmtMmntCd·ruCd·ruSn·lclsfAftCd·slcnTypeCd·slcnCd·searchSyr=2027`.

## 정정 (2026-06-30, 구현 완료 기준) — 아래 §3 일부 갱신

- **열거는 requests 불가, Playwright 필수**: 어디가 목록(`admssUnivAjax`→`admssUnivDetailLstAjax`)은
  페이지 JS가 만드는 **서버측 세션 상태**를 요구. 동일 본문·CSRF·쿠키로도 빈 결과(브라우저 in-page
  fetch는 동일 요청에 200/데이터 반환 — 세션 바인딩 확정). → `enumerate_admissions.fetch_units()`가
  **Playwright headless**로 세션 워밍 후 열거. (§3.1의 requests 3단계는 폐기.)
- **granularity = 전형×모집단위 전체** (사용자 결정). `comScsbjtCd = 학과(모집단위) 코드`.
  열거: 대학검색 → `admssUnivAjax` 페이지네이션으로 학과(comScsbjtCd) 수집 → 학과별 `LstAjax` →
  전형 sub-행(`fnDetailPage` 9인자) = (전형×모집단위). 가천대 = **71 모집단위 × 전형 = 761 tuple**.
- **detail/element는 requests GET(무세션)** 그대로 — 풀 파라미터 URL로 조회. 대량 크롤은 여기서.
- **이번 주 스코프 = 가천대 단독** (5개 대학 아님). 검증: 761행 전형일정 / 2556행 전형요소, 샘플 포맷 일치.

## 3. 정찰 결과 (2026-06-30, spike 확정)

- **전형일정및방법**(`admssUnivDetail.do`): GET 서버렌더, 표 5개
  (`전형일정`·`전형 요소별 반영비율`·`지원자격 및 기타`·`최저학력기준`·성적분석팝업[무시]).
  샘플 23열은 앞 2개 표에서 추출 (§5.1 매핑). 정적 파싱 OK.
- **전형요소**(`admssUnivDetailElement.do`): **GET이 실데이터를 정적 반환** —
  AJAX 후행 로드 아님(정찰 초안의 "AJAX 의심"은 오진). 단 전형 유형별로 해당 블록만 채워짐:
  학생부 반영 있는 전형(학생부교과/종합 등)은 `div.admssDtlSection` 안에
  `학생부 학년별/요소별 반영비율`·`학생부 교과성적 반영방법` 표가 채워지고,
  **논술·수능위주 전형은 학생부 블록이 비어** 본문 표 0개(성적분석 팝업만).
  → 파서는 `div.admssDtlSection table`만 평면화, 성적분석 팝업 표는 제외.
- **전형 열거**: 전형 목록·대학 카드 모두 AJAX. 확정 흐름 (§3.1):
  ① `admssUnivView.do` GET(쿠키+`#frm` 폼) →
  ② `admssUnivAjax.do` POST(`#frm` serialize + `searchUnvCode=<unvCd>`) → 대학 카드(`comScsbjtCd` 획득) →
  ③ `admssUnivDetailLstAjax.do` POST(`#frm` serialize + `unvCd`·`comScsbjtCd`) → 전형행 프래그먼트.

### 3.1 전형 열거 POST 파라미터셋 (확정)

`#frm`(id=`frm`) hidden 필드 전체를 jQuery `.serialize()`와 동일하게 직렬화
(체크박스/라디오는 checked만 — 정적 진입 시 거의 없음) 후 아래만 덮어쓴다.

| 키 | 값 | 출처 |
|---|---|---|
| `searchSyr` | `2027` | 진입 URL 쿼리(폼에 이미 설정됨) |
| `unvCd` | 대학코드 (예 `0000063`) | 타깃 대학 |
| `comScsbjtCd` | 예 `0055681` | **②단계 `admssUnivAjax.do` 응답** li 요소 `comscsbjtcd` 속성 |
| `cnrtYear` | `2026` | 폼 기본값 (변경 금지) |
| `menuId` | `PCPRCINF2000` / `unvSeCd`=`10` | 폼 기본값 |

- `comScsbjtCd`를 비우고 POST하면 `{"error":{"code":"041","message":"잘못된 매개 변수입니다."}}`.
  따라서 **②단계(UnivAjax)로 comScsbjtCd를 먼저 얻는 것이 필수**.
- ②단계 요청도 `#frm` serialize에 `searchUnvCode=<unvCd>` 한 줄 추가하면 됨.
- 공통 헤더: 최신 UA·`Accept-Language: ko-KR`·`X-Requested-With: XMLHttpRequest`·
  `Referer: <admssUnivView URL>`·`Origin: https://www.adiga.kr`. 요청 간 1s+ 지연.

### 3.2 전형행 파라미터·전형명 추출 (확정)

LstAjax 프래그먼트는 `div#tbResultSlcn` 안에 전형행 16개(가천대). 각 행:

- **전형명**: `a.selectUnivComScsbjtCd` 텍스트 (예 `논술위주 > 논술위주(논술)`).
- **파라미터**: 동일 `a`의 `onclick="fnDetailPage(...)"` 인자 9개를 정규식으로 추출
  (HTML 엔티티 `&quot;` 디코드·공백 제거 필요). 인자 순서:
  `fnDetailPage(unvCd, comScsbjtCd, slcnGroupCd, rcmtMmntCd, ruCd, ruSn, lclsfAftCd, slcnTypeCd, slcnCd)`.
  정규식: `fnDetailPage\(([^)]*)\)` → unescape → 쉼표 split → 각 토큰 `strip('"')`·공백제거.
  (예시 가천대 논술행이 `0247247,111786,...,04,01`로 task 예시와 정확히 일치 검증됨.)

## 4. 아키텍처

```
대학(샘플 5)
  └▶ [열거] admssUnivDetailLstAjax → 전형 목록(+파라미터)
        └▶ 각 전형
             ├▶ [parse_schedule] admssUnivDetail.do      → 고정 23열 스키마 행
             └▶ [parse_element]  admssUnivDetailElement   → raw 평면화 행
        └▶ 대학별 워크북(탭2: 전형일정및방법 / 전형요소)
  └▶ 통합 워크북(전체 대학, 대학명 열)
```

### 모듈 (`week10/scripts/`)

| 파일 | 책임 | 의존 |
|---|---|---|
| `crawl_admission.py` | 메인 — 열거·병렬·resume 캐시·리포트 (week06 골격) | 아래 전부 |
| `enumerate_admissions.py` | 대학 → 전형 목록+파라미터 (LstAjax 프래그먼트 파싱) | requests, bs4 |
| `parse_schedule.py` | 전형일정및방법 페이지 → 고정 23열 스키마 dict | bs4 |
| `parse_element.py` | 전형요소 페이지 → raw 평면화 dict(동적 컬럼) | bs4 |

각 모듈 단일 책임. 파서는 HTML(str)→레코드(dict) 순수 함수로 테스트 가능.
네트워크 계층(`_request`: retry+서킷브레이커+지연)은 week06에서 그대로 이식.

## 5. 출력 스키마

**탭1 전형일정및방법** — 샘플 고정 superset(23열):
- ID: 대학명 · 전형명 · 모집단위명
- 전형일정: 원서접수[인터넷·현장] · 대학별고사일정[논술등필답·면접구술·실기] · 합격자발표일
- 전형요소별 반영비율: 선발모형 · 선발방법 · 선발비율(%) ·
  반영비율[학생부·수능·면접·논술·적성·1단계성적·실기·서류·기타] · 기타내용
- 없는 값은 빈칸. 4단 병합헤더(openpyxl).

### 5.1 탭1 23열 → 페이지 매핑 (spike 확정)

`admssUnivDetail.do` 앞 2개 표 헤더가 샘플 23열과 일치:
- **`전형일정` 표**: 원서접수[인터넷·현장] · 대학별고사일정[논술등 필답·면접구술·실기] · 합격자발표일.
  데이터행 셀 텍스트 그대로(예 `1차 : 2026-11-30 ~ 2026-11-30`) — 1·2단계 등 다단 발표 가능.
- **`전형 요소별 반영비율` 표**: 선발모형 · 선발방법 · 선발비율(%) ·
  반영비율[학생부·수능·면접·논술·적성·1단계성적·실기·서류·기타] · 기타내용.
  (없는 요소는 빈 셀.)
- ID 3열(대학명·전형명·모집단위명)은 열거 단계 + 페이지 상단(`div.selectionInfo`)에서.

**탭2 전형요소** — 페이지 표/항목 **그대로 평면화**(컬럼 동적). 정규화·해석 안 함.
대상: `div.admssDtlSection` 내 `table`만 (각 표 `<caption>`이 표 이름).
가천대 학생부교과 기준 2표: `학생부 학년별/요소별 반영비율`(졸업년도×학년별·요소별 %),
`학생부 교과성적 반영방법`(반영교과·과목·산출지표). **성적분석 팝업 표(`pFrm`/`catAdmissSelPop`)는 제외.**
**전형요소가 비는 전형(논술·수능위주 등)은 탭2 행 없음/빈칸 — 정상.**

**출력 파일**:
- `week10/output/대학별/<대학명>.xlsx` (탭2개)
- `week10/output/전형정보_통합.xlsx` (전체 대학, 대학명 열 추가)

## 6. 샘플 대학

랜덤 5개 대학, 각 대학의 **모든 전형**. (예시 가천대·가야대 포함 가능)
대학 코드 풀은 week03 `target_universities.csv` 재사용.

## 7. 블로킹 대비 (week06 계승)

요청 간 지연 0.3~0.8s 지터 · 브라우저 헤더(최신 UA·Accept-Language) ·
연속 실패 8회 서킷브레이커(차단 의심 시 fail-fast) · 429 Retry-After 존중 · resume 캐시.

## 8. Phase 0 — Spike (완료 2026-06-30)

가천대(0000063)로 정찰 완료. 결과는 §3.1·§3.2·§5.1 반영.

1. **전형 열거 확정 ✅**: 2단계 AJAX(UnivAjax로 comScsbjtCd 획득 → LstAjax) →
   전형행에서 `fnDetailPage(...)` onclick 9인자 정규식 추출. §3.1·§3.2.
2. **전형요소 구조 확정 ✅ (폴백 불필요)**: 단순 GET이 실데이터 반환(AJAX 아님).
   학생부 반영 있는 전형은 `div.admssDtlSection table` 채워짐 → 평면화 가능.
   논술·수능위주 등은 전형요소가 본래 비어있음(데이터 없음 = 정상, 누락 아님).

→ **두 spike 모두 성공. 본 설계 확정.** 탭1·탭2 모두 이번 주 진행.

### 8.1 저장 픽스처

- `tests/fixtures/enum_가천대.html` — LstAjax 전형행 프래그먼트(전형 16개).
- `tests/fixtures/element_가천대학생부교과.html` — 전형요소 **실데이터**(반영비율 2표).
  ※ task 지정 `element_가천대논술.html` 대신 학생부교과로 저장 — 가천대 논술은
  전형요소가 실제로 비어 있어(데이터 표 0개) 실데이터 픽스처가 될 수 없기 때문.
- `tests/fixtures/schedule_가천대논술.html` — 전형일정및방법(표 5개).

**폴백(탭1만)은 채택하지 않음** — 전형요소 실데이터 확보 성공.

## 9. 검증

- 샘플 5대학 크롤 완료, 0 error (또는 사유 명시).
- **가천대 출력 탭1**이 첨부 `가천대.xlsx` 탭1 스키마(23열)와 컬럼 일치.
- 전형요소 탭 raw 채워짐(폴백 시 제외 사유 기록).
- 파서 단위 테스트: 저장된 HTML 픽스처 → 기대 레코드.

## 10. 비대상 (후속)

- 전량(모든 대학) 크롤 — 샘플 검증 후.
- 전형요소 정규화/LLM 정제 — 데이터랩스 영역.
- W08 3대 정제 산출물(최저·교과반영·학년별비율) — raw 확보 후 별도 주차.
