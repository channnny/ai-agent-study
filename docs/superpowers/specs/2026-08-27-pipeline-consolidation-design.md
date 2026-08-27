# 어디가 파이프라인 통합 설계 (crawler / refiner)

- 작성일: 2026-08-27
- 범위: W01~W11에 흩어진 크롤링·정제 코드를 두 개의 운영 프로젝트로 통합, 스펙 변동 대응 문서화, GitLab CI 파이프라인 구축
- 근거: 2026-08-27 코드베이스 전수 조사(진입점·하드코딩·테스트 자산). 이 문서의 모든 `file:line` 은 조사에서 실제 확인된 값이다.

---

## 1. 배경과 목표

### 현재 상태

크롤링·정제 코드가 주차 폴더에 분산되어 있고, 같은 일을 하는 코드가 세대별로 중복 존재한다.

| 자산 | 위치 | 규모 | 상태 |
|---|---|---|---|
| 전형정보 크롤러 | `week10/scripts/` | 16파일 2,399줄 | **현행 운영** |
| 전형정보 정제기 | `week11/scripts/refine/` | 10파일 ~1,000줄 | **현행 운영** |
| 입결 크롤러 트랙A | `week03/crawl_adiga.py` | 352줄 | 레거시 |
| 입결 크롤러 트랙B | `week06/scripts/crawl_2027_detail.py` | 449줄 | 실행 이력 있음 |
| 입결 정제기 | `week05/src/`, `week06/src/` | ~2,300줄 | 아카이브 대상 |

문제는 세 가지다.

1. **실행이 사람 손에 묶여 있다.** 전 진입점이 `cd weekXX && ../week05/.venv/bin/python scripts/...` 형태다. 공용 venv를 빌려 쓰고, 주차 폴더 밖에서는 돌지 않는다.
2. **스펙이 코드에 박혀 있다.** 연도(`SYR = "2027"`)가 5개 파일에, RAW 컬럼 인덱스가 정수 리터럴로 `cols.py` 전역에, 산출물 경로가 `/Users/channy/Downloads/...` 절대경로로 박혀 있다.
3. **품질 게이트가 수동이다.** 골든셋 정합률 99.98%는 재현 가능한 프로그램(`report.py`)으로 측정되지만, 입력 2개가 레포 밖 미추적 파일이라 CI에서 돌릴 수 없다.

### 목표

- 운영 코드를 `crawler/` · `refiner/` 두 프로젝트로 통합하고, 주차 폴더는 아카이브로 보존한다.
- 연도·사이트구조·스키마 세 종류의 스펙 종속을 각각 다른 계층에 격리한다.
- GitLab CI에서 수집·정제·검증을 실행할 수 있게 한다.
- 리팩터링이 산출물을 바꾸지 않았음을 증명한다.

### 비목표

- 입결 정제(`week05/src`, `week06/src`) 이관. 아카이브로 남긴다.
- 크롤 성능 개선. 현재 동시성(6)을 유지한다.
- DB 저장. W06 이후 드롭된 방향이며, 관련 코드는 이미 죽어 있다(4절 참조).

---

## 2. 조사에서 드러난 사실

설계 판단의 근거다. 추정이 아니라 확인된 것만 적는다.

### 2-1. 입결 크롤러는 두 트랙이고, 하나가 명백히 낫다

같은 "입결"이지만 서로 다른 어디가 화면을 긁는다.

| | 트랙 A | 트랙 B |
|---|---|---|
| 코드 | `week03/crawl_adiga.py` + `week06/scripts/crawl_2027_full.py` | `week06/scripts/crawl_2027_detail.py` |
| 엔드포인트 | `univDetailSelection.do` + `criteriaAndResultItemNewAjax.do` | `classUnivAdmssPopup.do` |
| 데이터 형태 | 대학마다 제각각인 아코디언 표, rowspan/colspan 평탄화 필요 | **80열 전국 공통 표준 양식** |
| 교차검증 | 없음 | **어디가 총건수 대비 크롤 건수 검증 리포트 생성** |
| 표가 아닌 경우 | 이미지 다운로드 + `OCR_REQUIRED.txt` 마커 | 해당 없음 |
| 실행 이력 | `week03/output` 존재 | `.progress` 437개, `detail/` 217개 폴더 — 전량 실행 확인 |
| 산출물 | 대학별 xlsx | 대학별 xlsx + 전체 통합본 + 크롤링 리포트 |

**결정: 트랙 B만 이관한다.** 트랙 A는 아카이브. 표준 양식 + 교차검증이 있는 쪽이 정제 하류 공정에 압도적으로 유리하다. 트랙 A의 `_table_to_grid` / `_flatten_table` 유틸은 트랙 B가 실제로 import해 쓰고 있으므로(아래) 그 두 함수만 신규 프로젝트로 옮긴다.

