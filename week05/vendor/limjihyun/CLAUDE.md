# CLAUDE.md

대학어디가(adiga.kr)에서 수시 입결 데이터를 자동 수집해, 정해진 엑셀 양식에 채우는 에이전트. 이 문서는 이 프로젝트에서 작업하는 Claude를 위한 운영 가이드다.

## 프로젝트 개요

- **목표**: 어디가의 학생부종합/학생부교과 전형 입시결과를 대학별로 크롤링 → 표준화 → 엑셀 양식(`어디가입결_양식.xlsx`)에 매핑.
- **운영**: 매년 입시철 1~2회, 1회 30~80개 대학, 최신 1개 학년도.
- **상세 설계**: [agent_design_v0.4.md](agent_design_v0.4.md) 참조 (아키텍처·리스크·시행착오 기록).
- **범위 제외**: adiga.kr 자동화 수집의 법적·이용약관 검토.

## 실행 방법

```bash
# 환경 (최초 1회)
python3 -m venv .venv
.venv/bin/pip install playwright anthropic openpyxl pyyaml
.venv/bin/python -m playwright install chromium

# API 키 (.env 파일, .gitignore에 등록됨)
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env

# 단일 대학 end-to-end (예: 고려대 본교)
.venv/bin/python run_poc.py 0000069

# 단계별 실행
.venv/bin/python -m agent.crawler 0000069     # → out/raw/{code}.json
.venv/bin/python -m agent.mapper 0000069      # → out/mapped/{code}.json
.venv/bin/python -m agent.validator 0000069   # → out/reports/{code}.json
.venv/bin/python -m agent.writer 0000069      # → outputs/{code}.xlsx
```

> **중요**: 모든 Python 실행은 `.venv/bin/python`으로. 시스템 python3(3.9)에는 의존성이 없다.

## 아키텍처

4단계 파이프라인 (`run_poc.py`가 순차 호출):

```
Crawler → Mapper → Validator → Writer
(Playwright) (사전+LLM)  (가드)   (openpyxl)
```

| 단계 | 파일 | 책임 | 산출 |
|---|---|---|---|
| Crawler | [agent/crawler.py](agent/crawler.py) | 페이지 진입, 표 추출, **멀티헤더 평면화** | `out/raw/{code}.json` |
| Mapper | [agent/mapper.py](agent/mapper.py) | 사전 매칭 우선 → 미해결만 LLM | `out/mapped/{code}.json` |
| Validator | [agent/validator.py](agent/validator.py) | 수치 일치성·범위·**빈 산출 가드** | `out/reports/{code}.json` |
| Writer | [agent/writer.py](agent/writer.py) | 양식 복제 + R3부터 row 입력 + 재독 | `outputs/{code}.xlsx` |

설정 파일:
- [mapping_dictionary.yaml](mapping_dictionary.yaml) — 컬럼명→표준필드, 전형명→admission_type 사전
- [cell_mapping.yaml](cell_mapping.yaml) — 표준필드→엑셀 셀 위치

## 어디가 표 예외 케이스 카탈로그 (8개 대학 실측)

대학마다 입결 표 양식이 다르다. 아래는 실측으로 확인하고 코드가 커버하는 예외들이다. **새 대학 추가 시 이 목록과 대조**할 것.

