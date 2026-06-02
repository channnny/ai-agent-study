"""Mapper: 평면화된 표 → 사전 우선 매칭 → 미해결만 LLM (재시도·격리)."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import yaml

ROOT = Path("/Users/vibeon/Documents/무제 폴더")
OUT_DIR = ROOT / "out"
RAW_DIR = OUT_DIR / "raw"
MAPPED_DIR = OUT_DIR / "mapped"
DICT_PATH = ROOT / "mapping_dictionary.yaml"
MODEL = "claude-sonnet-4-6"
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _norm(s: str) -> str:
    """공백·% 제거 + 소문자. 컷 표기 변형(50% cut / 50 cut / 50%cut)을 통일."""
    return re.sub(r"[\s%]+", "", str(s or "")).lower()


def _cell(v) -> str:
    return "" if v is None else str(v)


def _is_candidate(table: dict, dictionary: dict) -> bool:
    cfg = dictionary["candidate_keywords"]
    headers_blob = " ".join(_cell(h) for h in table["flat_headers"])
    rows_blob = " ".join(" ".join(_cell(c) for c in r) for r in table["data_rows"][:2])
    blob = headers_blob + " " + rows_blob
    return sum(1 for k in cfg["keywords"] if k in blob) >= cfg["required_min_count"] \
        and table["data_row_count"] >= 1  # SW우수자 등 1개 모집단위 전형도 포함


# 입결이 아닌 표를 걸러내는 신호
_REJECT_SIGNALS = [
    "총점(수능)", "백분위", "수학 선택", "선택과목응시", "선발방법",
    "전형요소 및 반영비율", "수능영역별", "정시모집요강",
]
_DISTRIBUTION_SIGNAL = "지원자 분포도"


def _clean_label(label: str) -> str:
    """전형명 부가설명 괄호 제거: '특성화고교 전형(2026학년도부터...)' → '특성화고교 전형'.
    주의: '선발'·'반영'은 전형명 자체에 흔하므로(기회균형선발전형) 트리거에서 제외."""
    s = _cell(label).strip()
    s = re.sub(r"\((?=[^)]*(?:학년도|:|\d{4}|배수))[^)]*\)", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _classify_admission(table: dict, dictionary: dict | None = None) -> str | None:
    """종합/교과 판별. None이면 입결 표 아님(정시·전형방법·분포도)."""
    label = _cell(table.get("thead_label"))
    headers = " ".join(_cell(h) for h in table["flat_headers"])
    blob = label + " " + headers
    nb = _norm(blob)

    if any(_norm(sig) in nb for sig in _REJECT_SIGNALS):
        return None

    # thead에 대분류 명시
    if "학생부종합" in blob or "종합)" in blob:
        return "학생부종합"
    if "학생부교과" in blob or "교과)" in blob:
        return "학생부교과"

    # 헤더 휴리스틱
    has_eval = ("평가에반영" in nb) or ("반영된교과" in nb)
    has_distribution = _DISTRIBUTION_SIGNAL in blob  # 분포도는 종합 특징
    has_hwansan = ("환산" in nb) or ("총점(학생부)" in nb)
    has_grade = ("학생부등급" in nb) or ("교과성적" in nb and "등급" in nb)

    if has_eval or has_distribution:
        return "학생부종합"
    if has_hwansan:
        return "학생부교과"
    if has_grade:
        return "학생부교과"  # 환산·평가반영 없이 등급만 → 교과 추정 (동국대 학교장추천)
    return None


_CUT_RE = re.compile(r"(\d+)\s*%?\s*cut", re.IGNORECASE)


def _match_column(header: str, dictionary: dict | None = None) -> str | None:
    """평면화 헤더 → 표준 필드. 규칙 기반(컷 번호 정규식)으로 표기 변형 흡수."""
    h = _cell(header)
    if not h:
        return None
    nh = _norm(h)

    if "모집단위" in nh and "코드" not in nh:
        return "recruitment_unit"
    if "모집인원" in nh or ("모집" in nh and "인원" in nh):
        if "최초" in nh or "이월" in nh:
            return None
        return "quota"
    if "경쟁률" in nh:
        return "competition_ratio"
    if "충원" in nh:
        return "fill_rank"
    if "평가에반영" in nh or "반영된교과" in nh or "반영교과" in nh:
        return "reflected_subjects"

    is_hwansan = "환산" in nh
    is_grade = ("학생부등급" in nh) or ("교과성적" in nh and "등급" in nh)
    cut_m = _CUT_RE.search(h)
    cutnum = cut_m.group(1) if cut_m else None

    if is_hwansan:
        if "총점" in nh:
            return "converted_score.total"
        if cutnum in ("50", "70", "80", "100"):
            return f"converted_score.cut_{cutnum}"
        if "평균" in nh:
            return "converted_score.avg"
        if "최고" in nh:
            return "converted_score.max"
    if is_grade:
        if cutnum in ("50", "70", "80", "90"):
            return f"grade.cut_{cutnum}"
        if "평균" in nh:
            return "grade.avg"
        if "최고" in nh:
            return "grade.max"
        if "최저" in nh:
            return "grade.min"
    return None


def _parse_num(v, strict: bool = False):
    """문자열→숫자. strict=True면 한글이 섞인 셀(예: '선발인원 3명 이하 공개')은 None.
    relaxed면 한글 3자 미만('6이내')까지만 허용."""
    if v is None or v == "":
        return None
    s = str(v).replace(",", "").strip()
    if s in ("-", "—", "N/A", "비공개", ""):
        return None
    hangul = len(re.findall(r"[가-힣]", s))
    if strict and hangul > 0:
        return None
    if hangul >= 3:  # '선발인원 N명 이하 모집단위 전형별 공개' 등 안내 문구 차단
        return None
    m = NUM_RE.search(s)
    if not m:
        return None
    try:
        f = float(m.group())
        return int(f) if f.is_integer() else f
    except ValueError:
        return None


def _empty_record(year: int, admission_type: str, admission_name: str | None = None) -> dict:
    return {
        "result_year": year,
        "admission_type": admission_type,
        "admission_name": admission_name or admission_type,
        "recruitment_unit": None,
        "quota": None,
        "competition_ratio": None,
        "fill_rank": None,
        "converted_score": {"max": None, "avg": None, "cut_50": None, "cut_70": None, "cut_80": None, "cut_100": None, "total": None},
        "grade": {"max": None, "avg": None, "cut_50": None, "cut_70": None, "cut_80": None, "cut_90": None, "min": None},
        "criteria": None,
        "reflected_subjects": None,
    }


def _set_path(rec: dict, path: str, value):
    """'grade.cut_70' → rec['grade']['cut_70'] = value"""
    parts = path.split(".")
    cur = rec
    for p in parts[:-1]:
        cur = cur[p]
    leaf = parts[-1]
    if leaf in ("quota",):
        cur[leaf] = _parse_num(value, strict=False) if value is not None else None  # '6이내' → 6
        if cur[leaf] is not None:
            cur[leaf] = int(cur[leaf]) if isinstance(cur[leaf], (int, float)) else cur[leaf]
    elif leaf in ("recruitment_unit", "fill_rank", "reflected_subjects", "criteria"):
        cur[leaf] = str(value).strip() if value is not None and str(value).strip() else None
    else:
        # 등급·환산·경쟁률은 순수 숫자만 (안내 문구의 숫자 추출 방지). 0은 미공개 → 결측
        n = _parse_num(value, strict=True)
        if path.startswith(("grade.", "converted_score.")) and n == 0:
            n = None
        cur[leaf] = n


def _build_admission_name(admission_type: str, thead_label: str) -> str:
    """세부 전형명. thead에 대분류가 이미 있으면 정리만, 없으면 '{type}({label})'."""
    label = _clean_label(thead_label)
    if not label or label == "모집단위":
        return admission_type
    if "학생부종합" in label or "학생부교과" in label:
        return label  # 이미 대분류 포함 (건국대·경기대·영남대·동국대)
    return f"{admission_type}({label})"


def _detect_criteria(table: dict) -> str | None:
    """헤더에 '최종등록자'가 있으면 기준='최종등록자'."""
    blob = " ".join(_cell(h) for h in table["flat_headers"])
    return "최종등록자" if "최종등록자" in blob else None


def _map_table_dict(table: dict, dictionary: dict, result_year: int) -> tuple[list[dict], dict]:
    """사전 매칭으로 한 표 → records 리스트. (records, report) 반환."""
    admission_type = _classify_admission(table, dictionary)
    if not admission_type:
        return [], {"reason": "admission_type 추론 실패", "thead_label": table.get("thead_label", "")}
    admission_name = _build_admission_name(admission_type, table.get("thead_label", ""))
    criteria = _detect_criteria(table)

    col_map: dict[int, str] = {}
    unmatched: list[tuple[int, str]] = []
    for ci, h in enumerate(table["flat_headers"]):
        h_str = _cell(h)
        if not h_str:
            continue
        field = _match_column(h_str, dictionary)
        if field:
            col_map[ci] = field
        else:
            unmatched.append((ci, h_str))

    if "recruitment_unit" not in col_map.values():
        return [], {"reason": "recruitment_unit 컬럼을 찾지 못함", "headers": [_cell(h) for h in table["flat_headers"][:10]]}

    records = []
    for row in table["data_rows"]:
        row_cells = [_cell(c) for c in row]
        if not any(c.strip() for c in row_cells):
            continue
        rec = _empty_record(result_year, admission_type, admission_name)
        rec["criteria"] = criteria
        for ci, field in col_map.items():
            if ci < len(row_cells):
                _set_path(rec, field, row_cells[ci])
        if rec.get("recruitment_unit"):
            records.append(rec)

    return records, {
        "admission_type": admission_type,
        "thead_label": table.get("thead_label", ""),
        "matched_columns": {f"col{ci}": (table["flat_headers"][ci], field) for ci, field in col_map.items()},
        "unmatched_headers": unmatched,
        "records": len(records),
    }


def _call_llm_with_retry(client, table, attempt_max=3):
    """LLM fallback (사전으로 못 푼 표만). 인증·잔액 오류는 즉시 예외."""
    from anthropic import APIStatusError, AuthenticationError
    sys_prompt = (
        "이 표를 입시결과 records로 변환하라. JSON만 반환:"
        '{"records":[{"admission_type":..,"recruitment_unit":..,...}],"confidence":0.0~1.0}'
    )
    msg = json.dumps({"flat_headers": table["flat_headers"], "thead_label": table.get("thead_label"), "data_rows": table["data_rows"][:25]}, ensure_ascii=False)
    delay = 1
    last_err = None
    for attempt in range(attempt_max):
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=4000, system=sys_prompt,
                messages=[{"role": "user", "content": msg}],
            )
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```", 2)[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except AuthenticationError as e:
            raise
        except APIStatusError as e:
            msg_lower = str(e).lower()
            if "credit balance" in msg_lower or "billing" in msg_lower:
                raise RuntimeError(f"CREDIT_EXHAUSTED: {e}")
            if e.status_code in (429, 500, 502, 503, 504):
                time.sleep(delay); delay *= 4; last_err = e; continue
            raise
        except Exception as e:
            last_err = e
            time.sleep(delay); delay *= 4
    raise RuntimeError(f"LLM retry exhausted: {last_err}")


def _merge_records(records: list[dict]) -> list[dict]:
    """(전형명, 모집단위) 키로 record 병합. 분포도 표·컷 표가 분리된 경우 합침."""
    merged: dict[tuple, dict] = {}
    order: list[tuple] = []
    for rec in records:
        key = (rec.get("admission_name"), rec.get("recruitment_unit"))
        if key not in merged:
            merged[key] = rec
            order.append(key)
        else:
            tgt = merged[key]
            for f, v in rec.items():
                if isinstance(v, dict):
                    for sub, sv in v.items():
                        if tgt[f].get(sub) is None and sv is not None:
                            tgt[f][sub] = sv
                elif tgt.get(f) is None and v is not None:
                    tgt[f] = v
    return [merged[k] for k in order]


def map_raw(unv_cd: str) -> dict:
    _load_dotenv()
    MAPPED_DIR.mkdir(parents=True, exist_ok=True)
    raw = json.loads((RAW_DIR / f"{unv_cd}.json").read_text(encoding="utf-8"))
    dictionary = yaml.safe_load(DICT_PATH.read_text(encoding="utf-8"))

    page_year = raw.get("year", 2027)
    result_year = page_year - 1  # POC 정책: 직전 학년도

    candidates = [t for t in raw["tables"] if _is_candidate(t, dictionary)]

    all_records: list[dict] = []
    table_reports = []
    llm_attempted = 0
    llm_failed = 0
    llm_disabled_reason = None

    client = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        except Exception as e:
            llm_disabled_reason = f"anthropic init: {e}"

    for t in candidates:
        recs, rep = _map_table_dict(t, dictionary, result_year)
        rep["idx"] = t["idx"]
        rep["source"] = "dict"
        if recs:
            all_records.extend(recs)
        elif client and not llm_disabled_reason:
            llm_attempted += 1
            try:
                llm_res = _call_llm_with_retry(client, t)
                llm_recs = llm_res.get("records", [])
                for r in llm_recs:
                    base = _empty_record(result_year, r.get("admission_type", "학생부종합"))
                    base.update({k: v for k, v in r.items() if k in base and not isinstance(base[k], dict)})
                    for sub in ("converted_score", "grade"):
                        if isinstance(r.get(sub), dict):
                            base[sub].update({k: v for k, v in r[sub].items() if k in base[sub]})
                    all_records.append(base)
                rep["source"] = "llm"
                rep["records"] = len(llm_recs)
            except Exception as e:
                llm_failed += 1
                err_msg = str(e).lower()
                err_type = type(e).__name__
                rep["llm_error"] = err_type
                # Fatal: 재시도해도 의미 없는 에러는 즉시 LLM 비활성화
                if (
                    "credit balance" in err_msg
                    or "billing" in err_msg
                    or "authentication" in err_msg
                    or err_type in ("AuthenticationError", "PermissionDeniedError", "NotFoundError")
                ):
                    llm_disabled_reason = err_type
                    print(f"    [{err_type}] LLM fallback 비활성화. 이후 표는 dict 결과만 사용.")
        table_reports.append(rep)

    all_records = _merge_records(all_records)
    fail_ratio = llm_failed / max(llm_attempted, 1) if llm_attempted else 0.0
    out = {
        "unvCd": unv_cd,
        "univName": raw.get("univName", ""),
        "page_year": page_year,
        "result_year": result_year,
        "records": all_records,
        "meta": {
            "candidate_table_count": len(candidates),
            "llm_attempted": llm_attempted,
            "llm_failed": llm_failed,
            "llm_fail_ratio": fail_ratio,
            "llm_disabled_reason": llm_disabled_reason,
            "mode": "dict_only" if not client or llm_disabled_reason else "dict_first_llm_fallback",
            "table_reports": table_reports,
        },
    }
    (MAPPED_DIR / f"{unv_cd}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    import sys
    cd = sys.argv[1] if len(sys.argv) > 1 else "0000069"
    res = map_raw(cd)
    print(f"[OK] {cd}: {len(res['records'])} records, mode={res['meta']['mode']}")
