"""T4b: normalizer-eval — susi_eval / jeongsi_eval seed 컬럼 정규화.

mapped/{unvCd}.json 을 읽어 enhanced regex extraction 후
normalized/{unvCd}.json 의 eval 시트 부분을 작성한다.

DoD 목표: susi_eval seed 채움률 ≥ 50%
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent.parent.parent.parent  # 프로젝트 루트

SCHEMA_SEED_COLS = [
    "대학", "전형", "모집단위", "캠퍼스", "모집인원",
    "전형구분_대분류", "전형구분_소분류", "평가표기방식", "면접유형", "수능최저유무",
    "선발방법", "1단계_배수", "1단계_요소비율", "2단계_요소비율",
    "평가요소1_이름", "평가요소1_비중", "평가요소2_이름", "평가요소2_비중",
    "평가요소3_이름", "평가요소3_비중", "학업역량_정량반영여부", "평가요소_세부항목수",
    "수능최저_요건", "수능최저_탐구반영",
    "면접_평가위원수", "면접_시간", "면접_평가요소비율", "면접_문항사전공개여부",
    "교과_학년별반영비율", "교과_반영영역_인문", "교과_반영영역_자연", "교과_반영영역_예체능",
    "교과_등급환산방식", "진로선택과목_반영여부",
    "데이터공개수준",
]

EVAL_NAMES = ["학업역량", "진로역량", "공동체역량", "학업태도", "학업외소양",
              "자기계발역량", "인성리더십", "탐구역량", "사회역량",
              "종합평가Ⅰ", "종합평가Ⅱ", "종합평가I", "종합평가II"]

# 수능최저 없음 패턴 (compact spaced 형태도 포함)
NO_SUNEUNG = re.compile(
    r"수능\s*최저\s*(?:학력\s*기준|학력기준|기준)?\s*(?:는|이)?\s*(?:없음|미적용|없음|안\s*함|적용\s*안\s*함|해당\s*없음)"
    r"|수능\s*최저\s*(?:학력\s*)?기준\s*[:：]\s*(?:없음|미적용)"
    r"|수능\s*(?:최저|최저학력기준)\s*(?:미적용|없음|안\s*함)"
    r"|수능최저학력기준\s*없음|수능최저\s*없음|최저학력기준\s*없음",
    re.I
)
YES_SUNEUNG_EXPLICIT = re.compile(
    r"수능\s*최저\s*(?:학력\s*)?기준\s*[:：]\s*(?:있음|적용|해당)"
    r"|수능\s*최저\s*학력\s*기준\s*(?:있음|이\s*있음|적용|이\s*적용)"
    r"|수능최저학력기준이\s*적용|수능최저\s*있음",
    re.I
)
# 수능최저 요건 패턴
SUNEUNG_REQ_PATTERN = re.compile(
    r"(?:국어|수학|영어|탐구|한국사|과학|사회)[^\n]{0,200}"
    r"(?:\d+\s*개\s*(?:영역|과목)?|합\s*\d+\s*등급|등급\s*합\s*\d+|\d+\s*등급\s*이내)",
    re.I
)

# 교과 반영 영역 패턴 (spaced text 포함)
INHUM_AREA_PATTERN = re.compile(
    r"(?:인문\s*(?:계열)?\s*[:：]\s*|인문계\s*[:：]\s*)((?:국어|수학|영어|사회|한국사|생활|과학)(?:\s*[,，、]\s*(?:국어|수학|영어|사회|한국사|생활|과학|도덕|역사))*)",
    re.I
)
NAT_AREA_PATTERN = re.compile(
    r"(?:자연\s*(?:계열)?\s*[:：]\s*|자연계\s*[:：]\s*)((?:국어|수학|영어|사회|과학|물리|화학|생물|지구)(?:\s*[,，、]\s*(?:국어|수학|영어|사회|과학|물리|화학|생물|지구|한국사))*)",
    re.I
)
ARTS_AREA_PATTERN = re.compile(
    r"(?:예\s*[·・]\s*체능\s*(?:계열)?\s*[:：]\s*|예체능\s*[:：]\s*|예능계\s*[:：]\s*)((?:국어|수학|영어|예체|음악|미술|체육)(?:\s*[,，、]\s*(?:국어|수학|영어|예체|음악|미술|체육))*)",
    re.I
)

# 1단계 요소비율 패턴 (다양한 형식)
STAGE1_RATIO = re.compile(
    r"(?:\[?\s*1\s*단계\s*\]?\s*[:：]?\s*|(?<![가-힣])1\s*단계\s+)"
    r"(?:[^\n/]{0,30}?)?"
    r"(서류|학생부\s*(?:교과)?|교과|논술|실기)\s*(?:\([^)]{0,20}\))?\s*(?:평가\s*)?(\d+)\s*%",
    re.I
)
STAGE2_RATIO = re.compile(
    r"(?:\[?\s*2\s*단계\s*\]?\s*[:：]?\s*|(?<![가-힣])2\s*단계\s+)"
    r"(?:[^\n/]{0,50}?)?"
    r"(1\s*단계\s*(?:성적)?|서류|교과|학생부|면접|논술)\s*(\d+)\s*%"
    r"[^\n]{0,30}?\+\s*(면접|서류|교과|학생부|논술|1\s*단계\s*(?:성적)?)\s*(\d+)\s*%",
    re.I
)

# 가천대 스타일 tabular: 방법 배수 학생부% 면접% 논술%
GACHEON_TABLE = re.compile(
    r"(?:(일괄합산|1\s*단계|2\s*단계))\s+(\d+)\s+(\d+|-)\s+(\d+|-)\s+(\d+|-)"
)

# 모집인원: "N 명" 또는 "N명" 단독 패턴 (앞에 명칭이 있는 경우 제외)
MOJIP_INNO = re.compile(r"(?<!\w)(\d{1,4})\s*명(?!\s*(?:이상|이하|이내|초과|내외|중|한정|수|당|이나))")


def _norm_space(text: str) -> str:
    """연속 공백을 단일 공백으로."""
    return re.sub(r"\s+", " ", text).strip()


_EVAL_NAME_PAT = re.compile(
    r"(학업역량|진로역량|공동체역량|학업태도|학업외소양|자기계발역량"
    r"|인성리더십|탐구역량|사회역량|종합평가[IⅠⅡⅢⅣ]+)"
)


def extract_eval_elements(raw_text: str) -> list[tuple[str, Optional[int]]]:
    """평가요소 이름 + 비중 추출 (다양한 패턴 처리)."""
    # 텍스트에서 고유 평가요소 이름 목록 (순서 유지)
    all_names_raw = _EVAL_NAME_PAT.findall(raw_text)
    unique_names = list(dict.fromkeys(all_names_raw))

    if not unique_names:
        return []

    # 패턴 1: "학업역량 40%, 진로역량 40%, 공동체역량 20%" — 이름 바로 뒤에 숫자
    p1 = re.findall(
        r"(학업역량|진로역량|공동체역량|학업태도|학업외소양|자기계발역량"
        r"|인성리더십|탐구역량|사회역량|종합평가[IⅠⅡⅢⅣ]+)"
        r"\s*[(\s]*(\d+)\s*[)%]?",
        raw_text
    )
    # p1이 고유 이름 수만큼 모두 잡혔을 때만 사용 (부분 매칭 방지)
    if p1:
        p1_dedup = _dedup([(n.strip(), int(pct)) for n, pct in p1 if 1 <= int(pct) <= 100])
        if len(p1_dedup) >= len(unique_names):
            return p1_dedup[:3]

    # 패턴 2: tabular "학업역량 탐구역량 사회역량 40 40 20"
    # 마지막 이름 등장 위치 이후의 숫자 시퀀스를 비중으로 사용
    if len(unique_names) >= 2:
        # 마지막으로 등장한 이름 집합 이후 위치 찾기
        last_occurrence = 0
        for name in unique_names:
            idx = raw_text.rfind(name)
            if idx >= 0:
                last_occurrence = max(last_occurrence, idx + len(name))
        suffix = raw_text[last_occurrence:last_occurrence + 60]
        nums = [int(n) for n in re.findall(r"(\d+)", suffix) if 1 <= int(n) <= 100]
        if len(nums) >= len(unique_names):
            pairs = [(unique_names[i], nums[i]) for i in range(min(3, len(unique_names)))]
            if sum(p for _, p in pairs) >= 90:  # 합계 100 근처여야 비중
                return pairs

    # 패턴 3: 이름만 (비중 없음)
    return [(n, None) for n in unique_names[:3]]


def _dedup(items: list[tuple[str, Optional[int]]]) -> list[tuple[str, Optional[int]]]:
    seen: set[str] = set()
    out = []
    for name, pct in items:
        if name not in seen:
            seen.add(name)
            out.append((name, pct))
    return out


def extract_mojip_inno(raw_text: str) -> Optional[int]:
    """모집인원 숫자 추출 — 텍스트 끝부분에 가장 신뢰성 높은 N명 패턴."""
    # "N명"에서 N 추출 (단독으로 나타나는 경우, 불필요한 맥락 제거)
    candidates = []
    for m in MOJIP_INNO.finditer(raw_text):
        n = int(m.group(1))
        # 너무 크거나 작은 수 필터링 (입시 모집인원 1~5000 범위)
        if 1 <= n <= 5000:
            # 바로 뒤에 학과명/문자열이 오면 제외
            candidates.append(n)
    # 첫 번째 유효한 값 반환 (보통 설명 첫 부분에 등장)
    if candidates:
        # 가천대 패턴: "... 455 명" 처럼 설명 후반에 등장하는 단독 숫자
        return candidates[0]
    return None


def extract_suneung_req(raw_text: str) -> Optional[str]:
    """수능최저 요건 문자열 추출."""
    # 패턴 1: "수능최저 : 요건..."
    m = re.search(
        r"수능\s*최저\s*(?:학력\s*기준)?\s*[:：]\s*([^\n]{5,300})",
        raw_text
    )
    if m:
        req = m.group(1).strip()
        if not re.match(r"(?:없음|미적용|안\s*함)", req[:10], re.I):
            return req[:300]

    # 패턴 2: 국수영탐 요건 패턴 직접 탐색
    m2 = SUNEUNG_REQ_PATTERN.search(raw_text)
    if m2:
        req = m2.group(0).strip()
        if len(req) > 10:
            return req[:300]

    return None


def extract_stage_ratios(raw_text: str, jeon: str = "") -> dict:
    """1단계/2단계 요소비율 추출."""
    result: dict[str, str] = {}

    # 가천대 스타일 table: "1 단계 N% 서류 ... / 2 단계 N% 면접 ..."
    # raw_text 내 "일괄합산 1 100 - -" 또는 "1 단계 7 100 - -" 패턴
    gacheon_matches = GACHEON_TABLE.findall(raw_text)
    if gacheon_matches:
        # 열 순서: 방법, 배수, 학생부%, 면접%, 논술%
        for method, bae, haklb, inter, nul in gacheon_matches:
            method = _norm_space(method)
            if "1" in method and "단계" in method:
                elem = []
                if haklb and haklb != "-":
                    elem.append(f"서류{haklb}")
                if inter and inter != "-":
                    elem.append(f"면접{inter}")
                if nul and nul != "-":
                    elem.append(f"논술{nul}")
                if elem:
                    result["1단계_요소비율"] = "+".join(elem)
                if bae and bae != "-":
                    result.setdefault("1단계_배수", bae)
            elif "2" in method and "단계" in method:
                elem = []
                if haklb and haklb != "-":
                    elem.append(f"1단계성적{haklb}")
                if inter and inter != "-":
                    elem.append(f"면접{inter}")
                if nul and nul != "-":
                    elem.append(f"논술{nul}")
                if elem:
                    result["2단계_요소비율"] = "+".join(elem)
            elif "일괄" in method:
                elem = []
                if haklb and haklb != "-":
                    elem.append(f"학생부{haklb}")
                if inter and inter != "-":
                    elem.append(f"면접{inter}")
                if nul and nul != "-":
                    elem.append(f"논술{nul}")
                if elem:
                    result["1단계_요소비율"] = "+".join(elem)

    # Fallback: 명시적 bracket 패턴 "[1단계] 서류 100%"
    if "1단계_요소비율" not in result:
        m1 = STAGE1_RATIO.search(raw_text)
        if m1:
            elem = re.sub(r"\s+", "", m1.group(1))
            pct = m1.group(2)
            result["1단계_요소비율"] = f"{elem}{pct}"

    if "2단계_요소비율" not in result:
        m2 = STAGE2_RATIO.search(raw_text)
        if m2:
            e1 = re.sub(r"\s+", "", m2.group(1))
            p1 = m2.group(2)
            e2 = re.sub(r"\s+", "", m2.group(3))
            p2 = m2.group(4)
            result["2단계_요소비율"] = f"{e1}{p1}+{e2}{p2}"

    return result


def extract_interview_type(raw_text: str) -> Optional[str]:
    """면접유형 분류."""
    RULES = [
        (["제시문", "논리적 사고", "논리사고", "구술고사", "제시문 기반"], "제시문_논리사고"),
        (["인적성", "인·적성", "AI면접", "AI 면접"], "인적성_면접"),
        (["심층면접", "2단계 면접", "단계별심층"], "단계별심층_2회"),
        (["실기", "실연", "작품 심사"], "실기포함"),
        (["서류진위", "서류확인", "서류기반", "서류 확인",
          "학생부를 기초로 한 대면", "학교생활기록부를 기초로 한 대면",
          "학생부 기반", "서류 기반", "학생부 기반 면접", "서류를 기반"],
         "서류기반_확인"),
        (["면접 없음", "미실시", "면접 미실시", "면접을 실시하지", "면접평가 없음"],
         "없음"),
    ]
    for keywords, label in RULES:
        for kw in keywords:
            if re.search(kw, raw_text, re.I):
                return label
    # 면접이 언급되면 서류기반 디폴트
    if re.search(r"면접\s*(?:평가|시간|방법|진행)", raw_text):
        return "서류기반_확인"
    return None


def normalize_eval_row(row: dict) -> dict:
    """매핑된 eval 행에 추가 정규화 적용, 새 행 반환."""
    out = dict(row)  # 기존 값 유지
    raw_text = out.get("raw_text", "") or ""

    if not raw_text:
        return out

    # ── 모집인원 ──────────────────────────────────────────────────
    if not out.get("모집인원"):
        n = extract_mojip_inno(raw_text)
        if n:
            out["모집인원"] = n

    # ── 수능최저유무 (개선) ───────────────────────────────────────
    if not out.get("수능최저유무"):
        if NO_SUNEUNG.search(raw_text):
            out["수능최저유무"] = "없음"
        elif YES_SUNEUNG_EXPLICIT.search(raw_text):
            out["수능최저유무"] = "있음_전체"
        elif re.search(r"수능\s*최저", raw_text):
            # 미적용/없음이 아닌데 수능최저 언급
            if "미적용" in raw_text or "없음" in raw_text:
                out["수능최저유무"] = "없음"
            elif "모집단위" in raw_text and "상이" in raw_text:
                out["수능최저유무"] = "있음_모집단위별"
            elif re.search(r"수능\s*최저\s*(?:학력\s*기준)?\s*[:：]\s*적용", raw_text):
                out["수능최저유무"] = "있음_전체"
            else:
                out["수능최저유무"] = "있음_전체"

    # ── 수능최저_요건 ──────────────────────────────────────────────
    if not out.get("수능최저_요건") and out.get("수능최저유무") and out["수능최저유무"] != "없음":
        req = extract_suneung_req(raw_text)
        if req:
            out["수능최저_요건"] = req

    # ── 수능최저_탐구반영 ──────────────────────────────────────────
    if not out.get("수능최저_탐구반영"):
        m_tang = re.search(r"탐구\s*(?:영역)?\s*(?:은|를|:)?\s*(\d)\s*개\s*(?:과목|영역)", raw_text)
        if m_tang:
            out["수능최저_탐구반영"] = f"{m_tang.group(1)}개과목"
        else:
            m_t2 = re.search(r"탐구\s*(\d)\s*과목\s*(?:평균|합)", raw_text)
            if m_t2:
                mode = "평균" if "평균" in m_t2.group(0) else "합"
                out["수능최저_탐구반영"] = f"{m_t2.group(1)}개{mode}"

    # ── 선발방법 (개선) ─────────────────────────────────────────────
    if not out.get("선발방법"):
        has_1dangyae = bool(re.search(r"(?<!\d)1\s*단계", raw_text))
        if re.search(r"일괄\s*합산|일괄\s*선발", raw_text):
            out["선발방법"] = "일괄합산"
        elif has_1dangyae or "단계별" in raw_text:
            out["선발방법"] = "단계별"
        elif re.search(r"서류\s*(?:\([^)]*\))?\s*(?:평가\s*)?100\s*%", raw_text):
            out["선발방법"] = "일괄합산"
        elif re.search(r"(?:학생부\s*교과|교과\s*성적)\s*100\s*%", raw_text):
            out["선발방법"] = "일괄합산"
        elif re.search(r"논술\s*100\s*%|논술\s*성적\s*100\s*%", raw_text):
            out["선발방법"] = "일괄합산"

    # ── 1단계_배수 ──────────────────────────────────────────────────
    if not out.get("1단계_배수"):
        m = re.search(r"(?:1단계|1\s*단계)[^\n]*?(\d+[~\-]\d+|\d+)\s*배수", raw_text)
        if m:
            out["1단계_배수"] = m.group(1)
        else:
            m = re.search(r"(\d+[~\-]?\d*)\s*배수", raw_text)
            if m:
                out["1단계_배수"] = m.group(1)

    # ── 1단계/2단계 요소비율 ─────────────────────────────────────────
    stage_result = extract_stage_ratios(raw_text, jeon=out.get("전형", ""))
    for k, v in stage_result.items():
        if not out.get(k):
            out[k] = v

    # ── 평가표기방식 (개선) ──────────────────────────────────────────
    if not out.get("평가표기방식"):
        pct_nums = [int(n) for n in re.findall(r"(\d+)\s*%", raw_text) if 0 < int(n) <= 100]
        if pct_nums and sum(pct_nums) >= 90:
            out["평가표기방식"] = "비율백분율"
        elif re.search(r"A\+|A0|B0|B-|등급제\s*[78]단계", raw_text):
            if re.search(r"\bF\b", raw_text):
                out["평가표기방식"] = "등급제_8단계"
            else:
                out["평가표기방식"] = "등급제_7단계"
        elif re.search(r"정성\s*(?:종합|평가|적)?\s*(?:평가|방식)?|정성적\s*종합", raw_text):
            out["평가표기방식"] = "정성종합"
        elif pct_nums:
            out["평가표기방식"] = "비율백분율"

    # ── 평가요소 이름/비중 ────────────────────────────────────────────
    elements = extract_eval_elements(raw_text)
    if elements:
        for slot, (name, pct) in enumerate(elements[:3], 1):
            if not out.get(f"평가요소{slot}_이름"):
                out[f"평가요소{slot}_이름"] = name
            if pct is not None and not out.get(f"평가요소{slot}_비중"):
                out[f"평가요소{slot}_비중"] = pct
        if not out.get("평가요소_세부항목수"):
            out["평가요소_세부항목수"] = len(elements)

    # ── 학업역량_정량반영여부 ────────────────────────────────────────
    if "학업역량" in raw_text and out.get("학업역량_정량반영여부") is None:
        m_lha = re.search(r"학업역량\s*[(\s]*(\d+)\s*[)%]", raw_text)
        out["학업역량_정량반영여부"] = m_lha is not None

    # ── 면접유형 ─────────────────────────────────────────────────────
    if not out.get("면접유형"):
        iv = extract_interview_type(raw_text)
        if iv:
            out["면접유형"] = iv

    # ── 면접_평가위원수 ─────────────────────────────────────────────
    if not out.get("면접_평가위원수"):
        m = re.search(r"(?:입학사정관|평가위원)\s*(\d+)\s*인", raw_text)
        if m:
            out["면접_평가위원수"] = int(m.group(1))

    # ── 면접_시간 ───────────────────────────────────────────────────
    if not out.get("면접_시간"):
        m = re.search(r"(?:면접\s*시간|1인당)[^\d]*(\d+)\s*분", raw_text)
        if m:
            out["면접_시간"] = int(m.group(1))

    # ── 면접_평가요소비율 ────────────────────────────────────────────
    if not out.get("면접_평가요소비율"):
        m = re.search(
            r"(?:2\s*단계|2단계)[^.]*면접\s*(?:및\s*구술고사\s*)?(\d+)\s*%",
            raw_text, re.I
        )
        if not m:
            m = re.search(r"면접\s*(\d+)\s*%", raw_text)
        if m:
            out["면접_평가요소비율"] = f"{m.group(1)}%"

    # ── 면접_문항사전공개여부 ─────────────────────────────────────────
    if not out.get("면접_문항사전공개여부"):
        if re.search(r"사전\s*공개|문항\s*사전", raw_text):
            out["면접_문항사전공개여부"] = True

    # ── 교과_등급환산방식 ────────────────────────────────────────────
    if not out.get("교과_등급환산방식"):
        if re.search(r"석차\s*등급", raw_text):
            out["교과_등급환산방식"] = "석차등급"
        elif re.search(r"변환\s*등급|등급\s*환산|변환등급", raw_text):
            out["교과_등급환산방식"] = "변환등급"
        elif re.search(r"정성\s*평가|정성적|입학사정관\s*종합", raw_text):
            out["교과_등급환산방식"] = "정성평가"

    # ── 교과_반영영역 ─────────────────────────────────────────────────
    if not out.get("교과_반영영역_인문"):
        m = INHUM_AREA_PATTERN.search(raw_text)
        if m:
            out["교과_반영영역_인문"] = _norm_space(m.group(1))[:100]

    if not out.get("교과_반영영역_자연"):
        m = NAT_AREA_PATTERN.search(raw_text)
        if m:
            out["교과_반영영역_자연"] = _norm_space(m.group(1))[:100]

    if not out.get("교과_반영영역_예체능"):
        m = ARTS_AREA_PATTERN.search(raw_text)
        if m:
            out["교과_반영영역_예체능"] = _norm_space(m.group(1))[:100]

    # ── 교과_학년별반영비율 ─────────────────────────────────────────
    if not out.get("교과_학년별반영비율"):
        # 패턴: "1 학년 ... 2 학년 ... 3 학년 ..."
        m = re.search(
            r"1\s*학년[^\d]*(\d+)\s*%[^\d]*2\s*학년[^\d]*(\d+)\s*%[^\d]*3\s*학년[^\d]*(\d+)\s*%",
            raw_text
        )
        if m:
            out["교과_학년별반영비율"] = f"1학년{m.group(1)}%+2학년{m.group(2)}%+3학년{m.group(3)}%"
        elif "학년별 가중치 없음" in raw_text or re.search(r"학년별\s*가중치\s*없음", raw_text):
            out["교과_학년별반영비율"] = "학년별가중치없음"

    # ── 진로선택과목_반영여부 ────────────────────────────────────────
    if not out.get("진로선택과목_반영여부"):
        if re.search(r"진로\s*선택", raw_text):
            # "반영하지 않음"은 False
            if re.search(r"진로\s*선택[^.]{0,30}반영\s*하지\s*않|진로\s*선택[^.]{0,30}미\s*반영", raw_text):
                out["진로선택과목_반영여부"] = False
            else:
                out["진로선택과목_반영여부"] = True

    # ── 전형구분_소분류 보완 ─────────────────────────────────────────
    if not out.get("전형구분_소분류"):
        jeon = out.get("전형", "") or ""
        _sobulyu = _classify_sobulyu(jeon, raw_text)
        if _sobulyu:
            out["전형구분_소분류"] = _sobulyu

    return out


def _classify_sobulyu(jeon: str, raw_text: str) -> Optional[str]:
    """전형구분_소분류 분류."""
    text = (jeon + " " + raw_text).lower()
    if re.search(r"지역\s*인재", text):
        return "지역인재전형"
    if re.search(r"고른\s*기회|기회\s*균등", text):
        return "고른기회전형"
    if re.search(r"농어촌", text):
        return "농어촌학생전형"
    if re.search(r"기초\s*생활|기초생활|차상위", text):
        return "기초생활수급자전형"
    if re.search(r"특성화고|특성화 고|재직자", text):
        return "특성화고졸재직자전형"
    if re.search(r"장애인|특수교육", text):
        return "특수교육대상자전형"
    if re.search(r"다문화", text):
        return "다문화전형"
    if re.search(r"사이버국방", text):
        return "사이버국방전형"
    if re.search(r"sw\s*특별|소프트웨어\s*특별", text, re.I):
        return "SW특별전형"
    if re.search(r"모바일\s*과학", text):
        return "모바일과학인재전형"
    if re.search(r"영농\s*창업|영농창업", text):
        return "영농창업인재전형"
    if re.search(r"학교\s*추천|학교추천|교사\s*추천", text):
        return "학교추천전형"
    if re.search(r"논술", text):
        return "논술전형"
    if re.search(r"활동\s*우수|활동우수", text):
        return "활동우수형"
    if re.search(r"계열\s*적합|계열적합|학업\s*우수|학업우수", text):
        return "계열적합전형"
    if re.search(r"잠재\s*역량|잠재역량|자기\s*추천|자기추천", text):
        return "잠재역량전형"
    if re.search(r"일반\s*(?:학생|전형)|학생부종합\s*(?:일반|전형)", text):
        return "일반전형"
    return None


# 공통 행에서 전형별 행으로 전파할 컬럼 (대학 전체에 동일하게 적용되는 정보)
PROPAGATE_COLS = [
    "교과_반영영역_인문", "교과_반영영역_자연", "교과_반영영역_예체능",
    "교과_등급환산방식", "교과_학년별반영비율",
    "평가표기방식", "면접유형",
    "평가요소1_이름", "평가요소1_비중",
    "평가요소2_이름", "평가요소2_비중",
    "평가요소3_이름", "평가요소3_비중",
    "평가요소_세부항목수", "학업역량_정량반영여부",
    "면접_평가위원수", "면접_시간", "면접_문항사전공개여부",
]


def propagate_common_defaults(rows: list[dict]) -> list[dict]:
    """공통 행(전형=""인 행)의 값을 전형별 행에 전파."""
    # 1) 공통 행에서 값 수집
    common_vals: dict[str, object] = {}
    for r in rows:
        jeon = (r.get("전형") or "").strip()
        if not jeon:  # 공통 행
            for col in PROPAGATE_COLS:
                if col not in common_vals and r.get(col) is not None and r.get(col) != "":
                    common_vals[col] = r[col]

    if not common_vals:
        return rows

    # 2) 전형별 행에 전파 (비어있는 컬럼만)
    result = []
    for r in rows:
        jeon = (r.get("전형") or "").strip()
        if jeon:  # 전형명이 있는 행만 전파 대상
            out = dict(r)
            for col, val in common_vals.items():
                if out.get(col) is None or out.get(col) == "":
                    out[col] = val
            result.append(out)
        else:
            result.append(r)
    return result


def normalize_univ(unvcd: str) -> dict:
    """한 대학의 eval 시트 정규화 수행."""
    mapped_path = ROOT / "output" / "mapped" / f"{unvcd}.json"
    norm_path   = ROOT / "output" / "normalized" / f"{unvcd}.json"

    if not mapped_path.exists():
        print(f"  [{unvcd}] mapped 파일 없음, 스킵")
        return {}

    mapped_data = json.loads(mapped_path.read_text(encoding="utf-8"))

    # 기존 normalized 파일 로드 (result 시트 보존용)
    norm_data: dict = {}
    if norm_path.exists():
        norm_data = json.loads(norm_path.read_text(encoding="utf-8"))

    stats: dict[str, dict] = {}

    for sheet_name in ["susi_eval", "jeongsi_eval"]:
        sheet = mapped_data.get(sheet_name, {})
        if isinstance(sheet, dict):
            rows = sheet.get("mapped", [])
        else:
            rows = sheet

        if not rows:
            norm_data[sheet_name] = []
            continue

        # 1차 정규화 (개별 행)
        normalized_rows = [normalize_eval_row(r) for r in rows]
        # 2차: 공통 행 → 전형별 행 전파
        normalized_rows = propagate_common_defaults(normalized_rows)
        norm_data[sheet_name] = normalized_rows

        # 채움률 계산
        seed = SCHEMA_SEED_COLS
        total_possible = len(rows) * len(seed)
        filled = sum(
            1 for r in normalized_rows
            for c in seed
            if r.get(c) is not None and r.get(c) != ""
        )
        stats[sheet_name] = {
            "rows": len(rows),
            "fill_rate": filled / total_possible if total_possible else 0,
        }

    norm_path.write_text(json.dumps(norm_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def main():
    unvs = {
        "0000063": "가천대학교",
        "0000019": "서울대학교",
        "0000027": "제주대학교",
        "0000149": "연세대학교",
        "0000069": "고려대학교",
        "0000014": "부산대학교",
        "0000005": "경북대학교",
        "0000245": "남서울대학교",
    }

    print("\n[T4b normalizer-eval] 시작")
    total_se_fill = []

    for unvcd, name in unvs.items():
        stats = normalize_univ(unvcd)
        for sheet, info in stats.items():
            fill = info["fill_rate"]
            print(f"  [{unvcd}] {name} {sheet}: {info['rows']}행, seed 채움률 {fill:.1%}")
            if sheet == "susi_eval":
                total_se_fill.extend([fill] * info["rows"])

    if total_se_fill:
        avg = sum(total_se_fill) / len(total_se_fill)
        print(f"\n[T4b] susi_eval 전체 평균 seed 채움률: {avg:.1%}")
        if avg >= 0.50:
            print("  ✓ DoD 3 달성!")
        else:
            print(f"  ✗ DoD 3 미달 ({avg:.1%} < 50%)")

    print("[T4b normalizer-eval] 완료\n")


if __name__ == "__main__":
    main()