| # | 예외 | 실제 예 | 커버 방법 (코드 위치) |
|---|---|---|---|
| 1 | 컷 표기 변형 | `50% cut`/`50 cut`/`50%cut`/`70% cut`(점 아닌 공백) | `_norm`이 공백·% 제거 + `_CUT_RE` 정규식 (mapper) |
| 2 | 컷 종류 다양 | 고려대 50·70 / 가천대 70·90 / 동국대 평균만 / 100컷 | `_match_column` 규칙: cutnum 추출 → `grade.cut_{N}` |
| 3 | 종합/교과 판별 | thead에 명시 안 됨(가천·동국·영남) | `_classify_admission`: thead 명시 > 평가반영·분포도→종합 > 환산→교과 > 등급만→교과 |
| 4 | 정시·전형방법 표 혼입 | "총점(수능)", "백분위", "선발방법" | `_REJECT_SIGNALS`로 제외 |
| 5 | 지원자 분포도 표 분리 | 경기대·영남대: 분포도 표 + 컷 표 별도 | `_merge_records`로 (전형,모집단위) 병합. 영남대 종합 64행 복구 |
| 6 | 소수인원 안내 문구 | "선발인원 3명 이하 모집단위 전형별 공개" | `_parse_num(strict=True)`: 한글 섞이면 None (숫자 "3" 오추출 차단) |
| 7 | 미공개를 0으로 표기 | 가톨릭관동대: 환산·등급 `0.00` | `_set_path`: grade/converted 0 → None |
| 8 | 모집인원 텍스트 | "6이내", "3이내" | `_parse_num(strict=False)`: 한글 3자 미만 허용 → 6 |
| 9 | 충원 비숫자 | "통합" | strict 파싱 → None |
| 10 | 전형명 부가설명 | "특성화고교 전형(2026학년도부터...)" | `_clean_label`: 학년도·콜론·4자리수·배수 든 괄호만 제거 (`선발`·`반영`은 전형명에 흔해 트리거 제외) |
| 11 | thead 범례 오염 | 영남대 "(O : 등록, X : 미등록...)" | `_clean_label`이 콜론 괄호 제거 → 대분류로 폴백 |
| 12 | 1개 모집단위 전형 | 경기대 SW우수자전형(1행) | `_is_candidate`: `data_row_count >= 1` (≥3이면 소수 전형 누락) |

**정답본이 어디가와 다른 케이스 (우리 추출이 어디가에 충실, 정답본이 외부 보충/상이):**
- 경기대 기회균형선발전형 등급 18건 — 어디가 원문(공공안전 2.71, 경제 3.94)과 정답본(공공안전 3.79, 경제 2.68)이 다름. 정답본 행 밀림 의심. **우리 값이 어디가 원문과 일치**.
- 경기대 기초생활수급자등선발전형(18행) — 어디가에 입결 표 자체가 없음(반영교과 설명만). 정답본이 외부 보충.
- 경기대 사회배려대상자(어디가 16 vs 정답 28)·농어촌(27 vs 37) — 어디가 분포도/컷 표의 모집단위가 정답본보다 적음.
- 충원 1~2건(고려대·영남대) — 어디가 원문 빈칸인데 정답본이 보충.

**아직 불완전한 케이스 (알려진 한계):**
- 캠퍼스 분리 대학: 본교 unvCd만 크롤하면 분교/제2캠 학과는 누락.
- 정답본이 소수인원 미공개 행을 거른 경우, 우리는 행을 만들어 매칭 키가 어긋남 (데이터는 어디가 충실).
- Validator 수치 일치성 임계값 0.20이 일부 대학(동국대 off_ratio 0.21)에서 과민하게 REVIEW 발생 → 캘리브레이션 필요.

## 멀티 대학 검증 결과 (정답본 2025_어디가입결_통합본 대조)

8개 대학, (모집단위·모집인원·경쟁률) 키 매칭 후 필드 일치율:

| 대학 | 양식 유형 | 매칭/내records | 매칭행 정확도 |
|---|---|---|---|
| 건국대 | 등급+환산(교과) | 75/75 | 100% |
| 고려대 | 등급 위주 | 235/235 | 99.5% |
| 가천대 | 70·90컷, 환산없음 | 285/285 | 100% |
| 동국대 | 등급평균만 | 135/139 | 100% |
| 동덕여대 | 혼합 | 62/62 | 100% |
| 영남대 | 환산+등급, 종합 분포도 | 332/332 | 99.4% |
| 가톨릭관동대 | 환산+등급, 소수인원 0표기 | 102/154 | ~99% (매칭행) |
| 경기대 | 분포도+컷 분리, 캠퍼스 | 140/162 | 충원·환산 100%, 등급은 정답본이 어디가와 상이(아래) |

> 재현: `.venv/bin/python run_batch.py` (8개 대학 크롤→매핑→검증→쓰기 + 정답 대조 리포트).

## 어디가 사이트 핵심 사실 (POC 실측)