### 2-2. 주차 간 재사용이 `sys.path` 조작과 monkey-patch로 되어 있다

```
crawl_2027_full.py:15-19    sys.path.insert(week03); import crawl_adiga as C
crawl_2027_full.py:22       C.OUTPUT_DIR = week06/output/crawl_2027_full   ← 모듈 전역 변조
crawl_2027_detail.py:37-41  sys.path.insert(week03) + sys.path.insert(scripts/)
build.py:13 / report.py:21 / tests/test_refine.py:8   각각 경로 주입
```

`crawl_2027_full`은 `C.save_to_excel`이 모듈 전역 `OUTPUT_DIR`를 읽는다는 사실에 의존한다. 정식 패키지로 바꾸면 이 암묵적 결합이 가장 먼저 깨진다.

`crawl_2027_detail`이 트랙 A에서 실제로 쓰는 것은 5개뿐이다: `BASE_URL`, `INPUT_FILE`, `_table_to_grid`, `_flatten_table`, `get_university_name`. 네트워크 계층·배치·저장은 전부 자체 구현(서킷브레이커, 429 Retry-After, 3회 재시도, resume 캐시)이다.

부수효과: `import crawl_adiga` 만으로 `week03/output` 디렉터리가 생성된다.

### 2-3. DB 코드는 이미 죽어 있다

`week03/crawl_adiga.py`에 `--db` 플래그와 MariaDB 저장 경로가 있으나, `week05/.venv` 에 `pymysql` / `mariadb` / `mysql-connector` / `SQLAlchemy` 가 **전부 미설치**다. requirements 파일에도 없다. 실행하면 즉시 ImportError. 이관 대상에서 제외한다.

### 2-4. 전체 크롤 시간은 enum 캐시 유무로 두 배 이상 갈린다

| 조건 | 소요 |
|---|---|
| `structured.py --all`, enum 캐시 있음 | **3시간 47분** (실측, 220대학 66,422유닛 → 45,376행) |
| enum 캐시 없음(콜드 스타트) | 열거만 대학당 35~65초 × 220 ≈ **+2.5~3시간** → 총 **6~7시간** |
| `--combine` 단독 | ~100초 |

CI timeout 설계에 직결된다. 캐시 있을 때 기준으로 잡으면 콜드 스타트에서 죽는다.

### 2-5. 골든셋 검증은 재현 가능하지만 CI에서 못 돌린다

`refine/report.py`는 일회성 스크립트가 아니라 `build(in, gold, out)` + CLI 인자를 갖춘 프로그램이다. 실행 검증됨:

```
7.18초 | 골든고유키 6,472 / 조인 6,361 / 모집단위개편 대조불가 111
        / 원본결손 평가제외 10 / 평가대상 6,351 / 일치 6,350 (99.98%) / 불일치 1
```

문제는 기본 입력 두 개가 레포 밖이라는 것이다.

```
report.py:24  DEF_IN   = /Users/channy/Downloads/통합본/260825/전형정보_통합_정제.xlsx
report.py:25  DEF_GOLD = /Users/channy/Downloads/어디가 골든셋/2027_최저관련_정제_0715_일단최종5시.xlsx
report.py:26  DEF_OUT  = /Users/channy/Downloads/통합본/260825/정제_검토필요_정합성검증.xlsx
```

경로에 크롤 스냅샷 날짜(`260825`)와 골든셋 스냅샷 날짜(`0715`)가 매몰돼 있다. **골든셋을 레포에 넣지 않으면 CI 게이트는 불가능하다.**

### 2-6. 기본 출력이 실산출물을 덮어쓴다 — 실제로 발생함

조사 중 `build.py`를 인자 없이 실행해 `week11/output/전형정보_통합_정제.xlsx`(34MB, 7/13 산출물)가 50행짜리로 덮어써지는 사고가 있었다. `~/Downloads/통합본/260713/`의 동일 파일로 복구했고 `shasum 338815f9...` 일치 확인했다.

이건 설계 결함의 실증이다. `build.py`, `review.py`, `sample_review.py` 모두 **기본 출력이 실산출물 경로**이고, `review.py`·`sample_review.py`는 출력 경로 CLI 오버라이드조차 없다. 신규 설계에서 반드시 막는다.

### 2-7. 테스트 자산은 있지만 그대로는 CI 게이트가 안 된다

| 위치 | 케이스 | 네트워크 | pytest | 비고 |
|---|---:|---|---|---|
| `week05/tests/` | 33 | 불필요 | ✅ | 입결 정제(아카이브 대상) |
| `week06/tests/` | 21 | 불필요 | ✅ | 입결 정제(아카이브 대상) |
| `week09/tests/` | 9 | 불필요 | ✅ | HTML fixture 기반 |
| `week10/tests/` | 9 | 불필요 | ✅ | **week09와 파일 바이트 동일** |
| `week11/tests/test_refine.py` | 6함수/36 assert | 불필요 | ✅ | 서드파티 의존 0 |
| `week10/scripts/test_validation.py` | 2함수/8 assert | 불필요 | ❌ **2 errors** | 스크립트로만 실행 가능 |

