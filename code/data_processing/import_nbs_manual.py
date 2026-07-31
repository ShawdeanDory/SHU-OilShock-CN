"""Import manually exported NBS monthly CSV files into the processed layer.

The NBS download format is a wide table with months in reverse chronological
order.  This importer preserves official missing observations, converts the
PPI year-on-year index (same month of previous year = 100) to a percentage
change, and writes tidy monthly files used by the Q2 pipeline.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
SOURCE_URL = "https://data.stats.gov.cn/dg/website/page.html#/pc/national/monthData"
START_PERIOD = "2010-01"
END_PERIOD = "2026-06"
EXPECTED_MONTHS = len(pd.period_range(START_PERIOD, END_PERIOD, freq="M"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_cell(value: str) -> str:
    return value.replace("\ufeff", "").replace("\t", "").strip()


def read_nbs_wide(path: Path) -> tuple[str, list[str], dict[str, list[str]]]:
    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            cleaned = [clean_cell(value) for value in row]
            while cleaned and cleaned[-1] == "":
                cleaned.pop()
            rows.append(cleaned)

    period_label = next((row[0] for row in rows if row and row[0].startswith("时间：")), "")
    header_index = next((index for index, row in enumerate(rows) if row and row[0] == "指标"), None)
    if header_index is None:
        raise ValueError(f"{path.name}: cannot find the NBS indicator header")

    months = rows[header_index][1:]
    if len(months) != EXPECTED_MONTHS:
        raise ValueError(f"{path.name}: expected {EXPECTED_MONTHS} months, found {len(months)}")

    indicators: dict[str, list[str]] = {}
    for row in rows[header_index + 1 :]:
        if not row or row[0].startswith("注：") or row[0].startswith("数据来源："):
            break
        values = row[1:]
        if len(values) < len(months):
            values.extend([""] * (len(months) - len(values)))
        indicators[row[0]] = values[: len(months)]
    return period_label, months, indicators


def parse_month(value: str) -> str:
    match = re.fullmatch(r"(\d{4})年(\d{1,2})月", value)
    if not match:
        raise ValueError(f"unrecognized month label: {value!r}")
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"


def numeric(values: list[str]) -> pd.Series:
    return pd.to_numeric(pd.Series(values, dtype="object").replace("", np.nan), errors="coerce")


def find_indicator(indicators: dict[str, list[str]], required: list[str], excluded: list[str] | None = None) -> tuple[str, list[str]]:
    excluded = excluded or []
    matches = [
        (label, values)
        for label, values in indicators.items()
        if all(token in label for token in required) and not any(token in label for token in excluded)
    ]
    if len(matches) != 1:
        labels = sorted(indicators)
        raise ValueError(f"expected one indicator matching {required}, found {len(matches)}; available={labels}")
    return matches[0]


def validate_periods(frame: pd.DataFrame, label: str) -> None:
    if frame["period"].duplicated().any():
        raise ValueError(f"{label}: duplicate periods")
    expected = pd.period_range(START_PERIOD, END_PERIOD, freq="M").astype(str).tolist()
    actual = frame["period"].tolist()
    if actual != expected:
        raise ValueError(f"{label}: period coverage does not equal {START_PERIOD}..{END_PERIOD}")


def import_ppi(path: Path, download_date: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    period_label, months, indicators = read_nbs_wide(path)
    indicator, values = find_indicator(
        indicators,
        required=["工业生产者出厂价格指数", "上年同月=100"],
        excluded=["生产资料", "生活资料", "分行业", "中类", "按工业部门"],
    )
    index_values = numeric(values)
    frame = pd.DataFrame(
        {
            "period": [parse_month(value) for value in months],
            "china_ppi_index_yoy_100": index_values,
            "china_ppi_yoy_pct": (index_values - 100.0).round(10),
        }
    ).sort_values("period", ignore_index=True)
    validate_periods(frame, "PPI")
    if frame["china_ppi_yoy_pct"].isna().any():
        missing = frame.loc[frame["china_ppi_yoy_pct"].isna(), "period"].tolist()
        raise ValueError(f"PPI: unexpected missing months: {missing}")

    raw_hash = sha256_file(path)
    frame["source_indicator"] = indicator
    frame["source_url"] = SOURCE_URL
    frame["download_date"] = download_date
    frame["raw_sha256"] = raw_hash
    metadata = {
        "source": "National Bureau of Statistics of China, National Data",
        "source_url": SOURCE_URL,
        "download_date": download_date,
        "raw_file": path.name,
        "raw_sha256": raw_hash,
        "period_label": period_label,
        "indicator": indicator,
        "calendar_months": int(len(frame)),
        "nonmissing_observations": int(frame["china_ppi_yoy_pct"].notna().sum()),
        "transformation": "china_ppi_yoy_pct = china_ppi_index_yoy_100 - 100",
    }
    return frame, metadata


def import_iav(path: Path, download_date: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    period_label, months, indicators = read_nbs_wide(path)
    indicator, values = find_indicator(indicators, required=["规上工业增加值同比增长"])
    cumulative_matches = [
        (label, row_values)
        for label, row_values in indicators.items()
        if "规上工业增加值累计增长" in label
    ]
    yoy_values = numeric(values)
    cumulative_values = numeric(cumulative_matches[0][1]) if len(cumulative_matches) == 1 else pd.Series(np.nan, index=range(len(months)))
    frame = pd.DataFrame(
        {
            "period": [parse_month(value) for value in months],
            "china_iav_yoy_pct": yoy_values,
            "china_iav_cumulative_yoy_pct": cumulative_values,
        }
    ).sort_values("period", ignore_index=True)
    validate_periods(frame, "IAV")

    missing = frame.loc[frame["china_iav_yoy_pct"].isna(), "period"].tolist()
    unexpected = [
        period
        for period in missing
        if not (
            period.endswith("-01")
            or (period >= "2013-02" and period.endswith("-02"))
        )
    ]
    if unexpected:
        raise ValueError(f"IAV: missing observations outside the official January/February pattern: {unexpected}")
    if frame["china_iav_yoy_pct"].notna().sum() < 120:
        raise ValueError("IAV: fewer than 120 nonmissing monthly observations")

    frame["observation_status"] = np.where(
        frame["china_iav_yoy_pct"].notna(),
        "observed",
        "official_calendar_gap_no_interpolation",
    )
    raw_hash = sha256_file(path)
    frame["source_indicator"] = indicator
    frame["source_url"] = SOURCE_URL
    frame["download_date"] = download_date
    frame["raw_sha256"] = raw_hash
    metadata = {
        "source": "National Bureau of Statistics of China, National Data",
        "source_url": SOURCE_URL,
        "download_date": download_date,
        "raw_file": path.name,
        "raw_sha256": raw_hash,
        "period_label": period_label,
        "indicator": indicator,
        "calendar_months": int(len(frame)),
        "nonmissing_observations": int(frame["china_iav_yoy_pct"].notna().sum()),
        "official_missing_months": missing,
        "missing_value_policy": "preserve official January/February gaps; no interpolation",
    }
    return frame, metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ppi", type=Path, required=True, help="NBS PPI wide CSV export")
    parser.add_argument("--iav", type=Path, required=True, help="NBS industrial value-added wide CSV export")
    parser.add_argument("--download-date", default=date.today().isoformat())
    args = parser.parse_args()

    ppi, ppi_meta = import_ppi(args.ppi.resolve(), args.download_date)
    iav, iav_meta = import_iav(args.iav.resolve(), args.download_date)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ppi.to_csv(PROCESSED_DIR / "nbs_ppi_monthly.csv", index=False, encoding="utf-8", lineterminator="\n")
    iav.to_csv(PROCESSED_DIR / "nbs_iav_monthly.csv", index=False, encoding="utf-8", lineterminator="\n")

    metadata = {
        "schema_version": "1.0",
        "cutoff": END_PERIOD,
        "ppi": ppi_meta,
        "iav": iav_meta,
    }
    (PROCESSED_DIR / "nbs_manual_import_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "ppi_rows": int(len(ppi)),
                "ppi_nonmissing": int(ppi["china_ppi_yoy_pct"].notna().sum()),
                "iav_rows": int(len(iav)),
                "iav_nonmissing": int(iav["china_iav_yoy_pct"].notna().sum()),
                "iav_official_gaps": int(iav["china_iav_yoy_pct"].isna().sum()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
