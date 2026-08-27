"""①② 수능최저 — 골든셋(데이터랩스 2027_최저관련_정제) 대조로 확정된 규칙 A~J.

표기 원칙: 모든 최저는 예외 없이 ① 'N합M' / ② '<영역> 중 N개 등급합 M'.
개별등급형·평균등급형·영한단독·OR형은 전부 N합M으로 환산한다.

  A 계열 오탐 해제(+계열별 필수영역 보존)  B 모집단위군 블록 분기
  C 평균등급형 → N합(N×M)                  D 등급컷 어순 확장(+D-1 '등급' 생략형)
  E 번호목록형 다조건 → 영어 합산           F 개별등급형 → N합(N×M)
  G 불릿 나열 + 말미 조건문                 H 영·한 단독조건 → 등급 합산
  I OR(택1) 다조건 → 대표 등급합 채택       J 최저 아님(필드 오적재) → '최저 없음'
"""
import re
from cols import (c, num, S1_CHOI_영역수, S1_CHOI_세부,
                  S1_국, S1_수, S1_영, S1_탐, S1_탐과목, S1_한)

_TAM_과 = ["물리", "화학", "생명", "지구과학", "과학"]
_TAM_사 = ["지리", "역사", "윤리", "사회", "경제", "정치", "세계", "수산", "해운",
           "농업", "공업", "상업", "가사", "인간발달", "직업"]
_AREA_KW = ("국어", "수학", "영어", "탐구", "한국사")


# ────────────────────────── 영역 조합(②) ──────────────────────────
def _tamgu_label(과목: str) -> str:
    사 = any(k in 과목 for k in _TAM_사)
    과 = any(k in 과목 for k in _TAM_과)
    if 과 and not 사:
        return "과"
    if 사 and not 과:
        return "사"
    return "탐"


def _tam_cnt(txt: str) -> str:
    """세부내용에서 탐구 반영 과목수. '상위 N과목'이 있으면 그것이 우선."""
    m = re.search(r"(?:상위|우수|최상위)\s*(\d+)\s*개?\s*과목", txt)
    if m:
        return m.group(1)
    m = re.search(r"탐구[^\n]{0,15}?(\d+)\s*개?\s*과목", txt)
    return m.group(1) if m else "1"


def _areas(s1, txt: str):
    """구조화 컬럼 → (영역라벨 리스트, 필수 리스트)."""
    areas, 필수 = [], []
    for label, idx in [("국", S1_국), ("수", S1_수), ("영", S1_영)]:
        v = c(s1[idx])
        if v:
            areas.append(label)
            if "필수" in v:
                필수.append(label)
    탐과목 = c(s1[S1_탐과목])
    if c(s1[S1_탐]) or 탐과목:
        areas.append(f"{_tamgu_label(탐과목)}({_tam_cnt(txt)})")
        if "필수" in c(s1[S1_탐]):
            필수.append("탐")
    return areas, 필수


def _txt_musts(txt: str) -> list:
    """본문에서 필수 지정 영역 추출('수학필수', '수학 포함' 등)."""
    out = []
    for label, kw in [("국", "국어"), ("수", "수학"), ("영", "영어")]:
        if re.search(kw + r"\s*(?:영역)?\s*(?:필수|을?\s*필수|.{0,6}?포함)", txt):
            out.append(label)
    return out


def _build2(s1, txt, N, M, extra_musts=None):
    areas, 필수 = _areas(s1, txt)
    필수 = list(dict.fromkeys(필수 + (extra_musts or _txt_musts(txt))))
    if not areas:
        return None
    body = ",".join(areas) + f" 중 {N}개 등급합 {M}"
    if 필수 and len(필수) < len(areas):
        body += f" ({','.join(필수)} 포함)"
    han = c(s1[S1_한])
    if han and "필수" not in han:
        hm = re.search(r"\d+", han)
        if hm:
            body += f" 한{hm.group(0)}"
    return body