두 가지 문제가 있다.

- `week09/tests` 와 `week10/tests` 는 파일이 바이트 동일한데 **검증 대상 구현이 갈라져 있다**(`net.py`·`enumerate_admissions.py`·`structured.py`·`write_blocks.py` 가 서로 다름). 같은 테스트가 서로 다른 코드를 통과시키고 있다.
- `test_validation.py` 는 pytest로 돌리면 에러가 난다. 크롤 검증 회귀 테스트로서 가치가 큰데(경동대 빈 파일 결함의 재발 방지) CI에 못 넣는다.

pytest 설정 파일(`pytest.ini` / `conftest.py` / `pyproject.toml`)은 **레포에 존재하지 않는다**.

### 2-8. 하드코딩 인벤토리 (이관 시 전부 처리 대상)

**연도**

```
week10/scripts/structured.py:24            SYR = "2027"
week10/scripts/structured.py:505           ident_vals = [selcntnm, SYR, ...]   ← 학년도 컬럼 값이 됨
week10/scripts/crawl_admission.py:32,58    SYR = "2027" / cnrtYear = "2026"
week10/scripts/write_blocks.py:25          SYR = "2027"
week09/scripts/enumerate_admissions.py:103 fetch_units(..., syr="2027")
week06/scripts/crawl_2027_detail.py:181    searchSyr: "2027"
week06/scripts/crawl_2027_detail.py:210    searchSyr = str(int(syr) - 1)   ← 팝업은 2026, 메인은 2027
```

마지막 줄이 함정이다. 어디가는 화면마다 연도 기준이 다르다(검색연도 vs 학년도). 설정 하나로 뭉뚱그리면 안 된다.

**스키마 (컬럼 인덱스)**

```
refine/cols.py:7    S1_SEL_MODEL,S1_SEL_METHOD,S1_SEL_RATE = 14,15,16
refine/cols.py:8    S1_RB = {학생부:17, 수능:18, ... 기타:25}
refine/cols.py:10   S1_CHOI_영역수=44, S1_CHOI_세부=45
refine/cols.py:11   S1_국=35, S1_수=37, S1_영=39, S1_탐=40, S1_탐과목=41, S1_한=43
refine/cols.py:14   S2_학년공통=33 ~ S2_3학년=37
refine/cols.py:15   S2_요소 = {교과:38, ... 기타:43}
refine/cols.py:16   S2_서류학생부=44, S2_반영교과=49, S2_진로선택=52, S2_각주=54
refine/choi.py:237  모집 = c(s1[6])         ← cols.py 상수 아닌 리터럴 6. 이관 시 누락 위험
refine/build.py:87  r2 = m2.get(r1[0], [None]*55)   ← 시트2 폭 리터럴
tests/test_refine.py:18   s1() 46칸 / s2() 55칸   ← 스키마 변경 시 테스트가 조용히 어긋남
week10/scripts/structured.py:47,51,97   N_IDENT=8, _SCHED_HEADERS 39열, _ELEM_HEADERS 47열 순서 고정
```

**어디가 UI 문구 종속**

```
refine/cols.py:4   PLACEHOLDER = "대학에서 입력된 정보가 없습니다."
```

`c()` 가 이 문자열을 빈값으로 정규화한다. 어디가가 문구를 바꾸면 전 규칙이 동시에 오작동한다. 조사 과정에서 이 문구는 실제 원본 결손 판정의 근거로도 쓰였다(검토필요 10건).

**규칙 내부 순서 의존**

```
refine/choi.py:197  _GYE_RULES — 인문/자연 계열 추정 키워드 3블록(~90개 학과명)
```

순서가 의미를 갖는다. `의류환경학과`가 `환경`(자연) 키워드에 먼저 걸리면 오분류된다. 인문 키워드 블록이 앞에 있어야 한다.

**전역 변조**

```
refine/report.py:28   import 시점에 review.POLICY 딕셔너리를 변조
```

`report.py`를 import하는 것만으로 `review.py`의 동작이 바뀐다.

**일회성 복구 스크립트 4개** — 대상 대학 코드가 소스에 박혀 있다.

```
recover_campuses.py    열거 0건 9개 대학       실측 1,088초
recover_campuses2.py   과소열거 11개 대학      실측 1,126초
recover_campuses3.py   스냅샷 시점차 6개 대학  실측 575초
recover_blank_choi.py  최저 공란 3개 대학      OUT 앵커가 다른 셋과 다름(parents[1])
```

넷 다 로직이 같다. 신규 프로젝트에서는 `python -m crawler selection --univ <코드들>` 파라미터 하나로 대체한다.

---

## 3. 아키텍처

### 3-1. 리포지토리 배치

