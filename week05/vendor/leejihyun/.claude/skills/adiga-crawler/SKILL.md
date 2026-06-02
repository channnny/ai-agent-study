# 스킬: adiga-crawler

## 역할
adiga 대학 상세 페이지를 HTTP GET으로 가져와 raw HTML 파일로 저장한다.
3회 재시도(지수 백오프), 병렬 워커, 실패 대학은 에러 로그 기록.

## 트리거
메인 에이전트(CLAUDE.md)가 T1 크롤링 단계에서 호출.

## 입력
- `--unvcd`: 대학 코드 리스트 (7자리 zero-padded, 예: `0000063 0000019`)
- `--year`: searchSyr 값 (예: `2027`)
- `--workers`: 동시 워커 수 (기본 3)
- `--output`: raw HTML 저장 디렉토리 (기본 `output/raw_html`)
- `--state`: run_state.json 경로 (기본 `output/run_state.json`)
- `--errors`: 에러 로그 경로 (기본 `output/logs/error_log.json`)
- `--csv`: universities.csv 경로 (unvcd 대신 사용 가능)

## 출력
- `{output}/{unvCd}.html`: 대학별 raw HTML
- `{state}` 갱신: fetching → fetched 또는 error_fetch
- `{errors}` 갱신: 실패 시 항목 추가

## 성공 기준
- HTTP 200
- HTML 크기 ≥ 10KB
- `<title>` 태그에 "대입정보포털" 포함

## 의존성
```
pip install requests beautifulsoup4 lxml
```

## 실행 예시
```bash
# 특정 대학
python .claude/skills/adiga-crawler/scripts/crawl.py \
  --unvcd 0000063 0000019 \
  --year 2027

# CSV에서 전체 대학
python .claude/skills/adiga-crawler/scripts/crawl.py \
  --csv input/universities.csv \
  --year 2027 \
  --workers 3

# force 재실행 (이미 fetched인 대학도)
python .claude/skills/adiga-crawler/scripts/crawl.py \
  --csv input/universities.csv \
  --year 2027 \
  --force
```