# ────────────────────────── 조건 파싱 ──────────────────────────
_P_F = re.compile(r"(\d+)\s*개\s*영역?[^\n]{0,6}?각[^\n]{0,6}?(\d+)\s*등급")                        # F 개별등급형
_P_MODU = re.compile(r"(?:영역|과목)\s*모두\s*(\d+)\s*등급")                                 # F' 모두형(환산 안함)
# '평균등급 5등급' / '평균 5등급' — 숫자 뒤 '등급'이 붙은 경우만 컷으로 인정
# ('평균의 50% 이상' 같은 비율 문구를 컷으로 오인하지 않기 위함)
_P_CAVG = re.compile(r"평균\s*(?:등급)?\s*(?:이|은|는|의)?\s*(\d+)\s*등급")                                              # C
_P_E1 = re.compile(r"(\d+)\s*등급\s*(\d+)\s*개\s*이상")                                      # E-1 개수형
_P_HABNUM = re.compile(r"합(?!격)(?:산)?(?:등급)?\s*(?:이|의)?\s*(\d+)(?!\d)(?!\s*%)")
_P_CNT = re.compile(r"(\d+)\s*(?:개|과목|영역)")
_P_SANGWI = re.compile(r"상위\s*\d+\s*개\s*(?:영역|등급|과목)?\s*과\s*[가-힣]{2,4}")
_P_PAREN = re.compile(r"\([^()]*\)|\[[^\[\]]*\]")
_HANSU = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5}
_P_HANSU = re.compile(r"(한|두|세|네|다섯)\s*개\s*(?:영역|과목)")
_P_D = re.compile(r"(\d+)\s*개\s*(?:영역|과목)[^\n]{0,12}?(\d+)\s*등?급?\s*(?:이내|이하)")   # D/D-1
_P_CUT = re.compile(r"(?:등급\s*(\d+)|(\d+)\s*등급)\s*(?:이내|이하)")
_P_영 = re.compile(r"영어\s*(?:영역)?\s*(\d+)\s*등급")
_P_한 = re.compile(r"한국사\s*(?:영역)?\s*(\d+)\s*등급")


def _hab(txt, 영역수):
    """'합 M' 을 먼저 찾고, 그 앞에서 가장 가까운 'N개/N과목/N영역' 을 N으로 취한다.
    '4개 영역 중 3개 영역 등급의 합이 7' → (3,7)  ※앞의 4를 잡던 버그 방지."""
    fallback = None
    for m in _P_HABNUM.finditer(txt):
        M = int(m.group(1))
        head = txt[:m.start()]
        flat = _P_PAREN.sub("", head)             # 괄호/대괄호 안 '(2과목 평균)' 등은 카운트 제외
        ns = _P_CNT.findall(flat)
        if not ns:
            hs = _P_HANSU.findall(flat)           # '두개 영역' 한글 수사
            ns = [str(_HANSU[hs[-1]])] if hs else []
        if ns:
            N = int(ns[-1])
            if _P_SANGWI.search(flat):            # '상위 N개 …과 수학 합산' → N+1
                N += 1
            return N, M
        mm = re.search(r"(\d+)\s*$", flat.strip())   # '3합 5' 처럼 단위 없는 표기
        if mm:
            return int(mm.group(1)), M
        if fallback is None and 영역수:
            fallback = (int(영역수), M)
    return fallback


def _cond(txt: str, 영역수):
    """단일 조건 블록 → (N, M, kind) or None. 모든 형태를 N합M으로 환산."""
    m = _P_F.search(txt)                                     # F 'N개 영역 각 M등급' → N합(N×M)
    if m:
        n, g = int(m.group(1)), int(m.group(2))
        return n, n * g, "F"
    m = _P_CAVG.search(txt)                                  # C 평균등급형 → N합(N×M)
    if m:
        g = int(m.group(1))
        ns = _P_CNT.findall(_P_PAREN.sub("", txt[:m.start()]))
        n = int(ns[-1]) if ns else (int(영역수) if 영역수 else None)
        if n:
            return n, n * g, "C"
    m = _P_E1.search(txt)                                    # E-1 'M등급 N개 이상' → N합(N×M)
    if m:
        g, n = int(m.group(1)), int(m.group(2))
        return n, n * g, "E1"
    h = _hab(txt, 영역수)                                     # 등급합(기본형·G·I)
    if h:
        return h[0], h[1], "HAB"
    m = _P_MODU.search(txt)                                  # '영역 모두 M등급' → 영역수합M
    if m and 영역수:
        return int(영역수), int(m.group(1)), "MODU"
    m = _P_D.search(txt)                                     # D 등급컷(영역수 포함)
    if m:
        return int(m.group(1)), int(m.group(2)), "D"
    me, mh = _P_영.search(txt), _P_한.search(txt)             # H 영·한 단독조건 → 등급 합산
    if me and mh and not re.search(r"(?:개|과목|영역)\s*(?:의)?\s*(?:등급\s*)?합", txt):
        return 2, int(me.group(1)) + int(mh.group(1)), "H"
    if 영역수 and (("또는" in txt) or ("①" in txt and "②" in txt)):
        cuts = [int(x) for x in re.findall(r"(\d+)\s*등급", txt)]   # 선택과목/조건별 분기
        if len(cuts) >= 2:
            return int(영역수), min(cuts), "OR"                      # 가장 엄격한 기준 채택
    m = _P_CUT.search(txt)                                   # D 등급컷(영역수는 구조화 컬럼)
    if m and 영역수:
        return int(영역수), int(m.group(1) or m.group(2)), "D"
    return None