```
ai-agent-study/
├─ crawler/                  프로젝트 1 — 수집
├─ refiner/                  프로젝트 2 — 정제
├─ shared/                   공통 최소 (설정 로더 · 로깅 · xlsx 스타일)
├─ config/
│   ├─ 2027.yaml             연도별 설정
│   └─ README.md             연도 전환 체크리스트
├─ docs/                     루트 문서
├─ tests/fixtures/           골든셋 · 소형 통합본
├─ week01~week11/            아카이브. 손대지 않음
├─ pyproject.toml
└─ .gitlab-ci.yml
```

`shared/` 에는 **도메인 지식이 없는 것만** 넣는다. 어디가 관련 코드는 절대 들어가지 않는다. 이 경계가 흐려지면 모노레포의 의미가 사라진다. 구체적으로는 설정 로딩, 로그 포맷, 엑셀 스타일 상수(`GRP_FILL=2E75B6`, `HEAD_FILL=1F4E78`, `RAW_FILL=FFF2CC`, `REF_FILL=E2EFDA`, `COL_WIDTHS`, freeze 규칙)다. 이 상수들은 현재 `refine/build.py:32` 와 `week10/scripts/structured.py` 양쪽에 중복돼 있다.

### 3-2. crawler/

```
crawler/
├─ adiga/                어디가 접근 — 사이트 구조가 바뀌면 여기만 고친다
│   ├─ client.py             세션 · 재시도 · 서킷브레이커 · 429 Retry-After
│   ├─ endpoints.py          URL과 파라미터 스펙 전부. 화면별 연도 기준 차이도 여기
│   └─ browser.py            Playwright 열거 (세션 종속 POST)
├─ parse/                HTML → dict — 셀렉터가 전부 여기
│   ├─ selectors.py
│   ├─ grid.py               _table_to_grid / _flatten_table (트랙 A에서 이관)
│   ├─ selection.py          전형정보
│   └─ result.py             입결 (트랙 B, 80열 표준 양식)
├─ model/                @dataclass — 컬럼 인덱스 대신 필드명
│   ├─ unit.py               Unit(unv_cd, com_scsbjt_cd, slcn_group_cd, ...)
│   └─ row.py                ScheduleRow(39필드) / ElementRow(47필드)
├─ collect/              오케스트레이션 — 동시성 · 캐시 · 재개 · 진행 로그
│   ├─ enumerate.py
│   ├─ selection.py
│   └─ result.py
├─ write/
│   ├─ xlsx.py               대학별 · 통합본
│   └─ report.py             크롤링 리포트 4시트 (종합/대학별/검증/실패상세)
├─ CLAUDE.md
├─ docs/site-changes.md
└─ cli.py
```

**엔드포인트 5종을 `endpoints.py` 한 곳에 모은다.**

| 용도 | URL | 메서드 |
|---|---|---|
| 전형 열거 | `ucp/prc/uni/admssUnivAjax.do` | POST (세션 종속) |
| 전형 상세 | `ucp/prc/uni/admssUnivDetail.do` | GET |
| 전형 요소 | `ucp/prc/uni/admssUnivDetailElement.do` | GET |
| 입결 팝업 | `ucp/cls/uni/classUnivAdmssPopup.do` | POST |
| 입결 아코디언 | `uct/acd/ade/criteriaAndResultItemNewAjax.do` | POST (트랙A, 아카이브) |

### 3-3. refiner/

```
refiner/
├─ read/
│   ├─ schema.py         헤더명 → 컬럼 인덱스 자동 매핑, 불일치 시 즉시 중단
│   └─ loader.py         통합본 → model
├─ core/                 순수 함수. 엑셀 I/O 없음
│   ├─ registry.py       @preprocess / @condition 등록
│   ├─ choi/             ①② 수능최저
│   │   ├─ patterns.py     공유 정규식 (_hab, _P_CNT, _P_PAREN, ...)
│   │   ├─ pre_*.py        A 계열오탐 · B 블록분기 · G 불릿 · J 최저아님
│   │   └─ cond_*.py       F · C · E1 · HAB · MODU · D · H · OR
│   ├─ gyogwa.py ③   jinro.py ④   ratio.py 5a/5b   jonghap.py
├─ qa/
│   ├─ golden.py         골든셋 대조 → 정합률
│   ├─ review.py         검토필요 시트
│   ├─ report.py         통합 리포트 3시트
│   └─ sample.py         층화표본 검수 시트
├─ write/xlsx.py
├─ CLAUDE.md
├─ docs/rules.md
└─ cli.py
```

**핵심: 규칙 레지스트리를 두 종류로 나눈다.**

현재 `choi.py`의 규칙 A~J는 형태가 두 가지다.

