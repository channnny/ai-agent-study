"""adiga 입시결과 마크다운 파서 (PoC)
web_fetch가 반환한 마크다운에서 학과별 입시결과 표를 추출한다.

본격 크롤러(requests+BS4)와 동일한 출력 스키마를 사용하므로
사용자 로컬 환경에서 실제 크롤러로 대체해도 평가 파이프라인은 동일하게 작동한다.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class TableHeader:
    """파싱한 표의 헤더 정보"""
    columns: list[str]
    has_70cut: bool = False
    has_90cut: bool = False
    has_50cut: bool = False
    has_반영교과: bool = False
    cutkind: str = '학생부등급'   # '학생부등급' 또는 '대학별환산'


# 헤더 패턴 (가천대 외에도 통용되는 패턴들)
HEADER_PATTERNS = [
    # 패턴 A: "모집인원 경쟁률 충원합격 순위 최종등록자 교과성적 학생부등급 70% cut 평가에 반영된 교과목"
    re.compile(r'모집\s*인원\s+경쟁률\s+충원합격\s*순위\s+최종등록자\s+교과성적\s+학생부등급\s+(\d+)%\s*cut\s+평가에\s*반영된\s*교과목'),
    # 패턴 B: "모집인원 경쟁률 충원 합격 순위 최종등록자 교과성적 학생부등급" + 다음줄 "70% cut 90% cut"
    re.compile(r'모집\s*인원\s+경쟁률\s+충원\s*합격\s*순위\s+최종등록자\s+교과성적\s+학생부등급\s*$'),
    # 패턴 C: 70% cut 90% cut 단독
    re.compile(r'^\s*(\d+)%\s*cut\s+(\d+)%\s*cut\s*$'),
]


TRANSY_PATTERN = re.compile(r'^모집단위\s+(.+?)(?:\s*전형)?(?:\s*\(.*\))?\s*$')


def parse_markdown(text: str, university: str) -> pd.DataFrame:
    """마크다운 텍스트에서 학과별 입시결과를 DataFrame으로 추출."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # 마크다운 리스트 마커 제거
    lines = [re.sub(r'^[-\*]\s+', '', l) for l in lines]

    rows = []
    current_jeon = None       # 전형명
    current_header = None     # TableHeader
    last_반영교과 = ''         # 첫 행에 나타난 후 후속 행 상속

    i = 0
    while i < len(lines):
        line = lines[i]

        # 1) 전형명 라인 감지
        m = TRANSY_PATTERN.match(line)
        if m and not _looks_like_dept_row(line):
            current_jeon = m.group(1).strip()
            current_header = None
            last_반영교과 = ''
            i += 1
            continue

        # 2) 헤더 라인 감지
        header = _try_parse_header(lines, i)
        if header:
            current_header = header[0]
            i = header[1]
            continue

        # 3) 데이터 라인 시도 (전형/헤더가 있을 때만)
        if current_jeon and current_header:
            row = _try_parse_data_row(line, current_header, last_반영교과)
            if row:
                # 반영교과 상속
                if row.get('반영교과'):
                    last_반영교과 = row['반영교과']
                else:
                    row['반영교과'] = last_반영교과

                row['대학'] = university
                row['전형'] = current_jeon
                rows.append(row)

        i += 1

    return pd.DataFrame(rows)


def _looks_like_dept_row(line: str) -> bool:
    """라인이 데이터 행처럼 보이는지 (학과명 + 숫자 시작)"""
    parts = line.split()
    if len(parts) < 3:
        return False
    try:
        # 두 번째 토큰이 정수 (모집인원) → 데이터 행
        int(parts[1])
        return True
    except ValueError:
        return False


