"""전형일정 및 전형 요소별 반영비율을 파싱하여 고정 23열 dict 반환."""
import re
from bs4 import BeautifulSoup

COLUMNS = [
    "대학명", "전형명", "모집단위명",
    "원서접수_인터넷", "원서접수_현장",
    "대학별고사_논술등필답", "대학별고사_면접구술", "대학별고사_실기",
    "합격자발표일", "선발모형", "선발방법", "선발비율",
    "반영_학생부", "반영_수능", "반영_면접", "반영_논술", "반영_적성",
    "반영_1단계성적", "반영_실기", "반영_서류", "반영_기타", "기타내용",
]

# leaf 라벨 → COLUMNS 키 매핑 (표별로 '실기' 구분 필요해 별도 dict 사용)
_SCHED_LABEL_MAP = {
    "인터넷": "원서접수_인터넷",
    "현장": "원서접수_현장",
    "논술등필답": "대학별고사_논술등필답",
    "논술등 필답": "대학별고사_논술등필답",
    "면접구술": "대학별고사_면접구술",
    "실기": "대학별고사_실기",
    "합격자발표일": "합격자발표일",
}

_RATIO_LABEL_MAP = {
    "선발모형": "선발모형",
    "선발방법": "선발방법",
    "선발비율(%)": "선발비율",
    "선발비율": "선발비율",
    "학생부": "반영_학생부",
    "수능": "반영_수능",
    "면접": "반영_면접",
    "논술": "반영_논술",
    "적성": "반영_적성",
    "1단계성적": "반영_1단계성적",
    "실기": "반영_실기",
    "서류": "반영_서류",
    "기타": "반영_기타",
    "기타내용": "기타내용",
}


def _flatten_headers(table):
    """colspan/rowspan을 고려해 헤더 행들을 그리드로 평탄화 → leaf 라벨 순서 반환."""
    rows = table.find_all("tr")
    # 헤더행(th만 있는 행)과 데이터행 구분
    header_rows = []
    for tr in rows:
        ths = tr.find_all("th")
        tds = tr.find_all("td")
        if ths and not tds:
            header_rows.append(tr)
        elif ths and tds:
            # 헤더와 데이터 혼재 → 헤더로 취급 (없는 경우 대비)
            header_rows.append(tr)

    if not header_rows:
        return []

    # 그리드 구성: (row_idx, col_idx) → label
    max_col = 0
    grid = {}
    occupied = set()

    for row_idx, tr in enumerate(header_rows):
        col_idx = 0
        cells = tr.find_all(["th", "td"])
        for cell in cells:
            # 이미 점유된 셀 건너뜀
            while (row_idx, col_idx) in occupied:
                col_idx += 1
            cs = int(cell.get("colspan", 1))
            rs = int(cell.get("rowspan", 1))
            label = cell.get_text(strip=True)
            # 점유 등록
            for dr in range(rs):
                for dc in range(cs):
                    occupied.add((row_idx + dr, col_idx + dc))
                    if dr == 0 and dc == 0:
                        grid[(row_idx + dr, col_idx + dc)] = label
                    else:
                        grid.setdefault((row_idx + dr, col_idx + dc), label)
            col_idx += cs
            max_col = max(max_col, col_idx)

    # 마지막 헤더 행의 각 열에서 leaf label 추출
    last_row = max(r for r, c in grid) if grid else 0
    leaf_labels = []
    for c in range(max_col):
        label = grid.get((last_row, c), "")
        leaf_labels.append(label)
    return leaf_labels


def _extract_data_rows(table):
    """테이블에서 td만 있는 데이터 행의 셀 텍스트 목록 반환."""
    result = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        ths = tr.find_all("th")
        if tds and not ths:
            result.append([td.get_text(strip=True) for td in tds])
    return result


def _extract_mojipdan(soup):
    """div.selectionInfo에서 모집단위명 추출."""
    info = soup.find("div", class_="selectionInfo")
    if not info:
        return ""
    text = info.get_text(strip=True)
    # 패턴: '] <모집단위> / 대학'
    m = re.search(r'\]\s*(.+?)\s*/\s*\S+대학교', text)
    if m:
        return m.group(1).strip()
    return ""


def parse(html: str, 대학명: str = "", 전형명: str = "") -> list:
    """HTML을 파싱해 고정 23열 dict의 list 반환 (이 페이지는 보통 1행)."""
    soup = BeautifulSoup(html, "html.parser")
    row = {c: "" for c in COLUMNS}
    row["대학명"] = 대학명
    row["전형명"] = 전형명
    row["모집단위명"] = _extract_mojipdan(soup)

    tables = soup.find_all("table")
    for table in tables:
        cap = table.find("caption")
        if not cap:
            continue
        cap_text = cap.get_text(strip=True)

        if cap_text == "전형일정":
            leaf_labels = _flatten_headers(table)
            data_rows = _extract_data_rows(table)
            if data_rows:
                for label, val in zip(leaf_labels, data_rows[0]):
                    col_key = _SCHED_LABEL_MAP.get(label, "")
                    if col_key:
                        row[col_key] = val

        elif "전형 요소별 반영비율" in cap_text:
            leaf_labels = _flatten_headers(table)
            data_rows = _extract_data_rows(table)
            if data_rows:
                for label, val in zip(leaf_labels, data_rows[0]):
                    col_key = _RATIO_LABEL_MAP.get(label, "")
                    if col_key:
                        row[col_key] = val

    return [row]