| 종류 | 규칙 | 시그니처 | 현재 위치 |
|---|---|---|---|
| **preprocess** | A 계열오탐 · B 블록분기 · G 불릿 · J 최저아님 | 텍스트를 자르거나 조기 반환 | `refine_choi` 앞부분 if 덩어리 |
| **condition** | F · C · E1 · HAB · MODU · D · H · OR | `(txt, ctx) → (N, M) \| None`, 우선순위대로 시도 | `_cond()` 안의 순차 8단 |

`_cond()`는 이미 우선순위 레지스트리다. 그대로 뽑아낸다.

```python
# refiner/core/choi/cond_each.py
from ..registry import condition

@condition("F", order=10)          # N개 영역 각 M등급 → N합(N×M)
def each_grade(txt, ctx):
    ...
    return (n, n * g)              # 또는 None
```

```python
# refiner/core/choi/__init__.py
for rule in registry.ordered():
    if hit := rule(txt, ctx):
        return hit
```

규칙 추가가 **파일 하나 + 테스트 하나**로 끝난다. `choi.py` 318줄을 열 필요가 없고 리뷰 단위가 작아진다. 정제 규칙은 계속 늘어나는 자산이다 — 216건을 규칙 10개로 잡았고 다음 해에 새 패턴이 또 나온다.

공유 정규식(`_hab`, `_P_CNT`, `_P_PAREN`, `_P_SANGWI`)은 `patterns.py`에 두어 규칙 파일끼리 의존하지 않게 한다.

### 3-4. 스펙 종속의 계층 격리

| 종속 | 격리 위치 | 바뀌면 고칠 곳 |
|---|---|---|
| 연도 | `config/<year>.yaml` | 설정 파일 하나 |
| 사이트 구조 | `crawler/adiga/endpoints.py`, `crawler/parse/selectors.py` | 두 파일 |
| RAW 스키마 | `refiner/read/schema.py` (헤더명 매핑) | 매핑 테이블 |
| 어디가 UI 문구 | `config/<year>.yaml` 의 `placeholder` | 설정 |
| 정제 규칙 | `refiner/core/choi/cond_*.py` | 규칙 파일 추가 |

**`config/2027.yaml` 초안**

```yaml
year:
  search_syr: "2027"        # admssUnivAjax / admssUnivDetail 계열
  cnrt_year: "2026"         # 학년도. 팝업 화면이 이 값을 씀
  label: "2027"             # 산출물 '학년도' 컬럼 값

crawl:
  workers: 6                # 어디가 부하. 올리기 전 반드시 검증
  delay_range: [0.3, 0.8]
  circuit_threshold: 8
  retry: 3

source:
  placeholder: "대학에서 입력된 정보가 없습니다."

qa:
  golden: tests/fixtures/golden_2027.xlsx
  min_match_rate: 99.9
  max_review_items: 15
```

`search_syr` 와 `cnrt_year` 를 분리한 이유는 2-8절의 함정 때문이다. 어디가는 화면마다 연도 기준이 다르다.

### 3-5. 스키마 자동 매핑

`cols.py`의 정수 리터럴을 헤더명 기반으로 바꾼다.

```python
# refiner/read/schema.py
SHEET1 = {
    "선발모형":       ("전형 요소별 반영비율", "선발모형", "선발모형"),
    "최저_영역수":    ("최저학력기준", "반영영역수", None),
    "최저_세부":      ("최저학력기준", "세부내용", None),
    ...
}

def resolve(ws) -> dict[str, int]:
    """3단 헤더를 읽어 논리명 → 0-based 인덱스. 하나라도 못 찾으면 SchemaError."""
```

찾지 못한 컬럼이 있으면 **즉시 중단**한다. 조용히 `None`을 반환하면 정제가 전 행에서 틀린 답을 내놓는데, 이건 플래그에도 안 잡힌다. 열 순서가 바뀌었을 때 가장 위험한 실패 양상이다.

---

## 4. GitLab CI

### 4-1. 러너 전제

전용 러너를 쓴다.

```toml
[[runners]]
  name = "adiga-crawl"
  maximum_job_timeout = 32400        # 9h
```

잡 `timeout:` 은 러너 상한을 넘을 수 없다. 이 값이 없으면 잡에 `timeout: 8h`를 써도 잘린다. 8시간이 아니라 9시간으로 잡는 이유는 콜드 스타트 실측 상한이 7시간이기 때문이다(2-4절).

stage를 나누는 목적은 timeout 회피가 아니다. (a) MR마다 5분 내 피드백, (b) 네트워크 필요한 잡 격리, (c) 실패 지점 구분 — 이 셋이다.

### 4-2. 파이프라인

