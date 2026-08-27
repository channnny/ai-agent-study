"""정제 파서 단위 테스트 — 검증노트 4대학 케이스 + 실데이터 확인 케이스.

pytest 없이도: python tests/test_refine.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "refine"))
import cols as C  # noqa: E402
from jonghap import is_jonghap  # noqa: E402
from gyogwa import refine_gyogwa  # noqa: E402
from ratio import refine_5a, refine_5b  # noqa: E402
from choi import refine_choi  # noqa: E402
from jinro import refine_jinro  # noqa: E402


def s1(d):
    r = [None] * 46
    for k, v in d.items():
        r[k] = v
    return tuple(r)


def s2(d):
    r = [None] * 55
    for k, v in d.items():
        r[k] = v
    return tuple(r)


# ── ③ 교과반영영역 ──
def test_gyogwa():
    assert refine_gyogwa("국어 / 수학 / 영어 / 사회(역사/도덕포함) / 과학 / 한국사", False) == "국영수사과한"
    assert refine_gyogwa("국어 / 수학 / 영어 / 사회(역사/도덕포함)", False) == "국영수사"   # 가천대(과학·한국사 없음)
    assert refine_gyogwa("국어 / 수학 / 영어 / 사회 / 과학 / 한국사", False) == "국영수사과한"       # 남서울/가야
    assert refine_gyogwa("아무거나", True) == "해당없음(종합)"
    assert refine_gyogwa("", False) == "미반영"


# ── 5a 전형요소별 ──
def test_5a():
    # 일괄 교과전형: 학생부100 → 요소(교과100)
    r1 = s1({C.S1_SEL_MODEL: "일괄합산", C.S1_SEL_RATE: "100", C.S1_RB["학생부"]: "100"})
    r2 = s2({C.S2_요소["교과"]: "100"})
    assert refine_5a(r1, r2, False, []) == "[일괄]교과100"
    # 일괄: 학생부100 → 교과90+출결10 (남서울)
    r2b = s2({C.S2_요소["교과"]: "90", C.S2_요소["출결"]: "10"})
    assert refine_5a(r1, r2b, False, []) == "[일괄]교과90+출결10"
    # 종합: 서류100
    r1c = s1({C.S1_SEL_MODEL: "일괄합산", C.S1_RB["학생부"]: "100"})
    assert refine_5a(r1c, s2({}), True, []) == "[일괄]서류100"
    # 수능+면접
    r1d = s1({C.S1_SEL_MODEL: "일괄합산", C.S1_RB["수능"]: "80", C.S1_RB["면접"]: "20"})
    assert refine_5a(r1d, s2({}), False, []) == "[일괄]수능80+면접20"


# ── 5b 학년/요소별 ──
def test_5b():
    r2 = s2({C.S2_학년공통: "전학년 공통", C.S2_공통비율: "100", C.S2_요소["교과"]: "100"})
    assert refine_5b(r2, False, []) == "[학년]전학년공통100 [요소]교과100"
    r2b = s2({C.S2_학년공통: "전학년 공통", C.S2_공통비율: "100",
              C.S2_요소["교과"]: "90", C.S2_요소["출결"]: "10"})
    assert refine_5b(r2b, False, []) == "[학년]전학년공통100 [요소]교과90+출결10"
    assert refine_5b(s2({}), True, []) == "해당없음(종합)"
    # 합≠100 → 플래그
    fl = []
    r2c = s2({C.S2_학년공통: "전학년 공통", C.S2_공통비율: "100",
              C.S2_요소["교과"]: "80", C.S2_요소["출결"]: "10"})
    refine_5b(r2c, False, fl)
    assert any("5b합90" in f for f in fl)


# ── ①② 수능최저 ──
def test_choi():
    # 미입력 → 최저 없음
    assert refine_choi(s1({}), []) == ("최저 없음", "최저 없음")
    # 단순: 4개 중 2개 합 5 → 영역수=2 → 2합5 (버그였던 케이스)
    r = s1({C.S1_CHOI_영역수: "2", C.S1_CHOI_세부: "4개 영역 중 2개 영역 등급 합 5 이내",
            C.S1_국: "선택반영", C.S1_수: "선택반영", C.S1_영: "선택반영", C.S1_탐: "선택반영"})
    n, y = refine_choi(r, [])
    assert n == "2합5", n
    assert y == "국,수,영,탐(1) 중 2개 등급합 5", y
    # E · 번호목록형 다조건 → 영어를 합에 통합 (영역수+1, 합+영어등급)
    r2 = s1({C.S1_CHOI_영역수: "4", C.S1_국: "선택반영", C.S1_수: "선택반영",
             C.S1_영: "필수반영", C.S1_탐과목: "물리학Ⅰ,화학Ⅰ,생명과학Ⅰ",
             C.S1_CHOI_세부: "\n1. 국어, 수학, 과학탐구 과목 가운데 수학을 포함하여 2개 과목 등급 합 2 이내"
                             "\n2. 영어 3등급 이내\n3. 한국사 4등급 이내"})
    n2, y2 = refine_choi(r2, [])
    assert n2 == "3합5", n2                      # 2합2 + 영3 = 3합5 (연세대 의·치·약)
    # F · 개별등급형 'N개영역 각 M등급' → N합(N×M)
    r3 = s1({C.S1_CHOI_영역수: "3", C.S1_국: "선택반영", C.S1_수: "선택반영", C.S1_영: "선택반영",
             C.S1_탐과목: "물리학Ⅰ,화학Ⅰ",
             C.S1_CHOI_세부: "국어, 수학, 영어, 과학탐구(2과목) 3개영역 각 1등급(과학탐구 적용 시 2과목 평균)"})
    n3, y3 = refine_choi(r3, [])
    assert n3 == "3합3", n3
    assert y3 == "국,수,영,과(2) 중 3개 등급합 3", y3
    # C · 평균등급형 → N합(N×M)
    r4 = s1({C.S1_CHOI_영역수: "2", C.S1_국: "선택반영", C.S1_수: "선택반영", C.S1_영: "선택반영",
             C.S1_탐과목: "한국지리,물리학Ⅰ",
             C.S1_CHOI_세부: "국어, 영어, 수학, 탐구(1과목) 중 우수 2과목 평균등급 5등급"})
    n4, _ = refine_choi(r4, [])
    assert n4 == "2합10", n4
    # D · '등급 4이내' 어순 (홍익대 26건 원인)
    r5 = s1({C.S1_CHOI_영역수: "1", C.S1_국: "선택반영", C.S1_수: "선택반영", C.S1_영: "선택반영",
             C.S1_탐과목: "한국지리,물리학Ⅰ",
             C.S1_CHOI_세부: "- 국어, 수학, 영어, 탐구(사회/과학) 중 1개 영역 등급 4이내"})
    n5, y5 = refine_choi(r5, [])
    assert n5 == "1합4", n5
    assert y5 == "국,수,영,탐(1) 중 1개 등급합 4", y5
    # H · 등급합 없는 영어·한국사 단독조건 → 등급 합산
    r6 = s1({C.S1_CHOI_세부: "영어 3등급 이내\n한국사 4등급 이내"})
    n6, _ = refine_choi(r6, [])
    assert n6 == "2합7", n6
    # J · 최저 아님(교과 안내문 오적재) → 최저 없음
    r7 = s1({C.S1_CHOI_세부: "과목선택은 학년, 학기 구분 없이 석차등급이 기재된 모든 과목을 대상으로 함"})
    assert refine_choi(r7, []) == ("최저 없음", "최저 없음")
    # A · 계열 언급만 있고 계열별 합조건 없음 → 단일조건 + 계열 필수영역 보존
    r8 = s1({C.S1_CHOI_영역수: "2", C.S1_국: "선택반영", C.S1_수: "선택반영", C.S1_영: "선택반영",
             C.S1_탐과목: "한국지리,물리학Ⅰ",
             C.S1_CHOI_세부: "[공통]2개 영역 등급 합 5 이내\n*탐구영역은 응시한 2과목 중 상위 1개 과목으로 반영함"
                             "\n※ 인문계열은 국어 영역, 자연계열은 수학 영역을 응시하여야 함"})
    n8, y8 = refine_choi(r8, [])
    assert n8 == "2합5", n8
    assert "인문:국어필수" in y8 and "자연:수학필수" in y8, y8


# ── ④ 진로 A/B/C ──
def test_jinro():
    # 등급환산형 (가야/남서울)
    r2 = s2({C.S2_진로선택: "고전 읽기,기하",
             C.S2_각주: "진로 선택과목은 A : 1등급, B : 3등급, C : 5등급 최대 2과목"})
    assert refine_jinro(r2, False, []) == "A=1,B=3,C=5등급"
    # 등호형(단위없음) + '등급으로 변환' context → 등급 (숙명)
    r2g = s2({C.S2_진로선택: "기하", C.S2_각주: "성취도를 등급으로 변환(성취도 A=1, B=3, C=5)하여 반영"})
    assert refine_jinro(r2g, False, []) == "A=1,B=3,C=5등급"
    # 괄호 점수형 (금강)
    r2p = s2({C.S2_진로선택: "기하", C.S2_각주: "진로과목 성취도 A(100점), B(96점), C(90점)"})
    assert refine_jinro(r2p, False, []) == "A=100,B=96,C=90점"
    # 등호형 + 라벨 + '점수' context → 점
    r2l = s2({C.S2_진로선택: "기하", C.S2_각주: "반영 점수: A(우수)=3, B(보통)=2, C(미흡)=0"})
    assert refine_jinro(r2l, False, []) == "A=3,B=2,C=0점"
    # 진로 있으나 각주 환산표 진짜 없음 → 내부확인 (가톨릭)
    r2b = s2({C.S2_진로선택: "고전 읽기", C.S2_각주: "성취도를 환산석차등급으로 반영"})
    assert refine_jinro(r2b, False, []) == "내부확인"
    # 진로 미반영 (가천대)
    assert refine_jinro(s2({C.S2_진로선택: " / / "}), False, []) == "미반영"
    # 종합
    assert refine_jinro(s2({C.S2_진로선택: "x"}), True, []) == "해당없음(종합)"


# ── 종합전형 판별 ──
def test_jonghap():
    assert is_jonghap("학생부종합(활동우수형)", s2({})) is True
    assert is_jonghap("학생부교과(일반전형)", s2({C.S2_서류학생부: "O"})) is True   # 서류평가 + 교과없음
    assert is_jonghap("학생부교과(일반전형)", s2({C.S2_반영교과: "국어"})) is False


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for t in tests:
        try:
            t(); print(f"  ✓ {t.__name__}")
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}"); fails += 1
    print("PASS" if not fails else f"FAIL ({fails}/{len(tests)})")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