def _try_parse_header(lines: list[str], i: int) -> Optional[tuple[TableHeader, int]]:
    """헤더 라인 + 다음 라인 조합을 검사. 매칭되면 (TableHeader, 다음_인덱스) 반환."""
    line = lines[i]
    has_50 = '50%' in line.lower() or '50컷' in line
    has_70 = '70%' in line.lower() or '70컷' in line
    has_90 = '90%' in line.lower() or '90컷' in line
    has_반영 = '반영된' in line or '반영교과' in line

    # 패턴 A/C: 한 줄 헤더 (70% cut 또는 90% cut)
    if '모집' in line and '학생부등급' in line:
        # 70% cut만 있는 경우 (한 줄에)
        if (has_70 or has_90 or has_50) and has_반영:
            return TableHeader(
                columns=['모집인원', '경쟁률', '충원합격순위', '학생부등급_cut', '반영교과'],
                has_70cut=has_70, has_90cut=has_90, has_50cut=has_50,
                has_반영교과=True,
            ), i + 1

        # 패턴 B: "모집인원 ... 학생부등급" + 다음줄 "70% cut 90% cut"
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            m = re.match(r'^\s*(?:(\d+)%\s*cut\s*)+\s*$', next_line)
            if m:
                cuts_in_next = re.findall(r'(\d+)%\s*cut', next_line)
                cols = ['모집인원', '경쟁률', '충원합격순위']
                cuts_h = TableHeader(columns=cols, has_50cut=False, has_70cut=False, has_90cut=False)
                for c in cuts_in_next:
                    if c == '50':
                        cols.append('학생부등급_50컷')
                        cuts_h.has_50cut = True
                    elif c == '70':
                        cols.append('학생부등급_70컷')
                        cuts_h.has_70cut = True
                    elif c == '90':
                        cols.append('학생부등급_90컷')
                        cuts_h.has_90cut = True
                cuts_h.columns = cols
                return cuts_h, i + 2
    return None


def _try_parse_data_row(line: str, header: TableHeader, prev_반영: str) -> Optional[dict]:
    """데이터 행 파싱."""
    if not _looks_like_dept_row(line):
        return None

    parts = line.split()
    # 학과명 = 첫 토큰
    dept = parts[0]
    rest = parts[1:]

    # 끝쪽 "전 과목" / "전과목" 등 패턴 처리
    반영교과 = ''
    if len(rest) >= 2 and rest[-2] in {'전', '전체'} and rest[-1] in {'과목'}:
        반영교과 = ' '.join(rest[-2:])
        rest = rest[:-2]
    elif len(rest) >= 1 and rest[-1] in {'전과목'}:
        반영교과 = rest[-1]
        rest = rest[:-1]

    # 숫자 토큰들 추출 (- 는 None 처리)
    nums = []
    for t in rest:
        if t == '-':
            nums.append(None)
        else:
            try:
                v = float(t) if '.' in t else int(t)
                nums.append(v)
            except ValueError:
                # 알 수 없는 토큰 → 중단 (반영교과 위치일 수 있음)
                break

    if len(nums) < 3:
        return None

    row = {'모집단위': dept}
    # 기본 3컬럼
    row['모집인원'] = nums[0]
    row['경쟁률'] = nums[1]
    row['충원합격순위'] = nums[2]

    # 컷 컬럼들
    idx = 3
    if header.has_70cut and '70%' in str(header):
        # 한 줄 헤더 (70% cut만 또는 90% cut만)
        pass

    # 컷 컬럼 처리: 헤더의 columns 순서대로
    cut_cols = [c for c in header.columns if 'cut' in c or '컷' in c]
    for c in cut_cols:
        if idx < len(nums):
            # '학생부등급_cut' 같은 일반 표기는 header.has_70/90/50 보고 매핑
            if c == '학생부등급_cut':
                if header.has_70cut:
                    row['학생부등급_70컷'] = nums[idx]
                elif header.has_90cut:
                    row['학생부등급_90컷'] = nums[idx]
                elif header.has_50cut:
                    row['학생부등급_50컷'] = nums[idx]
            else:
                row[c] = nums[idx]
            idx += 1

    if 반영교과:
        row['반영교과'] = 반영교과
    else:
        row['반영교과'] = ''

    return row


if __name__ == '__main__':
    with open('gachon_raw.txt') as f:
        text = f.read()
    df = parse_markdown(text, '가천대학교')
    print(f'파싱 결과: {len(df)}행')
    print(df.head(20).to_string())
    print('\n전형별 행 수:')
    print(df['전형'].value_counts())
    df.to_excel('gachon_parsed.xlsx', index=False)
    print('\n저장: gachon_parsed.xlsx')
