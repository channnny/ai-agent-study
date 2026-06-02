"""adiga 입시결과 크롤러 (본격 버전, 로컬 실행용)

사용법:
    python crawler.py                              # 8개 기본 대학
    python crawler.py --unvcd 0000063 0000019      # 특정 대학만
    python crawler.py --year 2027 --out result.xlsx

설치:
    pip install requests beautifulsoup4 lxml openpyxl pandas tqdm

특징:
- 동시에 5개 대학 병렬 처리 (옵션)
- 학과별 입시결과 표를 HTML <table>에서 직접 파싱 (마크다운 변환 거치지 않음)
- 골든셋 (2단 헤더 양식)과 동일한 구조로 저장 → evaluate.py 바로 적용 가능
- 3회 재시도 + 실패 대학은 error_log.json
"""
from __future__ import annotations
import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment


# ─────────────────────────────────────────────
# 8개 타겟 대학
# ─────────────────────────────────────────────

UNIVERSITIES = {
    '0000063': '가천대학교',
    '0000019': '서울대학교',
    '0000027': '제주대학교',
    '0000149': '연세대학교',
    '0000069': '고려대학교',
    '0000014': '부산대학교',
    '0000005': '경북대학교',
    '0000245': '남서울대학교',
}

BASE_URL = 'https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do'

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ' \
             'AppleWebKit/537.36 (KHTML, like Gecko) ' \
             'Chrome/120.0 Safari/537.36'

# 표기 정규화 사전 (adiga 페이지 → 골든셋 양식)
NORMALIZE_MAP = {
    '전 과목': '전교과',
    '전과목': '전교과',
    '전체': '전교과',
}


# ─────────────────────────────────────────────
# 데이터 모델
# ─────────────────────────────────────────────

@dataclass
class ParsedRow:
    """학과별 입시결과 1행"""
    대학: str
    전형: str
    모집단위: str
    모집인원: Optional[int] = None
    경쟁률: Optional[float] = None
    충원합격순위: Optional[int] = None
    학생부등급_50컷: Optional[float] = None
    학생부등급_70컷: Optional[float] = None
    학생부등급_80컷: Optional[float] = None
    학생부등급_90컷: Optional[float] = None
    학생부등급_기준: str = ''
    학생부등급_반영교과: str = ''
    raw_text: str = ''


# ─────────────────────────────────────────────
# 페이지 가져오기 (재시도 포함)
# ─────────────────────────────────────────────

def fetch_page(unvcd: str, year: int, max_retries: int = 3) -> Optional[str]:
    params = {
        'menuId': 'PCUVTINF2000',
        'unvCd': unvcd,
        'searchSyr': year,
    }
    headers = {'User-Agent': USER_AGENT}

    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(BASE_URL, params=params, headers=headers, timeout=30)
            r.raise_for_status()
            return r.text
        except Exception as e:
            if attempt == max_retries:
                print(f'  ✗ {unvcd}: {e}')
                return None
            time.sleep(2 ** attempt)
    return None


# ─────────────────────────────────────────────
# HTML 파싱
# ─────────────────────────────────────────────

def parse_university_page(html: str, university: str) -> tuple[list[ParsedRow], list[str]]:
    """페이지 HTML에서 학과별 입시결과를 추출.
    반환: (행 리스트, 경고/이슈 메시지 리스트)"""
    soup = BeautifulSoup(html, 'lxml')
    rows: list[ParsedRow] = []
    issues: list[str] = []

    # adiga 페이지는 "Q 2. 2025학년도 전형 결과" 같은 섹션 안에 학과별 표가 들어있음
    # 모든 <table>을 순회하면서 "모집단위" 같은 셀이 있는 표를 후보로 잡음
    tables = soup.find_all('table')

    current_jeon: Optional[str] = None
    for tbl in tables:
        result = _parse_one_table(tbl, university, current_jeon)
        if result is None:
            continue
        new_jeon, table_rows = result
        if new_jeon:
            current_jeon = new_jeon
        rows.extend(table_rows)

    # 표 외부에 "모집단위 XXX 전형" 같은 텍스트가 있을 수도 있어 보강 파싱
    # (실제 페이지에서는 표 안 caption이나 인접 텍스트로 전형명 식별)
    return rows, issues


