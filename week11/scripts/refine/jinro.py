"""④ 진로 A/B/C — 각주 성취도 환산표 파싱(다양 포맷) + 비-성취도 방식은 미반영 재분류.

포맷: A=1 / A:10 / A-10 / A(30) / (A)2점 / 수(A)=98 / A 3점, 소수값(9.5) 허용.
성취도 A/B/C 표 있으면 파싱, 성취도 언급하나 값 미공개면 '내부확인'(소스한계),
진로가 A/B/C 아닌 방식(석차등급/상위N)이면 '미반영', 진로칸 공란도 '미반영'.
"""
import re
from cols import c, S2_진로선택, S2_각주


def _L(x):
    # 성취도명?( 괄호?문자괄호? · 라벨괄호(비숫자) · 구분자=임의 비영숫자·비한글 0~3자
    # (하이픈·엔대시·화살표·등호·콜론·괄호·공백 모두 포괄) · 숫자(소수허용)
    return (r"[가-힣]?\(?" + x + r"\)?(?:\([^0-9)]*\))?[^0-9A-Za-z가-힣]{0,3}(\d+(?:\.\d+)?)")


_P_ABC = re.compile(_L("A") + r".{0,18}?" + _L("B") + r".{0,18}?" + _L("C"), re.S)


def refine_jinro(s2, jonghap: bool, flags: list) -> str:
    if jonghap:
        return "해당없음(종합)"
    진로 = c(s2[S2_진로선택]).replace("/", "").strip()
    if not 진로:
        return "미반영"
    각주 = c(s2[S2_각주])
    m = _P_ABC.search(각주)
    if m:
        a, b, cc = m.group(1), m.group(2), m.group(3)
        if "." in a + b + cc or max(float(a), float(b), float(cc)) > 9:
            unit = "점"                                  # 소수/9초과 → 점수(등급은 정수 1~9)
        else:
            pre = 각주[max(0, m.start() - 15):m.start()]
            unit = "점" if "점" in pre else "등급"
        return f"A={a},B={b},C={cc}{unit}"
    # 진로 반영O(진로칸 채워짐)이나 A/B/C 환산값 미표기 → 내부확인(데이터랩스 규칙, 소스한계).
    # 미반영은 진로칸 공란일 때만(위에서 처리).
    flags.append("진로내부확인")
    return "내부확인"
