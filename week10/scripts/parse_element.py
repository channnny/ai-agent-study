"""전형요소 (div.admssDtlSection 내 표) raw 평면화 파서."""
from bs4 import BeautifulSoup


def _parse_table(table, 대학명, 전형명, 표이름):
    """단일 표를 행별 dict로 변환. 헤더(th) 텍스트를 키로 사용."""
    rows = table.find_all("tr")
    header_labels = []
    result = []

    for tr in rows:
        ths = tr.find_all("th")
        tds = tr.find_all("td")

        if ths and not tds:
            # 순수 헤더 행 → 라벨 업데이트
            header_labels = [th.get_text(strip=True) for th in ths]
        elif tds:
            if not header_labels:
                continue
            vals = [td.get_text(strip=True) for td in tds]
            rec = {"대학명": 대학명, "전형명": 전형명, "표이름": 표이름}
            for label, val in zip(header_labels, vals):
                rec[label] = val
            result.append(rec)

    return result


def parse(html: str, 대학명: str = "", 전형명: str = "") -> list:
    """div.admssDtlSection 내 표만 순회, raw 평면화 dict 목록 반환.
    admssDtlSection이 없으면 [] 반환."""
    soup = BeautifulSoup(html, "html.parser")
    sections = soup.find_all("div", class_="admssDtlSection")
    if not sections:
        return []

    result = []
    for sec in sections:
        for table in sec.find_all("table"):
            cap = table.find("caption")
            표이름 = cap.get_text(strip=True) if cap else ""
            result.extend(_parse_table(table, 대학명, 전형명, 표이름))

    return result
