"""adiga 에이전트 결과 평가 스크립트
golden vs predicted 엑셀을 비교해 정확도 리포트를 생성한다.

사용법:
    python evaluate.py golden.xlsx predicted.xlsx [--out report.xlsx] [--targets 가천대학교 서울대학교 ...]

기본 동작:
    - 8개 타겟 대학에 대해 PK 매칭 + 셀 일치율 계산
    - 컬럼별/대학별 정확도 분해
    - 리포트 엑셀 출력 (summary, mismatched_rows, missing_rows, extra_rows)
"""
from __future__ import annotations
import argparse
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────

DEFAULT_TARGETS = [
    '가천대학교', '서울대학교', '제주대학교', '연세대학교',
    '고려대학교', '부산대학교', '경북대학교', '남서울대학교',
]

# 평가에서 완전히 제외할 컬럼 (ViveOn 내부 매핑용)
EXCLUDED_COLS = {
    '라벨',
    '바이브온_대학명', '바이브온_대학코드',
    '바이브온_전형명', '바이브온_전형코드',
    '바이브온_모집단위명', '바이브온_모집단위코드',
}

# PK 컬럼
PK_COLS = ['대학', '전형', '모집단위']

# 컬럼 타입별 일치 판정 허용 오차
TYPE_CONFIG = {
    'int_strict': {'cols': ['모집인원', '충원합격순위'], 'tolerance': 0},
    'float_ratio': {'cols': ['경쟁률'], 'tolerance': 0.01},  # 소수점 둘째자리
    # 등급/환산점수는 컬럼명만으로 못 잡으니 동적 처리
    'string': {'cols': ['기준', '반영교과'], 'tolerance': None},
}


# ─────────────────────────────────────────────
# 데이터 로딩
# ─────────────────────────────────────────────

def load_sheet(path: str, sheet_name: str = '수시') -> pd.DataFrame:
    """2단 헤더 엑셀 로딩 → 단일 헤더로 평탄화.
    그룹헤더가 있는 컬럼은 '그룹_컬럼' 형식으로 변환."""
    df = pd.read_excel(path, sheet_name=sheet_name, header=[0, 1])
    new_cols = []
    seen = defaultdict(int)
    for top, sub in df.columns:
        if pd.isna(top) or str(top).startswith('Unnamed'):
            name = str(sub)
        else:
            name = f'{top}_{sub}'
        # 동명이인 컬럼 방지
        if seen[name] > 0:
            name = f'{name}__{seen[name]}'
        seen[name] += 1
        new_cols.append(name)
    df.columns = new_cols
    return df


def normalize_pk_value(v) -> str:
    """PK 값 정규화: 공백·괄호 표기 흔들림 흡수."""
    if pd.isna(v):
        return ''
    s = str(v).strip()
    # 다중 공백 → 단일
    s = re.sub(r'\s+', ' ', s)
    # 전각 괄호 → 반각
    s = s.replace('(', '(').replace(')', ')')
    # 흔한 접미사 정규화 (대학마다 "XXX 전형"/"XXX" 혼용)
    s = re.sub(r'\s*전형\s*$', '', s)
    return s


def build_pk(row, pk_cols=PK_COLS) -> tuple:
    return tuple(normalize_pk_value(row[c]) for c in pk_cols)


# ─────────────────────────────────────────────
# 셀 일치 판정
# ─────────────────────────────────────────────

def cells_match(golden, predicted, col_name: str) -> tuple[bool, str]:
    """두 셀이 일치하는지. 반환: (일치여부, 판정사유)"""
    g_null = pd.isna(golden)
    p_null = pd.isna(predicted)

    if g_null and p_null:
        return True, 'both_null'
    if g_null and not p_null:
        # 골든셋이 NULL → 에이전트가 더 찾은 것일 수 있음, 일치로 처리
        return True, 'golden_null_pred_present'
    if not g_null and p_null:
        return False, 'pred_missing'

    # 둘 다 값이 있음
    # 숫자 비교 시도
    try:
        g_num = float(str(golden).replace(',', '').replace(' ', ''))
        p_num = float(str(predicted).replace(',', '').replace(' ', ''))
        # 컬럼 타입별 허용 오차
        if col_name in TYPE_CONFIG['int_strict']['cols']:
            return (g_num == p_num), 'int_compare'
        if col_name in TYPE_CONFIG['float_ratio']['cols']:
            return (abs(g_num - p_num) <= TYPE_CONFIG['float_ratio']['tolerance']), 'ratio_compare'
        # 그 외 숫자 (등급컷, 환산점수): 소수점 둘째자리
        return (abs(g_num - p_num) <= 0.01), 'numeric_compare'
    except (ValueError, TypeError):
        pass

    # 문자열 비교 (정규화)
    g_str = re.sub(r'[\s,]+', ' ', str(golden).strip())
    p_str = re.sub(r'[\s,]+', ' ', str(predicted).strip())
    return (g_str == p_str), 'string_compare'