def _has_num_list(txt: str) -> bool:
    return len(re.findall(r"(?:^|\n)\s*\d+\.\s", txt)) >= 2


# ────────────────────────── 블록 분기(A·B) ──────────────────────────
_P_BLK = re.compile(r"(?:^|\n)\s*[*\-]?\s*([^\n:：]{2,80}?)\s*[:：]\s*(.*?)(?=(?:\n\s*[*\-]?\s*[^\n:：]{2,80}?\s*[:：])|$)", re.S)
_P_BLK2 = re.compile(r"(?:^|\n)\s*\[([^\]\n]{2,60})\]\s*(.*?)(?=(?:\n\s*\[)|$)", re.S)


def _blocks(txt: str) -> list:
    """(라벨, 본문) 전체. 라벨 뒤 콜론형과 [라벨]형 모두."""
    out = [(l.strip(), b) for l, b in _P_BLK.findall(txt)]
    if len(out) < 2:
        out = [(l.strip(), b) for l, b in _P_BLK2.findall(txt)]
    return out


def _gyeyeol_musts(txt: str) -> str:
    """'인문계열은 국어, 자연계열은 수학을 응시하여야 함' → '인문:국어필수, 자연:수학필수'."""
    out = []
    for gy in ("인문", "자연"):
        m = re.search(gy + r"계열은?\s*([가-힣]{2,4})\s*(?:영역|과목)", txt)
        if m:
            out.append(f"{gy}:{m.group(1)}필수")
    return ", ".join(out)


# ────────────────────────── 엔트리 ──────────────────────────
# 모집단위명 → 계열 추정. 순서 중요(앞 규칙 우선) — '의류환경학과'가 '환경'에 걸려
# 자연으로 오분류되는 함정 때문에 인문 확정 키워드를 먼저 둔다.
_GYE_RULES = [
    ("인문", ["의류", "아동", "가족", "디자인", "패션", "복지", "유아", "관광", "무역",
             "회계", "세무", "광고", "홍보", "커뮤니케이션", "문헌정보"]),
    ("자연", ["간호", "식품", "영양", "건축", "토목", "통계", "수학", "물리", "화학", "생명",
             "생물", "컴퓨터", "소프트웨어", "전자", "전기", "기계", "재료", "신소재", "산업공학",
             "의예", "치의", "한의", "약학", "수의", "보건", "환경", "농업", "원예", "축산",
             "해양", "항공", "에너지", "반도체", "데이터", "인공지능", "AI", "공학", "과학"]),
    ("인문", ["국어", "영어", "영문", "중문", "일문", "불문", "독문", "노문", "사학", "역사",
             "철학", "경영", "경제", "행정", "법학", "사회", "교육", "심리", "정치", "외교",
             "미디어", "신문", "방송", "문화", "종교", "신학", "어문", "인문"]),
]


def _gyeyeol_of(모집: str):
    for gy, kws in _GYE_RULES:
        if any(k in 모집 for k in kws):
            return gy
    return None


def _fmt_with_eng(block: str, cond) -> str:
    """계열 절의 (N,M)에 영어 별도조건을 합산해 'N합M' 문자열로."""
    N, M, _ = cond
    me = _P_영.search(block)
    head = block[:block.find(str(N) + "개")] if (str(N) + "개") in block else block[:120]
    if me and "영어" not in head:
        N, M = N + 1, M + int(me.group(1))
    return f"{N}합{M}"