def _parse_one_table(tbl: Tag, university: str, prev_jeon: Optional[str]) -> Optional[tuple[Optional[str], list[ParsedRow]]]:
    """단일 <table>에서 입시결과 데이터 추출.
    반환: (이 표의 전형명 또는 None, 행 리스트)"""
    # 표의 첫 행에 "모집단위 XXX 전형" 같은 패턴이 있는지 확인
    first_row = tbl.find('tr')
    if not first_row:
        return None

    first_text = ' '.join(c.get_text(strip=True) for c in first_row.find_all(['td', 'th']))

    # 전형명 추출 시도 ("모집단위 [전형명] 전형" 또는 "모집단위 [전형명]")
    jeon = None
    m = re.search(r'모집단위\s+(.+?)(?:\s*전형)?(?:\s*\(.*?\))?\s*$', first_text)
    if m and len(first_row.find_all(['td', 'th'])) <= 3:
        jeon = m.group(1).strip()

    # 컬럼 헤더 찾기 (모집인원, 경쟁률, 충원합격순위 등을 포함하는 행)
    header_row = None
    header_idx = -1
    for idx, tr in enumerate(tbl.find_all('tr')):
        txt = ' '.join(c.get_text(strip=True) for c in tr.find_all(['td', 'th']))
        if '모집' in txt and ('경쟁률' in txt or '인원' in txt):
            if '학생부등급' in txt or 'cut' in txt.lower() or '교과성적' in txt:
                header_row = tr
                header_idx = idx
                break

    if not header_row:
        # 입시결과 표가 아님 (평가기준 등)
        return None

    # 헤더에서 컬럼 종류 파악
    header_text = ' '.join(c.get_text(strip=True) for c in header_row.find_all(['td', 'th']))
    cut_types = []
    if re.search(r'50\s*%?\s*cut', header_text, re.I):
        cut_types.append('50컷')
    if re.search(r'70\s*%?\s*cut', header_text, re.I):
        cut_types.append('70컷')
    if re.search(r'80\s*%?\s*cut', header_text, re.I):
        cut_types.append('80컷')
    if re.search(r'90\s*%?\s*cut', header_text, re.I):
        cut_types.append('90컷')

    # 기준 컬럼 ("최종등록자" 등) - 헤더에서 "최종등록자"가 있으면 모든 행의 기준 = "최종등록자"
    기준_value = ''
    if '최종등록자' in header_text:
        기준_value = '최종등록자'

    # 데이터 행 파싱
    rows = []
    all_trs = tbl.find_all('tr')
    last_반영교과 = ''
    for tr in all_trs[header_idx + 1:]:
        cells = [c.get_text(strip=True) for c in tr.find_all(['td', 'th'])]
        if len(cells) < 4:
            continue

        # 첫 셀이 학과명 (전형명이 다시 나오면 새 표 시작이므로 break)
        dept = cells[0]
        if not dept or '모집단위' in dept:
            continue

        # 두번째 셀이 정수면 데이터 행, 아니면 skip
        try:
            mojip = int(cells[1])
        except (ValueError, IndexError):
            continue

        # 경쟁률 / 충원합격순위
        try:
            kyungjaeng = float(cells[2]) if cells[2] else None
        except ValueError:
            kyungjaeng = None
        try:
            chungwon = int(cells[3]) if cells[3] and cells[3] != '-' else None
        except ValueError:
            chungwon = None

        # 등급 cut 값들 (4번째 셀 이후)
        cut_values = {}
        for i, cut_type in enumerate(cut_types):
            cell_idx = 4 + i
            if cell_idx < len(cells):
                try:
                    v = float(cells[cell_idx]) if cells[cell_idx] and cells[cell_idx] != '-' else None
                    cut_values[cut_type] = v
                except ValueError:
                    pass

        # 반영교과 (마지막 셀이 텍스트면)
        반영교과 = ''
        last_cell = cells[-1] if cells else ''
        if last_cell and not _is_number(last_cell):
            raw = last_cell
            반영교과 = NORMALIZE_MAP.get(raw, raw)
            last_반영교과 = 반영교과
        else:
            반영교과 = last_반영교과  # 상속

        row = ParsedRow(
            대학=university,
            전형=jeon or prev_jeon or '',
            모집단위=dept,
            모집인원=mojip,
            경쟁률=kyungjaeng,
            충원합격순위=chungwon,
            학생부등급_50컷=cut_values.get('50컷'),
            학생부등급_70컷=cut_values.get('70컷'),
            학생부등급_80컷=cut_values.get('80컷'),
            학생부등급_90컷=cut_values.get('90컷'),
            학생부등급_기준=기준_value,
            학생부등급_반영교과=반영교과,
        )
        rows.append(row)

    return jeon, rows


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


# ─────────────────────────────────────────────
# 한 대학 크롤
# ─────────────────────────────────────────────

def crawl_university(unvcd: str, university: str, year: int) -> tuple[list[ParsedRow], list[str]]:
    print(f'[{unvcd}] {university} fetching...')
    html = fetch_page(unvcd, year)
    if html is None:
        return [], [f'{university}: fetch 실패']

    # 디버그용 raw HTML 저장
    Path('raw_html').mkdir(exist_ok=True)
    (Path('raw_html') / f'{unvcd}.html').write_text(html, encoding='utf-8')

    rows, issues = parse_university_page(html, university)
    print(f'[{unvcd}] {university}: {len(rows)}행 추출')
    return rows, issues


