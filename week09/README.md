# W09 — 전형정보 크롤러 구축

4단계 "피드백 기반 개선·마무리" · 기간 6/26~7/2 · 진행률 9/12(75%)

W08에서 확정된 데이터랩스 백로그 **③ 전형 정보**를 구현하는 주차.
어디가 "전형정보"의 **전형일정및방법 탭 + 전형요소 탭**을 전 대학 × 전 전형 × 전 모집단위로 크롤해
데이터랩스 정제용 **raw 엑셀**(대학별 + 통합본)로 출력한다.

- 설계: [docs/design.md](docs/design.md) · 구현 계획: [docs/plan.md](docs/plan.md)
- **raw only** — 정제·해석 없음. (정제는 W11에서 별도 프로그램으로 구현)
- W05~W06 크롤러 방법론 계승: requests + BeautifulSoup, openpyxl 다단 병합헤더, resume 캐시, 병렬, 지연·브라우저헤더·서킷브레이커.

## 핵심 기술 결정 (spike로 확정)

| 항목 | 결론 |
|---|---|
| **열거는 requests 불가** | 어디가 목록 AJAX(`admssUnivAjax` → `admssUnivDetailLstAjax`)는 페이지 JS가 만드는 **서버측 세션 상태**를 요구. 동일 본문·CSRF·쿠키로도 빈 결과 → **Playwright headless**로 세션 워밍 후 열거 |
| **detail/element는 requests GET** | 풀 파라미터 URL로 무세션 조회 가능. 대량 크롤은 전부 여기서 (Playwright는 열거에만) |
| **granularity** | **전형 × 모집단위**. `comScsbjtCd` = 학과(모집단위) 코드. 예: 가천대 = 71 모집단위 × 전형 = **761 tuple** |
| **전형요소 탭** | GET이 실데이터를 정적 반환 (AJAX 아님). 단 전형 유형별로 해당 블록만 채워짐 — 논술·수능위주는 학생부 블록이 비어 표 0개 |

## 파일 구조

| 파일 | 책임 |
|---|---|
| `scripts/net.py` | 네트워크 계층 — retry + 서킷브레이커 + 지연 (week06 이식) |
| `scripts/enumerate_admissions.py` | 대학 → 전형×모집단위 열거 (Playwright 세션 워밍 + `fnDetailPage` 파싱) |
| `scripts/parse_schedule.py` | 전형일정및방법 HTML → 고정 컬럼 dict |
| `scripts/parse_element.py` | 전형요소 HTML → 평면화 dict (동적 컬럼) |
| `scripts/write_excel.py` · `write_blocks.py` | dict → 다단헤더 워크북 (대학별 + 통합) |
| `scripts/structured.py` | 구조화 포맷(3단헤더 평탄화) + 전체 실행 오케스트레이션 + 크롤링 리포트 |
| `scripts/crawl_admission.py` | 단일 대학 크롤 엔트리 |
| `tests/` | 파서 단위 테스트 + 실제 HTML 픽스처 |

파서는 `parse(html: str) -> list[dict]` 순수 함수 → 네트워크 없이 픽스처로 테스트.

## 실행

W05 venv를 공용으로 쓴다. 열거용 Playwright만 추가 설치 필요:

```bash
../week05/.venv/bin/pip install -r requirements-extra.txt
```

```bash
../week05/.venv/bin/python scripts/structured.py --all       # 전체 대학
```

```bash
../week05/.venv/bin/python scripts/structured.py --sample    # 샘플
```

```bash
../week05/.venv/bin/python scripts/structured.py --combine   # 대학별 파일 → 통합본만 재생성
```

```bash
../week05/.venv/bin/python -m pytest tests -q                # 9 passed
```

## 결과

전량 크롤 완료 (`output/crawl.log`): **220개 대학 · 65,661건 · 13시간 13분 · 실패 0**.

| 산출물 | 위치 |
|---|---|
| 대학별 엑셀 | `output/대학별/` (212개 파일) |
| 통합본 | `output/전형정보_통합.xlsx` |
| 크롤링 리포트 | `output/크롤링_리포트.xlsx` (종합·대학별·실패상세) |
| 열거 캐시 (resume용) | `output/enum/` (221개 JSON) |

> ⚠️ `output/` 의 **통합본·리포트는 이후 가천대 단독 재실행으로 덮여 있다**(가천대 761건 기준).
> 전량 기준의 정상 통합본·리포트는 **`week10/output/`** 을 보라.

## 알려진 한계 → W10에서 수정

- 220개 대학을 크롤했으나 대학별 파일은 **212개** — 출력 0행 대학이 파일 없음/빈 껍데기로 새어나감
- 리포트가 0행 출력을 성공으로 묻어 **validation이 사실상 무의미**했음

데이터랩스 피드백(*"경동대 파일이 비어있다. 이럴 거면 크롤러 리포트를 왜 작성하나"*)을 받아
W10에서 0행 대학 전수 추적 + 검증 시트를 신설했다. 상세는 [../week10/README.md](../week10/README.md).

> 관례: 주차 폴더는 이전 주차를 복사해 이어간다 (W10 = W09 복사). `week09/` 는 이 시점에 **동결**.