```yaml
stages: [lint, test, refine, verify, crawl]

default:
  image: python:3.11-slim
  before_script: [pip install -e ".[dev]"]

# ── 자동: MR·push마다. 합쳐서 5분 이내 ──
lint:
  stage: lint
  script: [ruff check ., ruff format --check .]

unit:
  stage: test
  script: [pytest -q --junitxml=report.xml]
  artifacts: { reports: { junit: report.xml } }

refine:fixture:
  stage: refine
  script:
    - python -m refiner build --in tests/fixtures/전형정보_통합_small.xlsx --out output/ci/
  artifacts: { paths: [output/ci/], expire_in: 1 week }

golden:gate:
  stage: verify
  script:
    - python -m refiner qa golden --in output/ci/ --min-rate 99.9 --max-review 15

# ── 수동: 네트워크 필요. 전용 러너 ──
crawl:partial:
  stage: crawl
  tags: [adiga-crawl]
  when: manual
  timeout: 1h
  variables: { UNIV_CODES: "" }          # 예: 0000003,0000007,0000023
  script: [python -m crawler selection --univ "$UNIV_CODES"]
  artifacts: { paths: [output/], expire_in: 30 days }

crawl:full:
  stage: crawl
  tags: [adiga-crawl]
  image: mcr.microsoft.com/playwright/python:v1.4x-jammy
  when: manual
  timeout: 8h
  resource_group: adiga-crawl            # 동시 실행 차단
  cache:
    key: adiga-$CRAWL_YEAR
    paths: [output/enum/, output/대학별/]
  script: [python -m crawler selection --all]
  artifacts:
    paths: [output/전형정보_통합.xlsx, output/크롤링_리포트.xlsx]
    expire_in: 90 days
```

`rules:changes` 로 `crawler/**` 를 건드리지 않은 MR에서는 크롤 잡을 숨긴다.

### 4-3. `resource_group` 이 필요한 이유

빼먹으면 두 사람이 동시에 ▶ 를 눌러 어디가에 2배 부하가 간다. 차단당하면 전체가 멈춘다. 현재 동시성 6으로 4시간 무사고인 것 말고는 안전 여유에 대한 근거가 없다.

### 4-4. `cache:` 가 재개의 전부다

CI 잡은 매번 빈 워크스페이스에서 시작한다. 그냥 두면 3시간째에 죽었을 때 처음부터 다시 돈다. 코드에 이미 있는 재개 로직을 살리려면 두 디렉터리가 잡 사이에 살아남아야 한다.

```python
# structured.py:978  — 열거 캐시
if cache.exists():
    return json.loads(cache.read_text(encoding="utf-8"))

# structured.py:993  — 대학별 산출물 있으면 스킵
if out_xlsx.exists():
    _log(f"[{i}/{len(univs)}] {name} — 이미 완료, 스킵")
    continue
```

`artifacts` 가 아니라 `cache` 를 쓰는 이유: artifacts는 **다음 잡**으로 넘기는 것이고, cache는 **같은 잡을 다시 돌릴 때** 복원된다. 재시도 시나리오에는 cache가 맞다. 키에 연도를 넣어 해가 바뀌면 자동으로 새 캐시를 쓴다.

효과: 3시간째 죽어도 재시도하면 남은 대학만 받는다. `recover_campuses*.py` 가 이미 이 방식으로 동작했다(캐시 삭제 → 특정 대학만 재열거).

### 4-5. 왜 샤딩하지 않는가

총 요청량은 고정이다. 실측에서 역산하면 `227분 × 동시 6 ≈ 1,362 분·worker`.

| 구성 | 총 동시 | 잡당 wall | 어디가 부하 |
|---|---:|---:|---:|
| 1 × 6 (현재) | 6 | 227분 | 1.0x |
| 4 × 6 | 24 | 57분 | 4.0x |
| 6 × 1 | 6 | 227분 | 1.0x |

마지막 줄이 핵심이다. **샤딩 자체는 시간을 줄이지 못한다.** 총 동시성이 그대로면 샤드를 쪼개도 각 샤드가 여전히 227분이다. 시간을 줄이려면 반드시 어디가 부하를 그만큼 올려야 한다.

크롤은 연 1회 + 변경 시 수시라 4시간이 아프지 않다. '딸깍'의 가치는 빠름이 아니라 사람이 안 붙어도 되는 것이다. 부하 4배로 차단 리스크를 사는 건 남는 거래가 아니다.

실제로 자주 눌릴 잡은 `crawl:partial` 이다. 피드백 대응(경동대 빈 파일, 원본 결손 3개 대학 재크롤)이 반복 업무였고 그건 몇 분이면 끝난다.

### 4-6. 골든셋 게이트

임계치를 두 개 건다.

```
--min-rate 99.9      정합률 하한 (현재 99.98%)
--max-review 15      검토필요 상한 (현재 10건)
```

정합률만 걸면 우회가 가능하다. 어려운 건을 전부 `검증필요`로 빼면 대조 대상에서 빠져 정합률이 올라간다. 검토필요 상한을 같이 걸어야 막힌다.

**골든셋을 `tests/fixtures/golden_2027.xlsx`로 커밋한다**(643KB). 2-5절대로 레포 밖 파일에 의존하면 CI 게이트 자체가 성립하지 않는다.