# ─────────────────────────────────────────────
# 출력 (골든셋 양식)
# ─────────────────────────────────────────────

GOLDEN_SCHEMA = [
    (None, '대학'), (None, '전형'), (None, '모집단위'),
    (None, '라벨'),
    (None, '바이브온_대학명'), (None, '바이브온_대학코드'),
    (None, '바이브온_전형명'), (None, '바이브온_전형코드'),
    (None, '바이브온_모집단위명'), (None, '바이브온_모집단위코드'),
    (None, '모집인원'), (None, '경쟁률'), (None, '충원합격순위'),
    ('대학별환산', '최고'), ('대학별환산', '평균'),
    ('대학별환산', '50컷'), ('대학별환산', '70컷'),
    ('대학별환산', '80컷'), ('대학별환산', '100컷'),
    ('대학별환산', '총점'),
    ('학생부등급', '최고'), ('학생부등급', '평균'),
    ('학생부등급', '50컷'), ('학생부등급', '70컷'),
    ('학생부등급', '80컷'), ('학생부등급', '90컷'),
    ('학생부등급', '최저'),
    ('학생부등급', '기준'), ('학생부등급', '반영교과'),
]


def save_xlsx(rows: list[ParsedRow], path: str):
    wb = Workbook()
    ws = wb.active
    ws.title = '수시'

    HEADER_FONT = Font(name='맑은 고딕', size=10, bold=True, color='FFFFFF')
    HEADER_FILL = PatternFill('solid', start_color='1F4E78')
    CENTER = Alignment(horizontal='center', vertical='center')

    # Row 1: 그룹 헤더
    for col_idx, (top, sub) in enumerate(GOLDEN_SCHEMA, start=1):
        if top:
            c = ws.cell(row=1, column=col_idx, value=top)
            c.font = HEADER_FONT
            c.fill = HEADER_FILL
            c.alignment = CENTER

    ws.merge_cells('N1:T1')
    ws.merge_cells('U1:AC1')

    # Row 2: 컬럼명
    for col_idx, (top, sub) in enumerate(GOLDEN_SCHEMA, start=1):
        c = ws.cell(row=2, column=col_idx, value=sub)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = CENTER

    # 컬럼명 → 인덱스 매핑
    DEST = {
        '대학': 1, '전형': 2, '모집단위': 3,
        '모집인원': 11, '경쟁률': 12, '충원합격순위': 13,
        '학생부등급_50컷': 23, '학생부등급_70컷': 24,
        '학생부등급_80컷': 25, '학생부등급_90컷': 26,
        '학생부등급_기준': 28, '학생부등급_반영교과': 29,
    }

    # 데이터 행
    for r_idx, row in enumerate(rows, start=3):
        for attr, col_idx in DEST.items():
            val = getattr(row, attr, None)
            if val is not None and val != '':
                ws.cell(row=r_idx, column=col_idx, value=val)

    wb.save(path)
    print(f'\n✓ 저장: {path} ({len(rows)}행)')


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--unvcd', nargs='*', default=None,
                    help='특정 대학 unvCd 리스트 (기본: 8개 전체)')
    ap.add_argument('--year', type=int, default=2027,
                    help='searchSyr (2026학년도 자료는 2027 사용)')
    ap.add_argument('--out', default='predicted.xlsx', help='출력 엑셀 경로')
    ap.add_argument('--workers', type=int, default=3, help='병렬 워커 수')
    ap.add_argument('--errors', default='error_log.json', help='실패 로그 경로')
    args = ap.parse_args()

    if args.unvcd:
        targets = {u: UNIVERSITIES.get(u, f'대학_{u}') for u in args.unvcd}
    else:
        targets = UNIVERSITIES

    all_rows: list[ParsedRow] = []
    errors: dict[str, list[str]] = {}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(crawl_university, unv, name, args.year): (unv, name)
                   for unv, name in targets.items()}
        for f in as_completed(futures):
            unv, name = futures[f]
            try:
                rows, issues = f.result()
                all_rows.extend(rows)
                if issues:
                    errors[name] = issues
            except Exception as e:
                errors[name] = [str(e)]

    save_xlsx(all_rows, args.out)

    if errors:
        Path(args.errors).write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'⚠ 일부 대학 이슈 발생: {args.errors}')

    print()
    print(f'━━━ 요약 ━━━')
    print(f'대상 대학: {len(targets)}개')
    print(f'총 추출 행: {len(all_rows)}개')
    print(f'대학별:')
    by_univ = {}
    for r in all_rows:
        by_univ[r.대학] = by_univ.get(r.대학, 0) + 1
    for name in targets.values():
        print(f'  {name}: {by_univ.get(name, 0)}행')


if __name__ == '__main__':
    main()
