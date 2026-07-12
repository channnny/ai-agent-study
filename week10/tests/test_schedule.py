import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import parse_schedule as S
FIX = pathlib.Path(__file__).parent / "fixtures" / "schedule_가천대논술.html"

def test_fixed_23_columns_and_values():
    recs = S.parse(FIX.read_text(encoding="utf-8"), 대학명="가천대학교", 전형명="논술위주(논술)")
    assert len(recs) == 1
    r = recs[0]
    assert list(S.COLUMNS) and all(c in r for c in S.COLUMNS)   # 23열 모두 존재
    assert r["원서접수_인터넷"].startswith("2026-09-07")
    assert r["합격자발표일"].startswith("1차")
    assert r["선발모형"] == "일괄합산"
    assert r["선발비율"] == "100"
    assert r["모집단위명"] == "AI인문대학"
    assert r["대학명"] == "가천대학교"