---

## 5. 문서 배치

| 경로 | 내용 | 왜 거기 |
|---|---|---|
| `CLAUDE.md` (루트) | 두 프로젝트 진입점, 어느 문서를 언제 읽는지 | AI가 세션 시작 시 자동으로 읽는 유일한 파일 |
| `docs/HANDOVER.md` | 30분 진입 문서 | 사람용 최상위 |
| `docs/decisions.md` | 왜 그렇게 했는지 | 코드로 복원 불가한 유일한 정보 |
| `crawler/CLAUDE.md` | 엔드포인트 5종, 9파라미터, 열거 함정 | 크롤러 고칠 때만 필요 |
| `crawler/docs/site-changes.md` | 사이트 변경 진단표 (증상 → 원인 → 확인법) | 장애 대응용 |
| `refiner/CLAUDE.md` | 규칙 레지스트리 사용법, 규칙 추가 절차 | 규칙 추가가 가장 잦은 작업 |
| `refiner/docs/rules.md` | 규칙 A~J 정의서 | 기획자가 읽고 판단할 문서 |
| `config/README.md` | 연도 전환 체크리스트 | 설정 파일 바로 옆 |

`CLAUDE.md` 를 세 개로 쪼개는 게 핵심이다. 루트 하나에 다 넣으면 정제 규칙만 고칠 때도 크롤러 함정 설명을 매번 컨텍스트에 싣게 된다.

### `docs/decisions.md` 에 반드시 남길 것

- W02 — 정제 프롬프트부터 하려다 크롤링 선행으로 피벗한 이유
- W06 이후 — DB 자동화를 드롭한 이유. 관련 코드(`--db`)가 죽어 있는 현 상태
- W10 — 열거가 Playwright여야만 했던 이유(세션 종속 POST), 검색창 Enter가 `onkeypress` 로 막혀 버튼 클릭으로 우회한 것, 페이지네이션 종단을 서명 반복으로 판정하는 이유
- W11 — 순수 결정적 정제(LLM 미사용)를 고른 이유, 모든 최저를 `N합M`으로 통일한 이유
- 검토필요 설계 — 틀린 답을 조용히 내는 대신 플래그로 드러내는 정책을 택한 이유
- 입결 트랙 A/B 중 B를 고른 이유 (2-1절)
- 골든셋을 레포에 넣기로 한 이유 (2-5절)

### `crawler/docs/site-changes.md` 진단표 (초안)

| 증상 | 의심 | 확인법 |
|---|---|---|
| 특정 대학 열거 0건 | 검색 필터 동작 변경 | 브라우저에서 대학명 검색 후 `admssUnivAjax.do` 응답 확인 |
| 전 대학 열거 0건 | 엔드포인트/파라미터 변경 | `endpoints.py` 의 9개 파라미터를 DevTools Network와 대조 |
| 상세는 오는데 값이 전부 빈칸 | 셀렉터 변경 | `selectors.py` 를 저장된 HTML fixture와 대조 |
| 열거 수가 사이트 표시보다 적음 | 페이지네이션 종단 오판 | 서명 반복 판정 로직 확인. 서버가 범위 밖 페이지를 마지막 페이지로 클램프함 |
| 컬럼이 한 칸씩 밀림 | RAW 스키마 변경 | `refiner/read/schema.py` 가 SchemaError를 던짐 — 매핑 테이블 갱신 |
| 최저 정제가 전 행에서 이상 | UI 문구 변경 | `config` 의 `placeholder` 문자열 확인 |

---

## 6. 마이그레이션

### 6-1. 순서

한 번에 옮기지 않는다.

| 단계 | 대상 | 검증 방법 | 근거 |
|---|---|---|---|
| 1 | `refiner/` | 게이트 1·2 (아래) | 입력이 파일이라 네트워크 없이 전량 검증 가능 |
| 2 | `crawler/` 전형정보 | 3개 대학 부분 크롤 후 비교 | `recover_blank_choi.py` 가 이미 검증한 경로 |
| 3 | `crawler/` 입결(트랙 B) | 표본 대학 비교 | 사용 빈도 낮음. 마지막 |

각 단계마다 게이트 통과 후 커밋. 실패하면 그 단계만 되돌린다.

### 6-2. 게이트 1 — 산출물 동일성

리팩터링 전 현재 코드로 산출물을 만들어 해시를 고정하고, 이관 후 같은 입력으로 재생성해 비교한다.

엑셀은 생성 시각이 들어가므로 파일 전체 해시는 쓸 수 없다. **zip 내부 `xl/worksheets/*.xml` 만** 비교한다. `scripts/xlsx_hash.py` 는 이 목적으로 **신규 작성**한다(현재 레포에 없음).

