import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import enumerate_admissions as E

FIX = pathlib.Path(__file__).parent / "fixtures" / "enum_가천대.html"

def test_parses_admission_rows():
    rows = E.parse_fragment(FIX.read_text(encoding="utf-8"))
    assert len(rows) == 16
    r = rows[0]
    for k in E.PARAM_KEYS:
        assert k in r and r[k]
    assert r["전형명"]
    assert r["ruCd"] == "0247247" and r["ruSn"] == "111786"
    assert r["slcnTypeCd"] == "04" and r["slcnCd"] == "01"
