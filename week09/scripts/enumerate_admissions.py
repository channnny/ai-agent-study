import re, html as _html
from bs4 import BeautifulSoup
import net

VIEW_URL = "https://www.adiga.kr/ucp/prc/uni/admssUnivView.do"
UNIV_AJAX_URL = "https://www.adiga.kr/ucp/prc/uni/admssUnivAjax.do"
LIST_URL = "https://www.adiga.kr/ucp/prc/uni/admssUnivDetailLstAjax.do"
PARAM_KEYS = ("unvCd", "comScsbjtCd", "slcnGroupCd", "rcmtMmntCd",
              "ruCd", "ruSn", "lclsfAftCd", "slcnTypeCd", "slcnCd")

def _form_fields(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    frm = soup.find(id="frm")
    out = {}
    if frm:
        for el in frm.find_all(["input", "select"]):
            name = el.get("name")
            if name:
                out[name] = el.get("value") or ""
    return out

def parse_fragment(html: str) -> list[dict]:
    """LstAjax 프래그먼트 → 전형 행 dict 목록."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for a in soup.select("a.selectUnivComScsbjtCd"):
        oc = a.get("onclick", "")
        m = re.search(r"fnDetailPage\(([^)]*)\)", _html.unescape(oc))
        if not m:
            continue
        args = [t.strip().strip("'\"").strip() for t in m.group(1).split(",")]
        if len(args) < len(PARAM_KEYS):
            continue
        rec = {k: args[i] for i, k in enumerate(PARAM_KEYS)}
        rec["전형명"] = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        rows.append(rec)
    return rows

def fetch(unv_cd: str, syr: str = "2027") -> list[dict]:
    """대학 → 전형 목록 (3단계 AJAX)."""
    import requests
    sess = requests.Session()
    rv = net._request("GET", VIEW_URL,
                      params={"menuId": "PCPRCINF2000", "unvCd": unv_cd, "searchSyr": syr},
                      session=sess)
    form = _form_fields(rv.text)
    form.update({"searchSyr": syr, "unvCd": unv_cd})
    hdr = {"X-Requested-With": "XMLHttpRequest",
           "Referer": rv.url, "Origin": "https://www.adiga.kr"}
    ra = net._request("POST", UNIV_AJAX_URL, data={**form, "searchUnvCode": unv_cd},
                      headers=hdr, session=sess)
    li = BeautifulSoup(ra.text, "html.parser").select_one("li.opnfldClass[comscsbjtcd]")
    if not li:
        return []
    com = li.get("comscsbjtcd")
    rl = net._request("POST", LIST_URL, data={**form, "unvCd": unv_cd, "comScsbjtCd": com},
                      headers=hdr, session=sess)
    return parse_fragment(rl.text)
