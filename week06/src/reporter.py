"""W06 리포트 작성.

W05와 같은 리포트 흐름을 유지하면서 통합 출처 요약과 통합 데이터 시트를
추가한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from week05.src.matcher import PersonResult  # noqa: E402
from week05.src.reporter import (  # noqa: E402
    _colorize_diff,
    _colorize_univ,
    _colorize_verdict,
    _highlight_dashboard,
    _style_glossary,
    _write_styled,
    build_by_column,
    build_by_university,
    build_diff_rows,
    build_mismatch,
    build_summary,
    build_uncovered,
)


def build_week06_glossary() -> pd.DataFrame:
    rows = [
        ("■ 이 리포트는?", "W05의 3인 크롤러 산출물(유찬·이지현·임지현)을 하나의 canonical 데이터셋으로 통합하고, 동일한 W05 평가 지표로 raw 3인과 통합본을 비교한 결과입니다."),
        ("", ""),
        ("■ 통합 원칙", "골든셋 값은 통합 데이터에 복사하지 않습니다. 골든셋은 평가에만 사용합니다."),
        ("셀 선택", "같은 PK·항목에 여러 소스가 값을 내면 W06 전략 비교에서 가장 높았던 유찬→임지현→이지현 순으로 선택합니다. 한 소스만 값이 있으면 누락 방지를 위해 그대로 채택합니다."),
        ("누락 방지", "한 소스만 값을 가진 셀은 그대로 채택합니다. 서로 다른 PK 행은 모두 보존해 extra가 늘 수 있지만 데이터 손실을 줄입니다."),
        ("", ""),
        ("■ 핵심 지표", "W05와 동일합니다."),
        ("커버리지", "골든 대학 중 데이터를 낸 대학 비율입니다. W06 목표는 가능한 100%에 가깝게 유지하는 것입니다."),
        ("셀 충진율", "매칭 행에서 양쪽 다 값이 있는 셀 비율입니다. 낮으면 크롤러가 항목을 덜 채웠다는 뜻입니다."),
        ("셀 일치율", "양쪽 다 값이 있는 셀 중 값이 일치한 비율입니다. W05의 최종 판정 기준입니다."),
        ("PK 매칭률", "대학·전형·모집단위가 같은 행 비율입니다. 전형명 표준화 이슈가 있어 참고 지표로 봅니다."),
        ("", ""),
        ("■ 추가 시트", "출처요약은 항목별로 어떤 소스 값이 얼마나 채택됐는지 보여줍니다. 통합데이터는 최종 canonical 행이며, 통합계보는 행·셀별 후보값과 채택 출처를 담습니다."),
    ]
    return pd.DataFrame(rows, columns=["항목", "설명"])


def write_week06_report(
    results: list[PersonResult],
    output_path: Path,
    source_summary: pd.DataFrame,
    integrated_df: pd.DataFrame,
    lineage_df: pd.DataFrame,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    glossary = build_week06_glossary()
    summary = build_summary(results)
    by_univ = build_by_university(results)
    by_col = build_by_column(results)
    uncovered = build_uncovered(results)
    diff = build_diff_rows(results)
    mismatched = build_mismatch(results)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        glossary.to_excel(writer, sheet_name="용어설명", index=False)
        _style_glossary(writer.sheets["용어설명"], glossary)

        _write_styled(
            writer,
            summary,
            "종합",
            "W05 raw 3인과 W06 통합본의 핵심 지표 비교. 통합본은 골든 값을 복사하지 않고 3개 크롤러 산출물만 병합했습니다.",
        )
        _highlight_dashboard(writer.sheets["종합"])

        _write_styled(
            writer,
            by_univ,
            "대학별",
            "대학별 raw 3인·통합본 비교. 통합본은 어느 한 소스라도 낸 행을 보존해 커버리지를 높입니다.",
        )
        _colorize_univ(writer.sheets["대학별"], by_univ)

        _write_styled(
            writer,
            by_col,
            "항목별",
            "데이터 항목별 셀 일치율. 통합본에서 낮은 항목은 소스 간 충돌 또는 파싱 규칙 보강 우선순위입니다.",
        )

        _write_styled(
            writer,
            source_summary,
            "출처요약",
            "통합 데이터의 항목별 채택 출처 카운트입니다. consensus=여러 소스가 같은 값, learned_priority=학습된 우선순위 기반 선택, empty=후보 없음입니다.",
        )

        _write_styled(
            writer,
            uncovered,
            "미수집대학",
            "한 명이라도 못 낸 대학과 통합본 미수집 여부입니다.",
        )

        _write_styled(
            writer,
            diff,
            "누락·잉여",
            "골든과 비교해 한쪽에만 있는 PK 행입니다. 통합본은 데이터 손실을 줄이기 위해 extra 행을 보존할 수 있습니다.",
        )
        _colorize_diff(writer.sheets["누락·잉여"], diff)

        _write_styled(
            writer,
            mismatched,
            "불일치셀",
            "PK는 맞았지만 값이 다른 셀입니다. 통합본의 남은 실제 오류를 위에서부터 확인하면 됩니다.",
        )
        _colorize_verdict(writer.sheets["불일치셀"], mismatched)

        _write_styled(
            writer,
            integrated_df,
            "통합데이터",
            "W06 통합 canonical 데이터셋입니다. 컬럼은 W05 평가 스키마와 동일합니다.",
        )

        # Excel 시트명 제한 때문에 lineage는 가장 마지막에 짧은 이름으로 둔다.
        lineage_sample = lineage_df
        if len(lineage_sample) > 50000:
            lineage_sample = lineage_sample.head(50000).copy()
            lineage_sample["주의"] = "lineage가 50,000행을 넘어 앞부분만 리포트에 포함됨"
        _write_styled(
            writer,
            lineage_sample,
            "통합계보",
            "행·셀별 후보값, 채택 출처, 충돌 항목입니다. 통합 데이터의 추적성을 위해 제공합니다.",
        )


def write_integrated_dataset(
    integrated_df: pd.DataFrame,
    lineage_df: pd.DataFrame,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        integrated_df.to_excel(writer, sheet_name="canonical", index=False)
        lineage_df.to_excel(writer, sheet_name="lineage", index=False)
