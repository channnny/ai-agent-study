import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import parse_element as EL
FIX = pathlib.Path(__file__).parent / "fixtures" / "element_가천대학생부교과.html"

def test_element_flattened_raw():
    recs = EL.parse(FIX.read_text(encoding="utf-8"), 대학명="가천대학교", 전형명="학생부교과")
    assert len(recs) >= 1
    assert all(isinstance(r, dict) and r.get("표이름") for r in recs)
    caps = {r["표이름"] for r in recs}
    assert any("학생부" in c for c in caps)

def test_empty_section_returns_empty():
    assert EL.parse("<html><body><p>no section</p></body></html>") == []
