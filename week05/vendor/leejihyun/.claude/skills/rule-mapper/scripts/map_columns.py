"""룰 기반 컬럼 매핑 — T3 단계

사용법:
    python map_columns.py --unvcd 0000063 \\
                          --parsed output/parsed/0000063.json \\
                          --schema input/schema_v3.yaml \\
                          --output output/mapped/0000063.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Optional

import yaml

# ─────────────────────────────────────────────
# 정규화 사전 (normalization-dictionary.md §1~§9)
# ─────────────────────────────────────────────

BANGYEONGGWA_MAP = {
    "전 과목": "전교과",
    "전과목": "전교과",
    "전체": "전교과",
    "전체 과목": "전교과",
    "국 수 영 사": "국,수,영,사",
    "국·수·영·사": "국,수,영,사",
}

NULL_MARKS = {"-", "–", "—", "", " ", "N/A", "해당없음", "미공개"}

BOOLEAN_TRUE  = {"있음", "적용", "○", "Y", "O", "TRUE", "true", "예", "해당"}
BOOLEAN_FALSE = {"없음", "미적용", "×", "N", "X", "FALSE", "false", "아니오", "미해당"}

# 전형구분 대분류 키워드 → 대분류
JEON_DAEBULYU_RULES: list[tuple[list[str], str]] = [
    (["학생부종합", "종합전형", "활동우수", "계열적합", "가천바람개비",
      "잠재역량", "미래인재", "자기추천", "서류"], "학생부위주(종합)"),
    (["학생부교과", "교과전형", "학교추천", "지역인재교과", "교과성적"], "학생부위주(교과)"),
    (["논술"], "논술위주"),
    (["실기", "실적", "특기자"], "실기/실적위주"),
    (["수능", "정시", "수능위주"], "수능위주"),
]

# 면접유형 키워드 → 유형
INTERVIEW_RULES: list[tuple[list[str], str]] = [
    (["제시문", "논리적 사고", "논리사고", "구술고사", "제시문 기반"], "제시문_논리사고"),
    (["인적성", "인·적성", "AI면접", "AI 면접"], "인적성_면접"),
    (["심층면접", "2단계 면접"], "단계별심층_2회"),
    (["실기", "실연", "작품 심사"], "실기포함"),
    (["서류진위", "서류확인", "서류기반",
      "학생부를 기초로 한 대면", "학교생활기록부를 기초로 한 대면",
      "학생부 기반", "서류 기반"], "서류기반_확인"),
    (["면접 없음", "미실시", "면접 미실시", "면접을 실시하지", "면접평가 없음"], "없음"),
]

# 캠퍼스 분리 패턴
CAMPUS_PATTERNS: list[tuple[str, str]] = [
    (r"\(글로벌\)|글로벌\s*캠퍼스", "글로벌"),
    (r"\(메디컬\)|메디컬\s*캠퍼스", "메디컬"),
    (r"\(상주\)|상주\s*캠퍼스", "상주"),
    (r"\(양산\)|양산\s*캠퍼스", "양산"),
    (r"\(밀양\)|밀양\s*캠퍼스", "밀양"),
    (r"\(아미\)|아미\s*캠퍼스", "아미"),
    (r"\(세종\)", "세종"),
    (r"\(미래\)", "미래"),
]


# ─────────────────────────────────────────────
# 정규화 함수들
# ─────────────────────────────────────────────

def clean_null(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str) and v.strip() in NULL_MARKS:
        return None
    return v


def normalize_bangyeonggwa(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = v.strip()
    if s in BANGYEONGGWA_MAP:
        return BANGYEONGGWA_MAP[s]
    # 중간점 → 쉼표, 공백 제거
    s = re.sub(r"[·•]", ",", s)
    s = re.sub(r"\s*,\s*", ",", s)
    return s


def normalize_bool(v: Any) -> Optional[bool]:
    if v is None:
        return None
    s = str(v).strip()
    if s in BOOLEAN_TRUE:
        return True
    if s in BOOLEAN_FALSE:
        return False
    return None


def normalize_number(v: Any) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if s in NULL_MARKS:
        return None
    # 천 단위 구분자, 퍼센트, 점, 명 등 제거
    s = re.sub(r"[,\s%점명]", "", s)
    # "약 25" → "25"
    s = re.sub(r"^약\s*", "", s)
    # "25명" → "25"
    s = s.rstrip("명")
    try:
        return float(s)
    except ValueError:
        return None


def normalize_integer(v: Any) -> Optional[int]:
    f = normalize_number(v)
    return int(f) if f is not None else None


def classify_jeon_daebulyu(jeon_name: str) -> str:
    for keywords, category in JEON_DAEBULYU_RULES:
        if any(kw in jeon_name for kw in keywords):
            return category
    return "기타"


def classify_interview(text: str) -> Optional[str]:
    for keywords, category in INTERVIEW_RULES:
        if any(kw in text for kw in keywords):
            return category
    return None


# 전형구분_소분류 분류 규칙 (전형명 + raw_text 기반)
JEON_SOBULYU_RULES: list[tuple[list[str], str]] = [
    (["일반학생전형", "일반전형", "일반학생 전형"], "일반전형"),
    (["지역인재 학교장추천", "학교장추천"], "학교장추천전형"),
    (["지역인재"], "지역인재전형"),
    (["농어촌", "농어촌학생"], "농어촌학생전형"),
    (["기회균형", "균형선발", "고른기회"], "고른기회전형"),
    (["사회배려자", "사회적배려"], "사회배려자전형"),
    (["저소득", "기초생활수급자", "차상위"], "기초생활수급자전형"),
    (["특성화고졸재직자", "특성화고교졸재직자"], "특성화고졸재직자전형"),
    (["특성화고교졸업자", "특성화고교 졸업자"], "특성화고교졸업자전형"),
    (["고졸재직자"], "고졸재직자전형"),
    (["특기자"], "특기자전형"),
    (["장애인", "특수교육대상자"], "장애인등대상자전형"),
    (["북한이탈", "탈북"], "북한이탈주민전형"),
    (["영농창업인재"], "영농창업인재전형"),
    (["SW특별", "SW 특별"], "SW특별전형"),
    (["사이버국방"], "사이버국방전형"),
    (["모바일과학인재"], "모바일과학인재전형"),
    (["해외고"], "해외고졸업자전형"),
    (["국제형"], "국제형전형"),
    (["활동우수형", "활동우수 형"], "활동우수형전형"),
    (["기회균형"], "고른기회전형"),
    (["의약학"], "의약학전형"),
    (["논술"], "논술전형"),
    (["교과우수자", "교과 우수자"], "교과우수자전형"),
    (["추천형"], "추천형전형"),
]


def classify_jeon_sobulyu(jeon_name: str, raw_text: str = "") -> Optional[str]:
    combined = jeon_name + " " + raw_text[:200]
    for keywords, category in JEON_SOBULYU_RULES:
        if any(kw in combined for kw in keywords):
            return category
    return None


def extract_campus(mojip_text: str) -> tuple[str, str]:
    """모집단위에서 캠퍼스 추출 → (캠퍼스, 정제된 모집단위)"""
    for pattern, campus_name in CAMPUS_PATTERNS:
        if re.search(pattern, mojip_text):
            clean = re.sub(pattern, "", mojip_text).strip()
            clean = re.sub(r"^\s*[\(\)]\s*", "", clean).strip()
            return campus_name, clean
    return "본교", mojip_text


# ─────────────────────────────────────────────
# 시트별 매핑 로직
# ─────────────────────────────────────────────

def map_susi_result_row(raw: dict) -> tuple[dict, list[dict]]:
    """susi_result 1행 매핑. 반환: (mapped_row, unmapped_list)"""
    unmapped: list[dict] = []

    campus, mojip_clean = extract_campus(str(raw.get("모집단위", "")))

    mapped: dict = {
        "대학": raw.get("대학", ""),
        "전형": raw.get("전형", ""),
        "모집단위": mojip_clean,
        "캠퍼스": campus,
        "전형구분_대분류": classify_jeon_daebulyu(str(raw.get("전형", ""))),
        "모집인원": normalize_integer(clean_null(raw.get("모집인원"))),
        "경쟁률": normalize_number(clean_null(raw.get("경쟁률"))),
        "충원합격순위": normalize_integer(clean_null(raw.get("충원합격순위"))),
        "기준": clean_null(raw.get("기준")),
        "반영교과": normalize_bangyeonggwa(clean_null(raw.get("반영교과"))),
        "raw_text": raw.get("raw_text"),
    }

    # 학생부등급 컷 매핑
    for cut in ["최고", "평균", "50컷", "70컷", "80컷", "90컷", "최저"]:
        key = f"학생부등급_{cut}"
        mapped[key] = normalize_number(clean_null(raw.get(key)))

    # 대학별환산 컷 매핑
    for cut in ["최고", "평균", "50컷", "70컷", "80컷", "100컷", "총점"]:
        key = f"대학별환산_{cut}"
        mapped[key] = normalize_number(clean_null(raw.get(key)))

    # 데이터공개수준 자동 판정
    filled = sum(
        1 for k in ["모집인원", "경쟁률", "학생부등급_70컷"]
        if mapped.get(k) is not None
    )
    mapped["데이터공개수준"] = (
        "표준양식_완전" if filled >= 3
        else "표준양식_부분" if filled >= 1
        else "미공개"
    )

    return mapped, unmapped


def map_susi_eval_row(raw: dict) -> tuple[dict, list[dict]]:
    """susi_eval 1행 매핑."""
    unmapped: list[dict] = []

    campus, mojip_clean = extract_campus(str(raw.get("모집단위", "")))

    jeon = str(raw.get("전형", ""))
    raw_text = raw.get("raw_text", "") or ""

    _daebulyu = classify_jeon_daebulyu(jeon)
    if _daebulyu == "기타" and raw_text:
        if re.search(r"학생부종합|서류평가|서류\s*100|종합\s*평가|학생부종합전형", raw_text, re.I):
            _daebulyu = "학생부위주(종합)"
        elif re.search(r"학생부교과|교과\s*성적|교과\s*우수", raw_text, re.I):
            _daebulyu = "학생부위주(교과)"
        elif "논술" in raw_text:
            _daebulyu = "논술위주"

    mapped: dict = {
        "대학": raw.get("대학", ""),
        "전형": jeon,
        "모집단위": mojip_clean,
        "캠퍼스": campus,
        "전형구분_대분류": _daebulyu,
        "전형구분_소분류": classify_jeon_sobulyu(jeon, raw_text),
        "수능최저유무": None,
        "선발방법": None,
        "raw_text": raw_text[:8000] if raw_text else None,
        "데이터공개수준": "비표준_텍스트만" if raw_text else "미공개",
    }

    # raw_text에서 규칙 기반으로 추출 가능한 항목
    if raw_text:
        # 면접유형
        iv = classify_interview(raw_text)
        if iv:
            mapped["면접유형"] = iv

        # 수능최저 유무 (없음 패턴 우선)
        no_suneung_patterns = [
            "수능최저학력기준 없음", "수능 최저 없음", "수능최저 없음",
            "최저학력기준 없음", "수능최저 미적용", "수능 최저 미적용",
            "수능 최저학력 기준 없음", "수능최저학력 기준 없음",
            "수능 최저학력기준 없음", "수능 최저학력기준 : 없음",
            "수능최저학력기준 : 없음", "수능 최저학력기준 : 미적용",
            "수능최저학력기준 : 미적용", "수능 최저학력기준 미적용",
            "수능최저 : 없음",
        ]
        yes_suneung_patterns = [
            "수능최저학력기준 있음", "수능최저 있음",
            "수능 최저학력기준 적용", "수능최저학력 기준 있음",
            "수능 최저학력기준 : 있음", "수능최저학력기준이 적용",
        ]
        if any(p in raw_text for p in no_suneung_patterns):
            mapped["수능최저유무"] = "없음"
        elif any(p in raw_text for p in yes_suneung_patterns):
            mapped["수능최저유무"] = "있음_전체"
        elif re.search(r"수능\s*최저", raw_text):
            mapped["수능최저유무"] = "있음_전체"

        # 수능최저_요건: 요건 문자열 추출 (없음인 경우 제외)
        if mapped.get("수능최저유무") and mapped["수능최저유무"] != "없음":
            m_req = re.search(
                r"수능\s*최저\s*(?:학력기준)?\s*[:：]\s*([^\n]{5,200})", raw_text
            )
            if m_req:
                req = m_req.group(1).strip()
                if not re.match(r"(?:없음|미적용|안 함)", req, re.I):
                    mapped["수능최저_요건"] = req[:200]

        # 수능최저_탐구반영
        m_tang = re.search(r"탐구\s*(?:영역)?\s*(?:은|를|:)?\s*(\d)\s*개\s*(?:과목|영역)", raw_text)
        if m_tang:
            n = int(m_tang.group(1))
            mapped["수능최저_탐구반영"] = f"{n}개과목"
        else:
            m_tang2 = re.search(r"탐구\s*(\d)\s*과목\s*평균", raw_text)
            if m_tang2:
                mapped["수능최저_탐구반영"] = f"{m_tang2.group(1)}개평균"

        # 선발방법
        _has_1dangyae = bool(re.search(r"(?<!\d)1\s*단계", raw_text))
        if "일괄합산" in raw_text or "일괄 합산" in raw_text or "일괄선발" in raw_text:
            mapped["선발방법"] = "일괄합산"
        elif _has_1dangyae or "단계별" in raw_text or re.search(r"\[1\s*단계\s*\]|\(1\s*단계\)", raw_text):
            mapped["선발방법"] = "단계별"
        else:
            # 서류 단독 100% → 일괄합산
            m_sal = re.search(r"서류\s*(?:\([^)]*\)\s*)?(?:평가\s*)?(\d+)\s*%", raw_text)
            if m_sal and int(m_sal.group(1)) >= 90:
                mapped["선발방법"] = "일괄합산"

        # 1단계 배수 (다양한 패턴)
        m = re.search(r"(?:1단계|1\s*단계)[^\n]*?(\d+[~\-]\d+|\d+)\s*배수", raw_text)
        if m:
            mapped["1단계_배수"] = m.group(1)
        else:
            m = re.search(r"(\d+[~\-]?\d*)\s*배수", raw_text)
            if m:
                mapped["1단계_배수"] = m.group(1)

        # 1단계_요소비율: "[1 단계 ] 서류 100%" 또는 "서류(학생부)평가 100%(3배수)"
        m1 = re.search(
            r"(?:\[1\s*단계\s*\]|(?<!\d)1단계\s*[:]\s*)[^/\n]*?"
            r"(서류|학생부교과|교과|논술|실기)\s*(?:\([^)]*\))?\s*(?:평가\s*)?(\d+)\s*%",
            raw_text, re.I
        )
        if m1:
            elem = re.sub(r"\s+", "", m1.group(1))
            pct = m1.group(2)
            mapped["1단계_요소비율"] = f"{elem}{pct}"

        # 2단계_요소비율: "[2 단계 ] 1 단계 성적 80% + 면접 20%"
        m2 = re.search(
            r"(?:\[2\s*단계\s*\]|(?<!\d)2단계\s*[:]\s*)[^/\n]*?"
            r"((?:1\s*단계|서류|면접|교과|학생부|논술)(?:\s*성적)?)\s*(\d+)\s*%"
            r"[^\n]*?\+\s*((?:면접|서류|교과|논술|1\s*단계))\s*(\d+)\s*%",
            raw_text, re.I
        )
        if m2:
            e1 = re.sub(r"\s+", "", m2.group(1))
            p1 = m2.group(2)
            e2 = re.sub(r"\s+", "", m2.group(3))
            p2 = m2.group(4)
            mapped["2단계_요소비율"] = f"{e1}{p1}+{e2}{p2}"

        # 평가표기방식: "%" 있고 합계 100에 가까운 숫자들 → 비율백분율
        pct_nums = re.findall(r"(\d+)\s*%", raw_text)
        pct_nums_int = [int(n) for n in pct_nums if 0 < int(n) <= 100]
        if pct_nums_int and sum(pct_nums_int) >= 90:
            mapped["평가표기방식"] = "비율백분율"
        elif re.search(r"A\+|B0|B-|등급제", raw_text):
            mapped["평가표기방식"] = "등급제_7단계" if not re.search(r"\bF\b", raw_text) else "등급제_8단계"

        # 평가요소 이름/비중 추출
        # 패턴 1: "학업역량 40%, 진로역량 40%, 공동체역량 20%"
        eval_elements: list[tuple[str, Optional[int]]] = []
        ptn1 = re.findall(r"(학업역량|진로역량|공동체역량|학업태도|학업외소양|자기계발역량|인성리더십|종합평가[Ⅰ-Ⅳ]|전공역량)\s*[(\s]*(\d+)\s*[)%]?", raw_text)
        for name, pct in ptn1:
            name = name.strip()
            p = int(pct) if pct else None
            if p is None or 1 <= p <= 100:
                eval_elements.append((name, p))

        if not eval_elements:
            # 패턴 2: "학업역량 , 진로역량 , 공동체역량" (비중 없음)
            ptn2 = re.findall(r"(학업역량|진로역량|공동체역량|학업태도|학업외소양|자기계발역량|인성리더십)", raw_text)
            seen: list[str] = []
            for name in ptn2:
                if name not in seen:
                    seen.append(name)
            eval_elements = [(name, None) for name in seen[:3]]

        seen_names: set[str] = set()
        unique_elements: list[tuple[str, Optional[int]]] = []
        for name, pct in eval_elements:
            if name not in seen_names:
                seen_names.add(name)
                unique_elements.append((name, pct))

        for slot, (name, pct) in enumerate(unique_elements[:3], 1):
            mapped[f"평가요소{slot}_이름"] = name
            if pct is not None:
                mapped[f"평가요소{slot}_비중"] = pct

        # 평가요소_세부항목수
        if unique_elements:
            mapped["평가요소_세부항목수"] = len(unique_elements)

        # 학업역량_정량반영여부: 학업역량이 정량(% 수치)으로 표기된 경우 True
        if "학업역량" in raw_text:
            m_lha = re.search(r"학업역량\s*[(\s]*(\d+)\s*[)%]", raw_text)
            mapped["학업역량_정량반영여부"] = m_lha is not None

        # 면접_평가위원수: "입학사정관 N인" 또는 "평가위원 N인"
        m_eval_n = re.search(r"(?:입학사정관|평가위원)\s*(\d+)\s*인", raw_text)
        if m_eval_n:
            mapped["면접_평가위원수"] = int(m_eval_n.group(1))

        # 면접_시간: "10분", "20분 내외" 등
        m_time = re.search(r"(?:면접\s*시간|1인당)[^\d]*(\d+)\s*분", raw_text)
        if m_time:
            mapped["면접_시간"] = int(m_time.group(1))

        # 면접_평가요소비율: 2단계에서 면접이 차지하는 비율
        m_int_pct = re.search(
            r"(?:2\s*단계|2단계)[^.]*면접\s*(?:및\s*구술고사\s*)?(\d+)\s*%",
            raw_text, re.I
        )
        if not m_int_pct:
            m_int_pct = re.search(r"면접\s*(\d+)\s*%", raw_text)
        if m_int_pct:
            mapped["면접_평가요소비율"] = f"{m_int_pct.group(1)}%"

        # 교과_등급환산방식
        if re.search(r"석차\s*등급", raw_text):
            mapped["교과_등급환산방식"] = "석차등급"
        elif re.search(r"변환\s*등급|등급\s*환산", raw_text):
            mapped["교과_등급환산방식"] = "변환등급"

        # 교과_반영영역_인문: 인문 계열 교과 반영 영역
        m_inhum = re.search(
            r"인문\s*(?:계열)?\s*[:]\s*(국어[^.]{0,100}(?:사회|한국사|생활))",
            raw_text, re.I
        )
        if m_inhum:
            mapped["교과_반영영역_인문"] = m_inhum.group(1)[:100]

        # 교과_반영영역_자연: 자연 계열 교과 반영 영역
        m_sci = re.search(
            r"자연\s*(?:계열)?\s*[:]\s*(국어[^.]{0,100}(?:과학|수학))",
            raw_text, re.I
        )
        if m_sci:
            mapped["교과_반영영역_자연"] = m_sci.group(1)[:100]

        # 교과_학년별반영비율: "1학년 20% 2학년 40% 3학년 40%" 패턴
        m_grade = re.search(
            r"(?:1\s*학년[^\d]*(\d+)\s*%[^\d]*2\s*학년[^\d]*(\d+)\s*%[^\d]*3\s*학년[^\d]*(\d+)\s*%)",
            raw_text
        )
        if m_grade:
            mapped["교과_학년별반영비율"] = f"1학년{m_grade.group(1)}%+2학년{m_grade.group(2)}%+3학년{m_grade.group(3)}%"

        # 면접 문항 사전 공개 (남서울대 등)
        if "사전공개" in raw_text or "문항 사전" in raw_text:
            mapped["면접_문항사전공개여부"] = True

        # 진로선택과목 반영 여부
        if "진로선택" in raw_text:
            mapped["진로선택과목_반영여부"] = True

        # 남은 텍스트는 unmapped에
        unmapped.append({
            "대학": raw.get("대학", ""),
            "전형": jeon,
            "모집단위": mojip_clean,
            "raw_text": raw_text[:8000],
            "field": "평가기준_전체",
        })

    return mapped, unmapped


def map_jeongsi_result_row(raw: dict) -> tuple[dict, list[dict]]:
    """jeongsi_result 1행 매핑."""
    unmapped: list[dict] = []

    campus, mojip_clean = extract_campus(str(raw.get("모집단위", "")))

    mapped: dict = {
        "대학": raw.get("대학", ""),
        "전형": raw.get("전형", ""),
        "모집단위": mojip_clean,
        "캠퍼스": campus,
        "군": raw.get("군"),
        "모집인원_최초": normalize_integer(clean_null(raw.get("모집인원"))),
        "경쟁률": normalize_number(clean_null(raw.get("경쟁률"))),
        "충원합격순위": normalize_integer(clean_null(raw.get("충원합격순위"))),
        "raw_text": raw.get("raw_text"),
    }

    # 백분위 컷
    for area in ["총점", "국어", "수학", "영어", "탐구1", "탐구2", "한국사"]:
        key = f"백분위_{area}_70컷"
        mapped[key] = normalize_number(clean_null(raw.get(key)))

    # 환산점수
    for cut in ["총점", "70컷", "50컷", "90컷"]:
        key = f"환산점수_{cut}"
        mapped[key] = normalize_number(clean_null(raw.get(key)))

    mapped["데이터공개수준"] = (
        "표준양식_완전" if mapped.get("경쟁률") is not None
        else "미공개"
    )

    return mapped, unmapped


def map_jeongsi_eval_row(raw: dict) -> tuple[dict, list[dict]]:
    """jeongsi_eval 1행 매핑."""
    unmapped: list[dict] = []

    campus, mojip_clean = extract_campus(str(raw.get("모집단위", "")))
    jeon = str(raw.get("전형", ""))
    raw_text = raw.get("raw_text", "") or ""

    mapped: dict = {
        "대학": raw.get("대학", ""),
        "전형": jeon,
        "모집단위": mojip_clean,
        "캠퍼스": campus,
        "군": raw.get("군"),
        "전형구분_대분류": "수능위주",
        "전형구분_소분류": classify_jeon_sobulyu(jeon, raw_text),
        "선발방법": None,
        "raw_text": raw_text[:8000] if raw_text else None,
        "데이터공개수준": "비표준_텍스트만" if raw_text else "미공개",
    }

    if raw_text:
        # 수능 활용지표
        if "변환표준점수" in raw_text:
            mapped["수능_활용지표"] = "변환표준점수"
        elif "백분위" in raw_text and "표준점수" in raw_text:
            mapped["수능_활용지표"] = "백분위_변환표준점수"
        elif "백분위" in raw_text:
            mapped["수능_활용지표"] = "백분위"
        elif "표준점수" in raw_text:
            mapped["수능_활용지표"] = "표준점수"

        # 수능 영역별 비율 추출
        for subj, label in [("국어", "수능_국어_비율"), ("수학", "수능_수학_비율"),
                              ("영어", "수능_영어_비율"), ("탐구", "수능_탐구_비율")]:
            m = re.search(rf"{subj}[:\s]*(\d+)\s*%?", raw_text)
            if m:
                mapped[label] = normalize_number(m.group(1))

        # 가산점
        for item, label in [("미적분", "가산점_미적분_비율"), ("기하", "가산점_기하_비율"),
                              ("과학탐구", "가산점_과학탐구_비율")]:
            m = re.search(rf"{item}[:\s가산점]*(\d+)\s*%?", raw_text)
            if m:
                mapped[label] = normalize_number(m.group(1))

        unmapped.append({
            "대학": raw.get("대학", ""),
            "전형": jeon,
            "모집단위": mojip_clean,
            "raw_text": raw_text[:8000],
            "field": "정시평가기준_전체",
        })

    return mapped, unmapped


# ─────────────────────────────────────────────
# 매핑률 계산
# ─────────────────────────────────────────────

def calc_fill_rate(rows: list[dict], exclude_cols: set[str]) -> float:
    if not rows:
        return 0.0
    total_cells = 0
    filled_cells = 0
    for row in rows:
        for k, v in row.items():
            if k in exclude_cols or k == "raw_text":
                continue
            total_cells += 1
            if v is not None:
                filled_cells += 1
    return filled_cells / total_cells if total_cells else 0.0


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

MAPPERS = {
    "susi_result":    map_susi_result_row,
    "susi_eval":      map_susi_eval_row,
    "jeongsi_result": map_jeongsi_result_row,
    "jeongsi_eval":   map_jeongsi_eval_row,
}


def main():
    ap = argparse.ArgumentParser(description="룰 기반 컬럼 매핑")
    ap.add_argument("--unvcd", required=True)
    ap.add_argument("--parsed", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    parsed_path = Path(args.parsed)
    if not parsed_path.exists():
        print(f"[오류] parsed 파일 없음: {args.parsed}")
        return 1

    print(f"[T3 룰매핑] {args.unvcd}: 시작")

    parsed = json.loads(parsed_path.read_text(encoding="utf-8"))

    # 스키마 로드 (타입 검증용)
    schema_path = Path(args.schema)
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8")) if schema_path.exists() else {}

    result: dict[str, dict] = {}
    all_fill_rates: list[float] = []

    for sheet_name, rows in parsed.items():
        mapper = MAPPERS.get(sheet_name)
        if mapper is None:
            result[sheet_name] = {"mapped": rows, "unmapped": []}
            continue

        mapped_list: list[dict] = []
        unmapped_list: list[dict] = []

        for raw_row in rows:
            m_row, u_items = mapper(raw_row)
            mapped_list.append(m_row)
            unmapped_list.extend(u_items)

        fill_rate = calc_fill_rate(mapped_list, {"대학", "전형", "모집단위", "캠퍼스"})
        all_fill_rates.append(fill_rate)

        result[sheet_name] = {
            "mapped": mapped_list,
            "unmapped": unmapped_list,
        }

        print(f"  {sheet_name}: {len(mapped_list)}행 매핑, {len(unmapped_list)}건 unmapped, 채움률={fill_rate:.0%}")

    overall_fill = sum(all_fill_rates) / len(all_fill_rates) if all_fill_rates else 0.0
    print(f"[T3 룰매핑] {args.unvcd}: 완료 — 전체 평균 채움률 {overall_fill:.0%}")

    if overall_fill < 0.60:
        print(f"  [경고] 매핑률 {overall_fill:.0%} < 60% 임계치")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
