"""Writer: 표준 records → cell_mapping.yaml 따라 엑셀 템플릿에 입력."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
import yaml
import openpyxl

ROOT = Path("/Users/vibeon/Documents/무제 폴더")
TEMPLATE = Path("/Users/vibeon/Downloads/어디가입결_양식.xlsx")
MAPPING_YAML = ROOT / "cell_mapping.yaml"
MAPPED_DIR = ROOT / "out" / "mapped"
OUT_DIR = ROOT / "outputs"
BACKUP_DIR = OUT_DIR / ".backup"

UNV_NAME = {"0000069": "고려대학교", "0000070": "고려대학교(세종)"}


def _cast(value, kind: str):
    if value is None or value == "":
        return None
    if kind == "int":
        try: return int(float(str(value).replace(",", "")))
        except (TypeError, ValueError): return None
    if kind == "float":
        try: return float(str(value).replace(",", ""))
        except (TypeError, ValueError): return None
    if kind == "str":
        return str(value)
    return value  # passthrough


def _get_path(rec: dict, dotted: str):
    """records[i].converted_score.cut_70 → rec['converted_score']['cut_70']."""
    body = dotted.split(".", 1)[1] if "." in dotted else dotted
    cur = rec
    for part in body.split("."):
        if cur is None: return None
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def write(unv_cd: str) -> Path:
    mapped = json.loads((MAPPED_DIR / f"{unv_cd}.json").read_text(encoding="utf-8"))
    mapping = yaml.safe_load(MAPPING_YAML.read_text(encoding="utf-8"))
    records = mapped["records"]
    univ_name = mapped.get("univName") or UNV_NAME.get(unv_cd) or unv_cd

    # 정렬
    sort_keys = mapping.get("sort_order", [])
    records.sort(key=lambda r: tuple((r.get(k) or "") for k in sort_keys))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{unv_cd}.xlsx"
    if out_path.exists():
        bak = BACKUP_DIR / f"{unv_cd}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        shutil.move(str(out_path), str(bak))

    shutil.copy(str(TEMPLATE), str(out_path))
    wb = openpyxl.load_workbook(out_path)
    ws = wb[mapping["sheet"]]
    start = mapping["data_start_row"]
    cols = mapping["columns"]
    coerce = mapping.get("type_coercion", {})

    for i, rec in enumerate(records):
        row = start + i
        for col, path in cols.items():
            if path == "university.univName":
                val = univ_name
            elif path.startswith("records[i]"):
                val = _get_path(rec, path)
            else:
                val = None
            if val is None and mapping.get("null_policy") == "skip_write":
                continue
            kind = coerce.get(col, "passthrough")
            val = _cast(val, kind)
            if val is None: continue
            ws.cell(row=row, column=openpyxl.utils.column_index_from_string(col), value=val)

    wb.save(out_path)

    # 재독 검증
    wb2 = openpyxl.load_workbook(out_path)
    ws2 = wb2[mapping["sheet"]]
    sample_ok = True
    if records:
        first_unit = records[0].get("recruitment_unit")
        cell_c = ws2.cell(row=start, column=3).value  # C 컬럼
        if first_unit and str(cell_c) != str(first_unit):
            sample_ok = False
            print(f"  [WARN] readback mismatch: C{start} expected={first_unit!r}, got={cell_c!r}")

    print(f"  rows written: {len(records)}, readback_ok: {sample_ok}, file: {out_path}")
    return out_path


if __name__ == "__main__":
    import sys
    cd = sys.argv[1] if len(sys.argv) > 1 else "0000069"
    p = write(cd)
    print(f"[OK] wrote {p}")