- **상세 진입 URL**: `https://www.adiga.kr/ucp/uvt/uni/univDetail.do?searchSyr={year}&searchUnvCodeAllYn=true&unvCd={code}&sortNm=&sortOrder=true&unvLink=on`
- **입결 영역**: 좌측 "평가기준 및 입시결과" 클릭 → `univDetailSelection.do`로 전환. `fnChangeTapType('selection')` 트리거.
- **파라미터명은 `unvCd`** (4자리 0-패딩). 예: `0000069`=고려대[본교], `0000070`=고려대(세종).
- **대학명 → unvCd 조회 API**: `GET /man/sch/univInfo.do?search={이름}&limit=100&sort=$relevance&...` → JSON `result.rows[].fields.UNIV_CD`.
- **학년도**: `page_year`(진입, 예 2027)와 `result_year`(표 안 데이터, 예 2026)는 다르다. **진입 학년도가 입시 전이면 그 해 입결이 없는 게 정상** — 표엔 직전 학년도가 뜬다.
- **표는 멀티헤더(2~3단 + rowspan/colspan)**. 평면화 없이는 LLM도 헤더 해석에 실패한다.
- **대학마다 공개 범위 다름**: 고려대 종합은 학생부등급만, 학교추천은 환산점수만 공개. 미공개는 빈칸 유지.

## 작업 시 규칙

1. **결정론 우선**: 페이지 조작·표 추출·셀 입력은 코드로. LLM은 사전으로 못 푼 표 매핑에만.
2. **사전이 먼저**: `mapping_dictionary.yaml` 매칭이 1순위. LLM은 fallback. 고려대는 사전 28개 키만으로 235행 100% 매핑됨 (LLM 0회).
3. **빈 산출 금지**: Validator가 records=0 또는 raw 대비 30% 미만이면 REVIEW. 빈 엑셀을 PASS로 흘리지 않는다.
4. **결측은 빈칸**: "N/A" 등을 임의로 채우지 않는다. 어디가 원문에 없으면 비운다.
5. **양식 보호**: 헤더 R1·R2 수정 금지, 병합셀(`G1:M1`,`N1:T1`) 보존, R3부터 데이터만. 기존 출력은 `outputs/.backup/`으로 자동 이동.
6. **LLM fatal 오류는 즉시 중단**: `AuthenticationError`/`credit balance`/`PermissionDeniedError`는 재시도 말고 LLM disable (사전 결과로 계속).

## 엑셀 양식 컬럼 (시트 `수시`, 22열)

```
A 대학  B 전형(세부명)  C 모집단위  D 모집인원  E 경쟁률  F 충원합격순위
G~M 대학별환산(최고/평균/50컷/70컷/80컷/100컷/총점)
N~T 학생부등급(최고/평균/50컷/70컷/80컷/90컷/최저)
U 기준  V 반영교과
```
- B(전형)에는 **세부 전형명**(`학생부종합(학업우수)`)을 넣는다. 대분류만 넣으면 같은 모집단위가 전형별로 구분 안 됨.
- U(기준)는 헤더에 "최종등록자"가 있으면 "최종등록자".

## 검증된 정확도 (고려대 235행, 정답본 대조)

행 매칭 100% · 모집인원·경쟁률·학생부등급 50/70컷·환산총점·기준 **100%** · 충원 99.5%(잔여 1건은 어디가 원문 빈칸).

**알려진 한계 / 정답본과 의도적 차이:**
- 환산 cut_50/cut_70: 양식 칸이 있어 채움(정답본은 비움). 정책 선택 가능.
- 반영교과: 어디가 원문 "전체교과" 유지(정답본은 "전교과" 축약).
- 바이브온_* 내부코드(대학/전형/모집단위 코드): 미구현. 별도 마스터 매핑 필요.
- 정시 표(Table 34~36)는 수시 정책상 제외.

## 디렉터리

```
agent/            크롤러·매퍼·검증·라이터
run_poc.py        end-to-end 실행
mapping_dictionary.yaml / cell_mapping.yaml   설정
어디가입결_양식.xlsx (~/Downloads)   엑셀 템플릿
out/raw, out/mapped, out/reports, out/screenshots   중간 산출물
outputs/          최종 엑셀 (+ .backup)
agent_design_v0.4.md   상세 설계서
scripts/          사이트 탐색용 일회성 스크립트
```
