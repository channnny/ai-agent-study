"""adiga HTML → 4시트 raw DataFrame (T2 단계)

실제 HTML 구조:
  - div.tabCon × 4: [0]=공통, [1]=학생부종합, [2]=학생부교과, [3]=수능위주
  - 각 tabCon 안에 li.accordionItem:
    - "Q1." 시작 → eval 시트
    - "Q2." 시작 → result 시트
  - Q1 eval: 전형별 주요사항 테이블 (컬럼1=전형명, 컬럼2=설명텍스트)
  - Q2 result: 입시결과 표 (모집인원/경쟁률/충원합격순위/등급컷 등)

사용법:
    python parse.py --unvcd 0000063 --univ 가천대학교 \\
                    --html output/raw_html/0000063.html \\
                    --output output/parsed/0000063.json
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, Tag

# ─────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────
NULL_MARKS = {"-", "–", "—", "", " ", "N/A", "해당없음", "미공개", "·"}


def cell_text(tag: Tag) -> str:
    return tag.get_text(separator=" ", strip=True)


def clean(s: str) -> Optional[str]:
    v = s.strip()
    return None if v in NULL_MARKS else v


def to_int(s: Optional[str]) -> Optional[int]:
    if s is None:
        return None
    try:
        return int(re.sub(r"[,\s약명]", "", s).rstrip("명"))
    except ValueError:
        return None


def to_float(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    try:
        # ':n' 비율 표기 제거 (예: '3.75:1', '12.56:1' → '3.75', '12.56')
        v = re.sub(r":\d+(\.\d+)?$", "", s.strip())
        return float(re.sub(r"[,\s%점]", "", v))
    except ValueError:
        return None


def is_number(s: str) -> bool:
    try:
        float(s.replace(",", "").replace(" ", ""))
        return True
    except (ValueError, TypeError):
        return False


# ─────────────────────────────────────────────
# 탭 인덱스 → 시트 분류
# ─────────────────────────────────────────────
# tabCon[0] = Ⅰ공통  → skip
# tabCon[1] = Ⅱ학생부종합 → susi
# tabCon[2] = Ⅲ학생부교과 → susi
# tabCon[3] = Ⅳ수능위주   → jeongsi
TAB_INDEX_TO_TYPE = {0: "skip", 1: "susi", 2: "susi", 3: "jeongsi"}


# ─────────────────────────────────────────────
# eval 시트 파싱 (Q1 accordionItem)
# ─────────────────────────────────────────────

_EVAL_SUBROW_MARKS = re.compile(
    r"^(?:\d+\s*단계|배수|방법|선발방법|전형요소|반영비율|서류|면접|진행방법|"
    r"평가위원|모집\s*인원|\d+$)",
    re.I,
)
_EVAL_HEADER_TEXTS = re.compile(
    r"전형요소\s*및\s*반영비율|배수\s*서류\s*면접|선발방법\s*전형요소",
    re.I,
)


def _is_garbage_jeon(jeon: str) -> bool:
    """단계·배수 등 서브헤더 셀을 전형명으로 오해한 경우 True."""
    j = jeon.strip()
    if not j:
        return False
    if re.match(r"^\d+$", j):
        return True
    if _EVAL_SUBROW_MARKS.match(j):
        return True
    return False


def parse_eval_item(item: Tag, university: str, sheet_prefix: str) -> list[dict]:
    """Q1 accordionItem → eval 시트 row 리스트.

    같은 전형명이 여러 테이블에 걸쳐 나타나면 raw_text를 합산한다.
    '2 단계' 처럼 전형명이 아닌 서브행은 직전 전형 row에 이어붙인다.
    """
    # 전형 순서 보존을 위해 OrderedDict 대신 list + dict 조합
    merged: dict[str, str] = {}   # jeon → accumulated raw_text
    order: list[str] = []         # 등장 순서

    tables = item.find_all("table")

    for tbl in tables:
        tbl_rows = tbl.find_all("tr")
        if not tbl_rows:
            continue

        header_text = cell_text(tbl_rows[0])
        # 헤더가 "전형요소 및 반영비율 배수 서류 면접" 같은 서브헤더 → 방법 요약 테이블
        is_method_table = bool(_EVAL_HEADER_TEXTS.search(header_text))
        is_jeon_table = any(k in header_text for k in ["전형", "모집단위", "주요사항"])

        if not (is_jeon_table or is_method_table) or len(tbl_rows) < 2:
            # 전형명 식별 불가 → 전체 텍스트를 빈-전형 row에 이어붙임
            raw = cell_text(tbl)
            if raw.strip():
                merged.setdefault("", "")
                merged[""] = (merged[""] + " " + raw).strip()
                if "" not in order:
                    order.append("")
            continue

        last_real_jeon: str = ""
        for tr in tbl_rows[1:]:
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            jeon_cell = cell_text(cells[0]).strip()
            desc_cell = " ".join(cell_text(c) for c in cells[1:]).strip()

            if not jeon_cell and not desc_cell:
                continue

            # 서브헤더 행 (예: "배수 서류 면접") 스킵
            if _EVAL_HEADER_TEXTS.search(jeon_cell + " " + desc_cell):
                continue

            if _is_garbage_jeon(jeon_cell):
                # 단계 서브행 → 마지막 실제 전형에 이어붙임
                target = last_real_jeon
                merged.setdefault(target, "")
                merged[target] = (merged[target] + " " + jeon_cell + " " + desc_cell).strip()
            else:
                # 실제 전형 행
                if jeon_cell not in merged:
                    merged[jeon_cell] = ""
                    order.append(jeon_cell)
                merged[jeon_cell] = (merged[jeon_cell] + " " + desc_cell).strip()
                last_real_jeon = jeon_cell

    # 테이블이 없으면 텍스트 그대로
    if not tables:
        raw = cell_text(item)
        raw = re.sub(r"^Q1\.\s*", "", raw)
        if raw.strip():
            merged[""] = raw.strip()
            order.append("")

    # 빈-전형 raw_text에서 단락별 전형 추출 시도
    if "" in merged and merged[""]:
        raw_full = re.sub(r"^Q1\.\s*", "", merged[""])
        raw_full = re.sub(r"^[^\n]*A제목\s*없음\s*", "", raw_full)
        merged[""] = raw_full.strip()

    rows: list[dict] = []
    for jeon in order:
        raw_text = merged.get(jeon, "") or ""
        raw_text = raw_text.strip()
        if not raw_text:
            continue
        rows.append({
            "대학": university,
            "전형": jeon,
            "모집단위": "전체",
            "raw_text": raw_text[:8000],
        })

    return rows


# ─────────────────────────────────────────────
# result 시트 파싱 (Q2 accordionItem)
# ─────────────────────────────────────────────

def detect_cut_columns(header_cells: list[str]) -> list[tuple[str, str]]:
    """
    헤더 셀 목록에서 컷 컬럼 타입·이름 매핑 반환.
    반환: [(컬럼_prefix, 컷_이름), ...]
    예: [("학생부등급", "70컷"), ("학생부등급", "90컷"), ...]
    """
    cols: list[tuple[str, str]] = []
    header_text = " ".join(header_cells)

    # 환산점수 계열 (대학별환산)
    if "환산" in header_text or "대학별" in header_text:
        for cut in ["최고", "평균", "50컷", "70컷", "80컷", "100컷", "총점"]:
            pattern = cut.replace("컷", r"[\s%]*cut") if "컷" in cut else cut
            if re.search(pattern, header_text, re.I):
                cols.append(("대학별환산", cut))

    # 백분위 계열
    if "백분위" in header_text:
        for cut in ["총점_70컷", "국어_70컷", "수학_70컷", "영어_70컷",
                    "탐구1_70컷", "탐구2_70컷", "한국사_70컷"]:
            cols.append(("백분위", cut))

    # 학생부등급 계열 (기본)
    if not cols or "학생부등급" in header_text or "교과성적" in header_text:
        for cut in ["최고", "평균", "50컷", "70컷", "80컷", "90컷", "최저"]:
            if "컷" in cut:
                num = cut.replace("컷", "")
                pattern = rf"{num}\s*(?:%|컷|cut)"
            else:
                pattern = cut
            if re.search(pattern, header_text, re.I):
                cols.append(("학생부등급", cut))
        # 85% → 80컷 특수 매핑 (경북대 형식 등)
        if re.search(r"85\s*%", header_text) and not any(c[1] == "80컷" for c in cols):
            cols.append(("학생부등급", "80컷"))

    return cols


def find_header_row(tbl: Tag) -> tuple[int, list[str]]:
    """헤더 행 인덱스와 셀 목록 반환."""
    all_trs = tbl.find_all("tr")
    combined_header: list[str] = []
    header_idx = -1

    for idx, tr in enumerate(all_trs):
        txt = cell_text(tr)
        if "모집" in txt and ("경쟁률" in txt or "인원" in txt):
            # 이 행 + 다음 몇 행을 헤더로 합침 (멀티행 헤더)
            header_idx = idx
            for i in range(idx, min(idx + 4, len(all_trs))):
                tr_cells = [cell_text(c) for c in all_trs[i].find_all(["td", "th"])]
                combined_header.extend(tr_cells)
                # 마지막 헤더 행 감지: 다음 행이 숫자 시작이면 헤더 끝
                if i + 1 < len(all_trs):
                    next_tr = all_trs[i + 1]
                    next_cells = [cell_text(c) for c in next_tr.find_all(["td", "th"])]
                    if next_cells and is_number(next_cells[0].replace("군", "")):
                        break
                    # 숫자로 시작하는 두번째 셀이 있으면 헤더 끝
                    if len(next_cells) >= 2 and is_number(next_cells[1]):
                        break
            break

    return header_idx, combined_header


_BANGYEONGGWA_MAP = {
    "전 과목": "전교과",
    "전과목": "전교과",
    "전체": "전교과",
    "전체 과목": "전교과",
}


def clean_jeon_name(s: str) -> str:
    """전형명 정규화: 괄호 공백 제거, 후미 주석 제거."""
    s = s.strip()
    # 괄호 주변 공백 제거: "농어촌 ( 종합 )" → "농어촌(종합)"
    s = re.sub(r"\s*\(\s*", "(", s)
    s = re.sub(r"\s*\)\s*", ")", s)
    # 쉼표 주변 공백 제거
    s = re.sub(r"\s*,\s*", ",", s)
    # 전형명 뒤에 붙은 연도/주석 괄호 제거: "지역균형 전형(2026학년도...)" → "지역균형 전형"
    # 단, 이름 안의 괄호(짧은 것)는 보존
    s = re.sub(r"\((?=[^)]{15,})\)", "", s)  # 15자 이상 내용은 제거 시작부
    s = re.sub(r"\([^)]{15,}\)$", "", s)     # 15자 이상 내용 닫힘도 제거
    return s.strip()


def normalize_bangyeonggwa(v: str) -> Optional[str]:
    s = v.strip()
    if s in _BANGYEONGGWA_MAP:
        return _BANGYEONGGWA_MAP[s]
    s = re.sub(r"[·•]", ",", s)
    return s


def parse_susi_result_table(
    tbl: Tag, university: str, current_jeon: Optional[str]
) -> tuple[Optional[str], list[dict]]:
    """수시 결과 테이블 파싱."""
    all_trs = tbl.find_all("tr")
    if not all_trs:
        return current_jeon, []

    # 전형명 추출 (첫 행 1~3개 셀인 경우)
    jeon = current_jeon
    first_tr = all_trs[0]
    first_cells = first_tr.find_all(["td", "th"])
    first_text = cell_text(first_tr)

    if len(first_cells) <= 3:
        if len(first_cells) == 2 and cell_text(first_cells[0]).strip() in ("모집단위", "모집 단위"):
            # "모집단위 | 전형명" 형태 — 두 번째 셀이 전형명
            jeon = clean_jeon_name(cell_text(first_cells[1]))
        elif "모집단위" in first_text:
            after = re.sub(r".*모집단위\s*", "", first_text).strip()
            if after:
                jeon = clean_jeon_name(after)
        elif re.search(r"전형", first_text) and len(first_text) < 60:
            jeon = clean_jeon_name(first_text)

    header_idx, header_cells = find_header_row(tbl)
    if header_idx == -1:
        return jeon, []

    header_text = " ".join(header_cells)
    cut_cols = detect_cut_columns(header_cells)

    # 기준 값 — header_text에 없을 수 있으므로 앞 몇 행도 검색
    full_pre_text = " ".join(cell_text(tr) for tr in all_trs[:max(3, header_idx + 1)])
    kijun_src = header_text + " " + full_pre_text
    if "최종등록자" in kijun_src:
        kijun = "최종등록자"
    elif "입학자" in kijun_src:
        kijun = "입학자"
    elif "합격자" in kijun_src:
        kijun = "합격자"
    else:
        kijun = ""

    # 단과대학 extra column 감지 (경북대 형식)
    # 지원인원이 모집인원 뒤에 오고 경쟁률 전에 있으면 → 컬럼 오프셋 존재
    has_dankkwa_col = bool(re.search(r"지원\s*인원.{0,30}경쟁률", header_text))

    rows: list[dict] = []
    last_dept: str = ""
    last_bangyeonggwa: str = ""

    for tr in all_trs[header_idx + 1:]:
        cells = [cell_text(c) for c in tr.find_all(["td", "th"])]
        if len(cells) < 3:
            continue

        if has_dankkwa_col:
            # 경북대 형식: 단과대학 컬럼이 존재
            # 첫 번째 셀이 텍스트, 두 번째도 텍스트 → 단과대학 + 모집단위 행
            if not is_number(cells[0]) and len(cells) > 1 and not is_number(cells[1]):
                if cells[1] and cells[1] not in NULL_MARKS:
                    last_dept = cells[1]
                    dept, c_off = cells[1], 2  # 데이터가 2번째 인덱스부터
                else:
                    continue
            else:
                # 단과대학 셀 없는 행 (병합): 모집단위가 첫 번째 셀
                dept, c_off = cells[0], 1
                if not dept or dept in NULL_MARKS:
                    dept = last_dept
            if not dept:
                continue
            mojip = to_int(clean(cells[c_off]))     if len(cells) > c_off     else None
            if mojip is None:
                continue
            kyung = to_float(clean(cells[c_off+2])) if len(cells) > c_off+2  else None
            chung = to_int(clean(cells[c_off+4]))   if len(cells) > c_off+4  else None
            # 고정 오프셋: +8=평균, +9=표준편차(skip), +10=50컷, +11=70컷, +12=80컷(85%)
            _DANKKWA_CUTS = [
                (8, "학생부등급", "평균"),
                (10, "학생부등급", "50컷"),
                (11, "학생부등급", "70컷"),
                (12, "학생부등급", "80컷"),
            ]
            cut_values: dict[str, Optional[float]] = {}
            for rel_off, prefix, cut_name in _DANKKWA_CUTS:
                idx = c_off + rel_off
                if idx < len(cells):
                    cut_values[f"{prefix}_{cut_name}"] = to_float(clean(cells[idx]))
            row: dict = {
                "대학": university,
                "전형": jeon or "",
                "모집단위": dept,
                "모집인원": mojip,
                "경쟁률": kyung,
                "충원합격순위": chung,
                "기준": kijun or None,
                **cut_values,
            }
            rows.append(row)
            continue

        dept = cells[0].strip()
        if not dept or dept in NULL_MARKS or "모집단위" in dept:
            continue
        # 전형명 행 감지
        if len(cells) <= 3 and not is_number(cells[1] if len(cells) > 1 else ""):
            if "모집단위" in dept:
                after = re.sub(r".*모집단위\s*", "", dept).strip()
                if after:
                    jeon = after
            elif len(cells) == 2 and cell_text(first_cells[0]).strip() not in ("모집단위",):
                # 두 번째 셀이 있고 순수 전형명 행
                if cells[1] and re.search(r"전형", cells[1]):
                    jeon = cells[1].strip()
            continue

        mojip = to_int(clean(cells[1])) if len(cells) > 1 else None
        if mojip is None:
            continue

        kyung  = to_float(clean(cells[2])) if len(cells) > 2 else None
        chung  = to_int(clean(cells[3]))   if len(cells) > 3 else None

        cut_values = {}
        for i, (prefix, cut_name) in enumerate(cut_cols):
            idx = 4 + i
            if idx < len(cells):
                cut_values[f"{prefix}_{cut_name}"] = to_float(clean(cells[idx]))

        # 반영교과 (마지막 셀이 텍스트)
        bangyeonggwa = ""
        if cells:
            last_cell = cells[-1].strip()
            if last_cell and not is_number(last_cell) and last_cell not in NULL_MARKS:
                # 정규화
                bangyeonggwa = normalize_bangyeonggwa(last_cell) or last_cell
                last_bangyeonggwa = bangyeonggwa
            else:
                bangyeonggwa = last_bangyeonggwa

        row: dict = {
            "대학": university,
            "전형": jeon or "",
            "모집단위": dept,
            "모집인원": mojip,
            "경쟁률": kyung,
            "충원합격순위": chung,
            "기준": kijun or None,
            "반영교과": bangyeonggwa or None,
        }
        row.update(cut_values)
        rows.append(row)

    return jeon, rows


def parse_jeongsi_result_table(
    tbl: Tag, university: str, jeon_name: str
) -> list[dict]:
    """정시 결과 테이블 파싱.
    구분(군) | 모집단위 | 최초 | 이월 | 최종 | 경쟁률 | 충원 | 환산/백분위...
    """
    all_trs = tbl.find_all("tr")
    if not all_trs:
        return []

    header_idx, header_cells = find_header_row(tbl)
    if header_idx == -1:
        return []

    header_text = " ".join(header_cells)

    # 컬럼 레이아웃 결정
    has_goon = "구분" in header_text or "군" in header_text
    has_mojip_split = "최초" in header_text and "이월" in header_text

    rows: list[dict] = []
    current_gun = ""

    for tr in all_trs[header_idx + 1:]:
        cells = [cell_text(c) for c in tr.find_all(["td", "th"])]
        if len(cells) < 3:
            continue

        col = 0
        # 군 처리
        gun = ""
        if has_goon:
            gun_val = cells[0].strip()
            if gun_val in {"가군", "나군", "다군", "가", "나", "다"}:
                current_gun = gun_val
                col = 1
            elif gun_val and not is_number(gun_val):
                col = 1
                current_gun = gun_val
            else:
                col = 0
            gun = current_gun

        # 모집단위
        if col >= len(cells):
            continue
        dept = cells[col].strip()
        col += 1
        if not dept or dept in NULL_MARKS:
            continue

        # 모집인원
        mojip_sochoe = to_int(clean(cells[col])) if col < len(cells) else None
        col += 1
        mojip_iwol   = to_int(clean(cells[col])) if col < len(cells) else None
        col += 1
        mojip_choongjong = to_int(clean(cells[col])) if col < len(cells) and has_mojip_split else None
        if has_mojip_split:
            col += 1
        else:
            mojip_choongjong = mojip_sochoe
            mojip_sochoe = None

        # 경쟁률
        kyung = to_float(clean(cells[col])) if col < len(cells) else None
        col += 1
        # 충원합격순위
        chung = to_int(clean(cells[col])) if col < len(cells) else None
        col += 1

        # 환산점수·백분위 (나머지 숫자들)
        rest_nums: list[Optional[float]] = []
        for i in range(col, len(cells)):
            rest_nums.append(to_float(clean(cells[i])))

        row: dict = {
            "대학": university,
            "전형": jeon_name,
            "모집단위": dept,
            "군": gun or None,
            "모집인원_최초": mojip_sochoe,
            "모집인원_이월": mojip_iwol,
            "모집인원_최종": mojip_choongjong,
            "경쟁률": kyung,
            "충원합격순위": chung,
        }

        # 환산점수/백분위 숫자 배치
        cut_labels = ["환산점수_70컷", "환산점수_총점",
                      "백분위_국어_70컷", "백분위_수학_70컷", "백분위_영어_70컷",
                      "백분위_탐구1_70컷", "백분위_탐구2_70컷", "백분위_한국사_70컷",
                      "수학선택_확률통계_비율", "수학선택_미적분_비율", "수학선택_기하_비율"]
        for label, val in zip(cut_labels, rest_nums):
            if val is not None:
                row[label] = val

        rows.append(row)

    return rows


# ─────────────────────────────────────────────
# 메인 파서
# ─────────────────────────────────────────────

class AdigaParser:
    def __init__(self, html: str, university: str):
        self.soup = BeautifulSoup(html, "lxml")
        self.university = university
        self.sheets: dict[str, list[dict]] = {
            "susi_result":    [],
            "susi_eval":      [],
            "jeongsi_result": [],
            "jeongsi_eval":   [],
        }

    def parse(self) -> dict[str, list[dict]]:
        tab_divs = self.soup.find_all("div", class_="tabCon")

        if len(tab_divs) >= 4:
            self._parse_by_tab_divs(tab_divs)
        else:
            # 탭 구조 없으면 전체 fallback
            self._fallback_parse()

        return self.sheets

    def _parse_by_tab_divs(self, tab_divs: list[Tag]) -> None:
        """tabCon div 4개를 인덱스로 분류해 파싱."""
        for tab_idx, tab_div in enumerate(tab_divs[:4]):
            tab_type = TAB_INDEX_TO_TYPE.get(tab_idx, "skip")
            if tab_type == "skip":
                continue

            accordion_items = tab_div.find_all("li", class_="accordionItem")
            for item in accordion_items:
                item_text = item.get_text(strip=True)

                if item_text.startswith("Q1.") or "전형별 주요사항" in item_text[:30]:
                    # 평가기준 → eval
                    sheet_name = f"{tab_type}_eval"
                    rows = parse_eval_item(item, self.university, sheet_name)
                    self.sheets[sheet_name].extend(rows)

                elif item_text.startswith("Q2.") or "전형 결과" in item_text[:30]:
                    # 결과 → result
                    sheet_name = f"{tab_type}_result"
                    self._parse_result_item(item, tab_type, sheet_name)

    def _parse_result_item(
        self, item: Tag, tab_type: str, sheet_name: str
    ) -> None:
        """Q2 결과 accordionItem 안의 테이블들을 파싱."""
        tables = item.find_all("table")
        if not tables:
            return

        # jeongsi: 전형명을 같은 탭의 Q1에서 가져와야 하므로 기본값 사용
        if tab_type == "jeongsi":
            # Q1 텍스트에서 전형명 추출 시도
            parent_div = item.parent.parent if item.parent else None
            jeon_name = self._extract_jeongsi_jeon(parent_div) or "수능위주"
            for tbl in tables:
                rows = parse_jeongsi_result_table(tbl, self.university, jeon_name)
                self.sheets[sheet_name].extend(rows)
        else:
            # susi: 테이블마다 전형명 추출
            # ◈ 마커로 전형명 사전 추출 (경북대 등)
            item_text = item.get_text(separator="\n", strip=True)
            pre_jeons = re.findall(r"◈\s*([^\n◈※]{2,50}?)(?:\s*\n|\s*※|\s*◈|$)", item_text)
            pre_jeons = [clean_jeon_name(j) for j in pre_jeons if j.strip()]
            pre_jeon_idx = 0

            current_jeon: Optional[str] = pre_jeons[0] if pre_jeons else None
            for tbl in tables:
                if not self._is_result_table(tbl):
                    continue
                jeon, rows = parse_susi_result_table(tbl, self.university, current_jeon)
                if jeon:
                    current_jeon = jeon
                elif pre_jeons:
                    # 테이블에서 전형명 추출 실패 시 ◈ 목록 순서대로 사용
                    if pre_jeon_idx < len(pre_jeons):
                        current_jeon = pre_jeons[pre_jeon_idx]
                    pre_jeon_idx += 1
                self.sheets[sheet_name].extend(rows)

    def _extract_jeongsi_jeon(self, parent_div: Optional[Tag]) -> Optional[str]:
        """tabCon div에서 Q1 accordionItem의 전형명 목록을 텍스트로 반환."""
        if parent_div is None:
            return None
        q1_items = [
            li for li in parent_div.find_all("li", class_="accordionItem")
            if li.get_text(strip=True).startswith("Q1.")
        ]
        if q1_items:
            raw = q1_items[0].get_text(strip=True)
            # 첫 번째 전형명 추출 시도
            m = re.search(r"전형별 주요사항(.{5,40}?)(?:수능|전형|성적|모집)", raw)
            if m:
                return m.group(1).strip()
        return None

    @staticmethod
    def _is_result_table(tbl: Tag) -> bool:
        header_text = tbl.get_text(separator=" ", strip=True)
        has_mojip = "모집" in header_text and ("경쟁률" in header_text or "인원" in header_text)
        has_score = any(k in header_text.lower() for k in [
            "학생부등급", "학생부 등급", "cut", "교과성적", "환산점수", "백분위", "충원", "추합",
        ])
        return has_mojip and has_score

    def _fallback_parse(self) -> None:
        """탭 구조 없을 때 전체 테이블 스캔."""
        current_jeon: Optional[str] = None
        for tbl in self.soup.find_all("table"):
            if self._is_result_table(tbl):
                jeon, rows = parse_susi_result_table(tbl, self.university, current_jeon)
                if jeon:
                    current_jeon = jeon
                self.sheets["susi_result"].extend(rows)


# ─────────────────────────────────────────────
# 검증
# ─────────────────────────────────────────────

def validate_sheets(sheets: dict[str, list[dict]]) -> list[str]:
    issues: list[str] = []
    for sheet_name, rows in sheets.items():
        if not rows:
            issues.append(f"{sheet_name}: 0행 (빈 시트)")
            continue
        for i, row in enumerate(rows[:5]):
            for pk_col in ["대학", "모집단위"]:
                if not row.get(pk_col):
                    issues.append(f"{sheet_name}[{i}]: PK '{pk_col}' 비어있음")
    return issues


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="adiga HTML → 4시트 JSON")
    ap.add_argument("--unvcd",  required=True)
    ap.add_argument("--univ",   required=True)
    ap.add_argument("--html",   required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--errors", default="output/logs/error_log.json")
    args = ap.parse_args()

    html_path = Path(args.html)
    if not html_path.exists():
        print(f"[오류] HTML 파일 없음: {args.html}")
        return 1

    print(f"[T2 파싱] {args.unvcd} ({args.univ}): 시작")
    html = html_path.read_text(encoding="utf-8")

    parser = AdigaParser(html, args.univ)
    sheets = parser.parse()

    issues = validate_sheets(sheets)
    for issue in issues:
        print(f"  [경고] {issue}")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(sheets, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total = sum(len(v) for v in sheets.values())
    print(f"[T2 파싱] {args.unvcd}: 완료 — 총 {total}행")
    for sheet, rows in sheets.items():
        print(f"  {sheet}: {len(rows)}행")

    if issues:
        errors_path = Path(args.errors)
        errors_path.parent.mkdir(parents=True, exist_ok=True)
        existing: list = []
        if errors_path.exists():
            try:
                existing = json.loads(errors_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        for issue in issues:
            existing.append({
                "unvCd": args.unvcd,
                "university": args.univ,
                "stage": "T2",
                "error": issue,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            })
        errors_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return 0 if not any("0행" in i for i in issues) else 1


if __name__ == "__main__":
    raise SystemExit(main())