# ─────────────────────────────────────────────
# 평가 본체
# ─────────────────────────────────────────────

@dataclass
class EvaluationResult:
    targets: list[str]
    golden_rows: int = 0
    pred_rows: int = 0
    matched_pks: int = 0
    missing_pks: list[tuple] = field(default_factory=list)
    extra_pks: list[tuple] = field(default_factory=list)

    # 셀 단위
    eval_cols: list[str] = field(default_factory=list)
    col_total: dict = field(default_factory=lambda: defaultdict(int))
    col_match: dict = field(default_factory=lambda: defaultdict(int))
    col_golden_filled: dict = field(default_factory=lambda: defaultdict(int))

    # 대학별
    univ_match_cells: dict = field(default_factory=lambda: defaultdict(int))
    univ_total_cells: dict = field(default_factory=lambda: defaultdict(int))
    univ_matched_pks: dict = field(default_factory=lambda: defaultdict(int))
    univ_golden_pks: dict = field(default_factory=lambda: defaultdict(int))

    # 상세 (mismatched_rows에 들어갈 항목)
    mismatches: list[dict] = field(default_factory=list)

    def cell_match_rate(self) -> float:
        total = sum(self.col_total.values())
        match = sum(self.col_match.values())
        return match / total if total else 0.0

    def pk_match_rate(self) -> float:
        return self.matched_pks / self.golden_rows if self.golden_rows else 0.0

    def extra_rate(self) -> float:
        return len(self.extra_pks) / self.pred_rows if self.pred_rows else 0.0


def evaluate(golden_df: pd.DataFrame, pred_df: pd.DataFrame, targets: list[str]) -> EvaluationResult:
    # 타겟 대학 필터링
    golden_df = golden_df[golden_df['대학'].isin(targets)].copy()
    pred_df = pred_df[pred_df['대학'].isin(targets)].copy()

    # PK 생성
    golden_df['_pk'] = golden_df.apply(build_pk, axis=1)
    pred_df['_pk'] = pred_df.apply(build_pk, axis=1)

    # PK 중복 제거 (마지막 행 유지 — 골든셋이 정제 안 됐을 경우 대비)
    golden_df = golden_df.drop_duplicates(subset='_pk', keep='last')
    pred_df = pred_df.drop_duplicates(subset='_pk', keep='last')

    golden_pks = set(golden_df['_pk'])
    pred_pks = set(pred_df['_pk'])
    matched_pks = golden_pks & pred_pks

    # 평가 대상 컬럼: 골든셋에 있고 EXCLUDED/PK 아닌 모든 컬럼
    eval_cols = [c for c in golden_df.columns
                 if c not in EXCLUDED_COLS
                 and c not in PK_COLS
                 and c != '_pk']

    result = EvaluationResult(
        targets=targets,
        golden_rows=len(golden_df),
        pred_rows=len(pred_df),
        matched_pks=len(matched_pks),
        missing_pks=sorted(golden_pks - pred_pks)[:200],
        extra_pks=sorted(pred_pks - golden_pks)[:200],
        eval_cols=eval_cols,
    )

    # 대학별 골든셋 PK 카운트
    for pk in golden_pks:
        univ = pk[0]
        result.univ_golden_pks[univ] += 1
    for pk in matched_pks:
        univ = pk[0]
        result.univ_matched_pks[univ] += 1

    # 매칭된 PK들에 대해 셀 비교
    # tuple PK를 그대로 인덱스로 쓰면 .loc가 다중 인덱서로 오인하므로
    # dict로 변환해 안전하게 접근
    g_rows = {pk: row for pk, row in zip(golden_df['_pk'], golden_df.to_dict('records'))}
    p_rows = {pk: row for pk, row in zip(pred_df['_pk'], pred_df.to_dict('records'))}

    for pk in matched_pks:
        g_row = g_rows.get(pk)
        p_row = p_rows.get(pk)
        if g_row is None or p_row is None:
            continue
        univ = pk[0]
        for col in eval_cols:
            if col not in p_row:
                continue
            g_val = g_row.get(col)
            p_val = p_row.get(col)

            # 골든셋이 NULL인 셀은 평가에서 제외 (충진 평가 아닌 정답 비교)
            if pd.isna(g_val):
                continue

            result.col_total[col] += 1
            result.col_golden_filled[col] += 1
            result.univ_total_cells[univ] += 1

            match, reason = cells_match(g_val, p_val, col)
            if match:
                result.col_match[col] += 1
                result.univ_match_cells[univ] += 1
            else:
                if len(result.mismatches) < 1000:  # 너무 많으면 자름
                    result.mismatches.append({
                        '대학': pk[0], '전형': pk[1], '모집단위': pk[2],
                        '컬럼': col, '골든셋': g_val, '에이전트': p_val,
                        '판정사유': reason,
                    })

    return result