```bash
# 기준 생성 (이관 전)
python week11/scripts/refine/build.py week10/output/전형정보_통합.xlsx --out baseline/
scripts/xlsx_hash.py baseline/*.xlsx > baseline/sheets.sha

# 이관 후
python -m refiner build --in week10/output/전형정보_통합.xlsx --out candidate/
scripts/xlsx_hash.py candidate/*.xlsx | diff - baseline/sheets.sha
```

### 6-3. 게이트 2 — 정합률 불변

```
일치율 99.98% · 불일치 1건 · 검토필요 10건 · 플래그 분포
```

리팩터링 후에도 그대로여야 한다. 한 건이라도 바뀌면 멈추고 원인부터 찾는다. 플래그 기준값:

```
진로내부확인 6540 · 5a학생부분해 1758 · 5b합99 696
최저E영어합산 107 · 최저계열추정 14 · 최저파싱 6
```

### 6-4. 게이트 3 — 테스트 이관

- `week11/tests/test_refine.py` 6함수/36 assert 를 `refiner/tests/` 로 그대로 옮긴다. 서드파티 의존이 0이라 이식이 쉽다.
- `week09/tests` 와 `week10/tests` 중복을 정리한다. **`week10` 쪽 구현이 현행**이므로 그것을 검증하는 쪽만 남긴다(2-7절).
- `week10/scripts/test_validation.py` 를 pytest 호환으로 고쳐 `crawler/tests/` 로 옮긴다. 지금은 pytest에서 2 errors라 CI에 못 넣는데, 경동대 빈 파일 결함의 재발 방지 테스트라 가치가 크다.
- `pyproject.toml` 에 pytest 설정을 신설한다(현재 레포에 없음).

### 6-5. 안전장치 — 출력 경로

2-6절 사고를 막는다.

- 모든 CLI 진입점에 `--out` 을 **필수**로 하거나, 기본값을 `output/<YYYYMMDD-HHMMSS>/` 타임스탬프 디렉터리로 한다.
- 기존 파일을 덮어쓰는 경우 `--force` 없이는 거부한다.
- `review` · `sample` 에도 `--out` 을 추가한다(현재 없음).

---

## 7. 위험

| 위험 | 근거 | 완화 |
|---|---|---|
| dataclass 도입으로 조용한 회귀 | `cols.py` 인덱스를 쓰는 코드가 정제 전 모듈 + `choi.py:237` 리터럴 6까지 산재 | 게이트 1·2 필수. refiner 먼저 이관해 네트워크 없이 전량 검증 |
| `crawl_2027_full` monkey-patch 결합 파손 | `C.OUTPUT_DIR` 전역 변조에 의존(2-2절) | 트랙 A를 아예 이관하지 않음. 트랙 B만 |
| 골든셋 커밋 시 자산 노출 | 643KB, 대학 입시 공개정보 | 커밋 전 내용 확인. 비공개 정보 있으면 축소 번들로 전환 |
| CI 크롤이 콜드 스타트로 진입 | enum 캐시 만료/키 변경 시 6~7시간(2-4절) | 러너 `maximum_job_timeout = 9h`. 캐시 키에 연도만 넣어 불필요한 무효화 방지 |
| `_GYE_RULES` 순서 파손 | 규칙 파일 분리 시 순서 보장이 사라짐 | `@rule(order=)` 명시 + 순서 회귀 테스트(`의류환경학과 → 인문`) |
| `report.py` 전역 변조 | import 시점에 `review.POLICY` 변조(`report.py:28`) | 이관 시 명시적 인자 전달로 변경 |
| 같은 테스트가 다른 구현 검증 | `week09/tests` ≡ `week10/tests` 바이트 동일, 대상 구현 상이(2-7절) | 이관 시 현행(week10) 기준으로 단일화 |
| 어디가 차단 | 동시 6에서 4시간 무사고가 유일한 근거 | `resource_group` 으로 동시 실행 차단. 동시성 상향 금지 |

---

## 8. 완료 기준

- [ ] `python -m crawler selection --all` / `--univ <코드>` 동작
- [ ] `python -m refiner build --in <통합본> --out <디렉터리>` 동작
- [ ] `python -m refiner qa golden --min-rate 99.9 --max-review 15` 동작
- [ ] 게이트 1: 이관 전후 `xl/worksheets/*.xml` 해시 동일
- [ ] 게이트 2: 정합률 99.98% · 불일치 1 · 검토필요 10 · 플래그 6종 분포 불변
- [ ] `pytest -q` 전량 통과 (`test_validation.py` 포함)
- [ ] `.gitlab-ci.yml` 파이프라인이 MR에서 5분 내 완료
- [ ] `crawl:partial` 수동 실행으로 3개 대학 재크롤 성공
- [ ] 연도 전환 리허설: `config/2028.yaml` 만들고 문서만 보고 AI가 끝까지 시도 — 막힌 지점을 문서에 보강
- [ ] 문서 8종 작성 완료
