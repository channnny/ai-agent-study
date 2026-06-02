"""Validator: 매핑된 records가 raw에 존재하는 수치인지·범위가 맞는지 검증."""
from __future__ import annotations

import json
import re
from pathlib import Path

OUT_DIR = Path("/Users/vibeon/Documents/무제 폴더/out")
RAW_DIR = OUT_DIR / "raw"
MAPPED_DIR = OUT_DIR / "mapped"
REPORT_DIR = OUT_DIR / "reports"


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _normalize_num(v) -> str | None:
    if v is None or v == "":
        return None
    s = str(v).replace(",", "").strip()
    m = _NUM_RE.search(s)
    if not m:
        return None
    return f"{float(m.group()):.2f}"


def _collect_raw_numbers(raw: dict) -> set[str]:
    nums = set()
    for t in raw["tables"]:
        rows = t.get("data_rows") or t.get("rows") or []
        for row in rows:
            for cell in row:
                for m in _NUM_RE.findall(str(cell)):
                    nums.add(f"{float(m):.2f}")
    return nums


def _count_raw_data_rows(raw: dict) -> int:
    total = 0
    for t in raw["tables"]:
        rows = t.get("data_rows") or t.get("rows") or []
        flat_headers = t.get("flat_headers") or []
        if any(k in " ".join(flat_headers) for k in ("모집인원", "경쟁률", "충원합격순위")):
            total += len(rows)
    return total


def validate(unv_cd: str) -> dict:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    raw = json.loads((RAW_DIR / f"{unv_cd}.json").read_text(encoding="utf-8"))
    mapped = json.loads((MAPPED_DIR / f"{unv_cd}.json").read_text(encoding="utf-8"))

    raw_numbers = _collect_raw_numbers(raw)
    issues: list[dict] = []
    checked, matched = 0, 0

    for i, rec in enumerate(mapped["records"]):
        # 수치 일치성
        for path, val in _walk_numeric(rec):
            checked += 1
            norm = _normalize_num(val)
            if norm is None:
                continue
            if norm in raw_numbers:
                matched += 1
            else:
                issues.append({"record_idx": i, "path": path, "value": val, "kind": "number_not_in_raw"})

        # 범위 검사
        for path, val in _walk_numeric(rec, only_paths=("grade.",)):
            norm = _normalize_num(val)
            if norm is not None:
                f = float(norm)
                if not (1.0 <= f <= 9.0):
                    issues.append({"record_idx": i, "path": path, "value": val, "kind": "grade_out_of_range"})
        if rec.get("competition_ratio") is not None:
            try:
                cr = float(rec["competition_ratio"])
                if cr < 0 or cr > 1000:
                    issues.append({"record_idx": i, "path": "competition_ratio", "value": rec["competition_ratio"], "kind": "ratio_out_of_range"})
            except (TypeError, ValueError):
                issues.append({"record_idx": i, "path": "competition_ratio", "value": rec["competition_ratio"], "kind": "ratio_not_number"})

        # 필수: recruitment_unit
        if not rec.get("recruitment_unit"):
            issues.append({"record_idx": i, "path": "recruitment_unit", "value": None, "kind": "missing_required"})

    critical = [i for i in issues if i["kind"] in ("missing_required", "grade_out_of_range")]
    n_num_off = sum(1 for i in issues if i["kind"] == "number_not_in_raw")
    off_ratio = n_num_off / max(checked, 1)

    # v0.4 빈 산출 하드 가드 3종
    guards = []
    n_records = len(mapped["records"])
    raw_data_rows = _count_raw_data_rows(raw)
    if n_records == 0:
        guards.append("empty_records")
    if raw_data_rows >= 10 and n_records < raw_data_rows * 0.30:
        guards.append(f"too_few_records ({n_records} < {int(raw_data_rows * 0.30)} = raw_data_rows × 30%)")
    admission_types = {r.get("admission_type") for r in mapped["records"] if r.get("admission_type")}
    has_both_in_raw = any("학교추천" in (t.get("thead_label") or "") or "교과" in " ".join(t.get("flat_headers", [])) for t in raw["tables"])
    if has_both_in_raw and len(admission_types) < 2 and n_records > 0:
        guards.append(f"single_admission_type ({admission_types})")

    if guards:
        verdict = "REVIEW"
    elif critical or off_ratio > 0.20:
        verdict = "REVIEW" if off_ratio > 0.20 else "FAIL"
    else:
        verdict = "PASS"

    report = {
        "unvCd": unv_cd,
        "verdict": verdict,
        "summary": {
            "records": n_records,
            "raw_data_rows_estimate": raw_data_rows,
            "numeric_checked": checked,
            "numeric_matched": matched,
            "numeric_off_ratio": round(off_ratio, 4),
            "issue_count": len(issues),
        },
        "guards_triggered": guards,
        "issues": issues[:50],
    }
    (REPORT_DIR / f"{unv_cd}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def _walk_numeric(rec: dict, only_paths: tuple[str, ...] | None = None, prefix: str = ""):
    """record 내 모든 (path, numeric_value) 산출."""
    for k, v in rec.items():
        path = f"{prefix}{k}"
        if isinstance(v, dict):
            yield from _walk_numeric(v, only_paths, prefix=path + ".")
        elif isinstance(v, (int, float)):
            if only_paths and not any(path.startswith(p) for p in only_paths):
                continue
            yield path, v
        elif isinstance(v, str) and _NUM_RE.fullmatch(v.replace(",", "").strip()):
            if only_paths and not any(path.startswith(p) for p in only_paths):
                continue
            yield path, v


if __name__ == "__main__":
    import sys
    cd = sys.argv[1] if len(sys.argv) > 1 else "0000069"
    r = validate(cd)
    print(json.dumps(r["summary"], ensure_ascii=False, indent=2))
    print(f"verdict: {r['verdict']}")