# ─────────────────────────────────────────────
# 리포트 생성
# ─────────────────────────────────────────────

def print_summary(result: EvaluationResult) -> None:
    print('━━━ 평가 결과 요약 ━━━')
    print(f'타겟 대학: {", ".join(result.targets)}')
    print(f'골든셋 행: {result.golden_rows:>6,}')
    print(f'에이전트 행: {result.pred_rows:>6,}')
    print(f'PK 매칭률: {result.pk_match_rate()*100:>6.1f}%  ({result.matched_pks}/{result.golden_rows})')
    print(f'잉여행률  : {result.extra_rate()*100:>6.1f}%  ({len(result.extra_pks)} extra rows)')
    print(f'셀 일치율 : {result.cell_match_rate()*100:>6.1f}%  ({sum(result.col_match.values()):,}/{sum(result.col_total.values()):,})')

    print('\n━━━ 대학별 ━━━')
    print(f'{"대학":15s} {"PK매칭":>10s} {"셀일치":>10s}')
    for univ in result.targets:
        g_pks = result.univ_golden_pks.get(univ, 0)
        m_pks = result.univ_matched_pks.get(univ, 0)
        t_cells = result.univ_total_cells.get(univ, 0)
        m_cells = result.univ_match_cells.get(univ, 0)
        pk_rate = (m_pks / g_pks * 100) if g_pks else 0
        cell_rate = (m_cells / t_cells * 100) if t_cells else 0
        print(f'  {univ:13s} {pk_rate:>5.1f}% ({m_pks}/{g_pks})  {cell_rate:>5.1f}% ({m_cells}/{t_cells})')

    print('\n━━━ 컬럼별 정확도 ━━━')
    print(f'{"컬럼":30s} {"채워진 셀":>10s} {"일치율":>10s}')
    for col in result.eval_cols:
        total = result.col_total.get(col, 0)
        match = result.col_match.get(col, 0)
        if total == 0:
            continue
        rate = match / total * 100
        print(f'  {col:28s} {total:>8,d}  {rate:>5.1f}%')