def refine_choi(s1, flags: list) -> tuple:
    세부 = c(s1[S1_CHOI_세부])
    영역수 = num(s1[S1_CHOI_영역수])
    if not 세부 and not 영역수:
        return "최저 없음", "최저 없음"
    txt = 세부.replace("!", "")
    # J · 최저 아님(교과 안내문 등 오적재)
    if not 영역수 and not any(k in txt for k in _AREA_KW):
        return "최저 없음", "최저 없음"

    모집 = c(s1[6])
    # 인문/자연 계열 택1 절 — 계열별 값이 다르면 모집단위 계열을 구조화 컬럼으로 알 수 없음 → 사람 판단
    mi = re.search(r"[∙·]\s*인문\s*계열(.*?)(?=[∙·]\s*자연\s*계열|$)", txt, re.S)
    mj = re.search(r"[∙·]\s*자연\s*계열(.*)$", txt, re.S)
    if mi and mj:
        ci, cj = _cond(mi.group(1), 영역수), _cond(mj.group(1), 영역수)
        if ci and cj:
            fi, fj = _fmt_with_eng(mi.group(1), ci), _fmt_with_eng(mj.group(1), cj)
            if fi != fj:
                gy = _gyeyeol_of(모집)          # 모집단위명으로 계열 추정
                if gy is None:
                    flags.append("최저계열택1")
                    tag = f"검증필요:계열택1 [인문 {fi} / 자연 {fj}]"
                    return tag, tag
                flags.append("최저계열추정")
                blk, val = (mi.group(1), fi) if gy == "인문" else (mj.group(1), fj)
                N, M = (int(x) for x in val.split("합"))
                y = _build2(s1, blk, N, M) or f"{N}개 등급합 {M}"
                if "과학탐구만" in blk or ("과학탐구" in blk and "사회탐구" not in blk):
                    y = y.replace("탐(", "과(")          # 자연계열 절은 과탐만 반영
                y = y.replace("(영,", "(").replace(" (영 포함)", "")  # 영어는 합에 통합됨(필수 아님)
                return val, f"{y} [계열추정:{gy}]"
            txt = mj.group(1)
    # B · 모집단위군/계열 블록 분기 (블록 2개 이상일 때만 다조건)
    blks = _blocks(txt)
    if len([1 for _, b in blks if _cond(b, 영역수)]) >= 2:
        pick = None
        for lab, b in blks:                            # 1순위: 모집단위명이 라벨에 나열됨
            toks = [t.strip() for t in re.split(r"[,·/]", lab) if len(t.strip()) >= 2]
            if any(t in 모집 or 모집 in t for t in toks):
                pick = b
                break
        if pick is not None and "없음" in pick and not _cond(pick, 영역수):
            return "최저 없음", "최저 없음"
        if pick is None:                               # 2순위: '그 외/기타' 포괄 블록
            pick = next((b for lab, b in blks
                         if re.search(r"그\s*외|그외|기타|이외", lab) and _cond(b, 영역수)), None)
        if pick is None:                               # 3순위: 포괄 계열 라벨(공학계열 등)
            pick = next((b for lab, b in blks
                         if "계열" in lab and _cond(b, 영역수)
                         and not re.search(r"(인문|자연|예체능|국제)\s*계열", lab)), None)
        if pick is None:                               # 4순위: 마지막 유효 블록
            cands = [b for lab, b in blks if _cond(b, 영역수)]
            pick = cands[-1] if cands else None
        sub = _cond(pick, 영역수) if pick is not None else None
        if sub:
            y = _build2(s1, txt, sub[0], sub[1]) or f"{sub[0]}개 등급합 {sub[1]}"
            return f"{sub[0]}합{sub[1]}", y

    cond = _cond(txt, 영역수)
    if cond:
        N, M, kind = cond
        if kind == "H":                          # H · 영·한 단독조건은 구조화 영역 대신 실제 상한 표기
            me, mh = _P_영.search(txt), _P_한.search(txt)
            hit = [(k, int(m.group(1))) for k, m in (("영", me), ("한", mh)) if m]
            lab = ",".join(f"{k}({'필,' if k == '한' else ''}{v})" for k, v in hit)
            return f"{N}합{M}", f"{lab} — {N}개 등급합 {M}"
        # E · 번호목록형에서 영어 등급이 별도 조건이면 영역수+1, 합+영어등급
        if _has_num_list(txt) or re.search(r"및\s*영어\s*\d+\s*등급", txt):
            head = txt[:txt.find(str(N) + "개")] if (str(N) + "개") in txt else txt[:120]
            me = _P_영.search(txt)
            if me and "영어" not in head:
                N, M = N + 1, M + int(me.group(1))
                flags.append("최저E영어합산")
        y = _build2(s1, txt, N, M) or f"{N}개 등급합 {M}"   # 구조화 영역 없으면 영역 미상 표기
        gy = _gyeyeol_musts(txt)
        if gy:
            y += f" [{gy}]"
        return f"{N}합{M}", y

    # H · 등급합 없이 영어·한국사 단독조건만
    me, mh = _P_영.search(txt), _P_한.search(txt)
    parts = [("영", me), ("한", mh)]
    hit = [(lab, int(m.group(1))) for lab, m in parts if m]
    if hit:
        N, M = len(hit), sum(v for _, v in hit)
        lab2 = ",".join(f"{k}({'필,' if k == '한' else ''}{v})" for k, v in hit)
        return f"{N}합{M}", f"{lab2} — {N}개 등급합 {M}"

    flags.append("최저파싱")
    tag = f"검증필요:최저 [{txt[:30]}]"
    return tag, tag