def write_xlsx_report(result: EvaluationResult, out_path: str) -> None:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    # 스타일
    BOLD = Font(name='맑은 고딕', size=11, bold=True, color='FFFFFF')
    NORMAL = Font(name='맑은 고딕', size=10)
    HEADER_FILL = PatternFill('solid', start_color='1F4E78')
    CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
    BORDER = Border(*[Side(style='thin', color='BFBFBF')] * 4)

    def style_header(ws, n_cols):
        for i in range(1, n_cols + 1):
            c = ws.cell(row=1, column=i)
            c.font = BOLD
            c.fill = HEADER_FILL
            c.alignment = CENTER
            c.border = BORDER

    # Sheet 1: summary
    ws = wb.create_sheet('summary')
    rows = [
        ('타겟 대학', ', '.join(result.targets)),
        ('골든셋 행 수', result.golden_rows),
        ('에이전트 행 수', result.pred_rows),
        ('PK 매칭률', f'{result.pk_match_rate()*100:.2f}%'),
        ('잉여행 수', len(result.extra_pks)),
        ('잉여행률', f'{result.extra_rate()*100:.2f}%'),
        ('전체 셀 일치율', f'{result.cell_match_rate()*100:.2f}%'),
        ('일치 셀 수', sum(result.col_match.values())),
        ('비교 가능 셀 수', sum(result.col_total.values())),
    ]
    ws['A1'] = '지표'; ws['B1'] = '값'
    style_header(ws, 2)
    for i, (k, v) in enumerate(rows, start=2):
        ws.cell(row=i, column=1, value=k).font = NORMAL
        ws.cell(row=i, column=2, value=v).font = NORMAL
    ws.column_dimensions['A'].width = 25
    ws.column_dimensions['B'].width = 50

    # Sheet 2: 대학별
    ws = wb.create_sheet('by_university')
    ws.append(['대학', '골든셋_PK', '매칭_PK', 'PK매칭률(%)', '비교셀', '일치셀', '셀일치율(%)'])
    style_header(ws, 7)
    for univ in result.targets:
        g_pks = result.univ_golden_pks.get(univ, 0)
        m_pks = result.univ_matched_pks.get(univ, 0)
        t_cells = result.univ_total_cells.get(univ, 0)
        m_cells = result.univ_match_cells.get(univ, 0)
        ws.append([
            univ, g_pks, m_pks,
            round((m_pks / g_pks * 100) if g_pks else 0, 2),
            t_cells, m_cells,
            round((m_cells / t_cells * 100) if t_cells else 0, 2),
        ])
    for i in range(1, 8):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 14

    # Sheet 3: 컬럼별
    ws = wb.create_sheet('by_column')
    ws.append(['컬럼', '비교셀', '일치셀', '일치율(%)'])
    style_header(ws, 4)
    for col in result.eval_cols:
        total = result.col_total.get(col, 0)
        match = result.col_match.get(col, 0)
        if total == 0:
            continue
        ws.append([col, total, match, round(match / total * 100, 2)])
    ws.column_dimensions['A'].width = 30
    for i in range(2, 5):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 12

    # Sheet 4: missing_rows (골든셋에 있는데 에이전트가 못 찾은)
    ws = wb.create_sheet('missing_rows')
    ws.append(['대학', '전형', '모집단위'])
    style_header(ws, 3)
    for pk in result.missing_pks:
        ws.append(list(pk))
    ws.column_dimensions['A'].width = 18
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 25

    # Sheet 5: extra_rows (에이전트가 만들어낸 잉여행)
    ws = wb.create_sheet('extra_rows')
    ws.append(['대학', '전형', '모집단위'])
    style_header(ws, 3)
    for pk in result.extra_pks:
        ws.append(list(pk))
    ws.column_dimensions['A'].width = 18
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 25

    # Sheet 6: mismatched_cells (값이 다른 셀들)
    ws = wb.create_sheet('mismatched_cells')
    ws.append(['대학', '전형', '모집단위', '컬럼', '골든셋', '에이전트', '판정사유'])
    style_header(ws, 7)
    for m in result.mismatches:
        ws.append([m['대학'], m['전형'], m['모집단위'], m['컬럼'],
                   m['골든셋'], m['에이전트'], m['판정사유']])
    for i, w in enumerate([18, 30, 25, 20, 15, 15, 15], start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    wb.save(out_path)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='adiga 에이전트 결과 평가')
    ap.add_argument('golden', help='골든셋 엑셀 (예: 2025_어디가입결_통합본.xlsx)')
    ap.add_argument('predicted', help='에이전트 결과 엑셀')
    ap.add_argument('--out', default='evaluation_report.xlsx', help='리포트 출력 경로')
    ap.add_argument('--sheet', default='수시', help='시트명 (default: 수시)')
    ap.add_argument('--pred-sheet', default=None, help='에이전트 결과 시트명 (default: --sheet와 동일)')
    ap.add_argument('--targets', nargs='+', default=DEFAULT_TARGETS,
                    help='평가 대상 대학 (default: 8개 타겟)')
    args = ap.parse_args()

    print(f'[1/3] 골든셋 로딩: {args.golden}')
    golden = load_sheet(args.golden, args.sheet)
    print(f'      → {len(golden):,}행, {len(golden.columns)}컬럼')

    pred_sheet = args.pred_sheet or args.sheet
    print(f'[2/3] 에이전트 결과 로딩: {args.predicted} (시트: {pred_sheet})')
    pred = load_sheet(args.predicted, pred_sheet)
    print(f'      → {len(pred):,}행, {len(pred.columns)}컬럼')

    print(f'[3/3] 평가 실행 (타겟 {len(args.targets)}개 대학)')
    result = evaluate(golden, pred, args.targets)

    print()
    print_summary(result)

    write_xlsx_report(result, args.out)
    print(f'\n✓ 리포트 저장: {args.out}')


if __name__ == '__main__':
    main()
