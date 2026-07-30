"""Diagnose P0 data readiness without blocking modeling on optional snapshots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
RESULTS_DIR = REPO_ROOT / "results"
WARNINGS_PATH = RESULTS_DIR / "data_warnings.json"
CUTOFF = pd.Timestamp("2026-06-30")
SUCCESS_STATUSES = {"DOWNLOADED", "CACHED"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_issue(
    bucket: list[dict[str, Any]],
    code: str,
    message: str,
    path: Path | None = None,
) -> None:
    row: dict[str, Any] = {"code": code, "message": message}
    if path is not None:
        row["path"] = path.relative_to(REPO_ROOT).as_posix()
    bucket.append(row)


def read_csv_checked(path: Path, errors: list[dict[str, Any]], **kwargs: Any) -> pd.DataFrame:
    try:
        return pd.read_csv(path, **kwargs)
    except Exception as exc:
        add_issue(errors, "parse_failed", f"{path.name}: {exc}", path)
        return pd.DataFrame()


def check_no_duplicate(frame: pd.DataFrame, keys: list[str], name: str, errors: list[dict[str, Any]]) -> None:
    missing = [key for key in keys if key not in frame.columns]
    if missing:
        add_issue(errors, "missing_key_columns", f"{name} missing key columns {missing}")
        return
    duplicated = int(frame.duplicated(keys).sum())
    if duplicated:
        add_issue(errors, "duplicate_keys", f"{name} has {duplicated} duplicated keys: {keys}")


def check_cutoff(
    values: pd.Series,
    name: str,
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    dates = pd.to_datetime(values, errors="coerce")
    if dates.isna().any():
        add_issue(warnings, "date_parse_warning", f"{name} has {int(dates.isna().sum())} unparsable dates")
    max_date = dates.max()
    if pd.notna(max_date) and max_date > CUTOFF:
        add_issue(errors, "cutoff_violation", f"{name} max date {max_date.date()} exceeds 2026-06-30")


def check_finite(frame: pd.DataFrame, columns: list[str], name: str, errors: list[dict[str, Any]]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        add_issue(errors, "missing_core_columns", f"{name} missing core columns {missing}")
        return
    numeric = frame[columns].apply(pd.to_numeric, errors="coerce")
    bad = int((~np.isfinite(numeric.to_numpy(dtype=float))).sum())
    if bad:
        add_issue(errors, "nonfinite_core_values", f"{name} has {bad} non-finite core numeric cells")


def validate_raw_manifest(warnings: list[dict[str, Any]], errors: list[dict[str, Any]]) -> None:
    manifest_path = RAW_DIR / "source_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        add_issue(errors, "manifest_parse_failed", f"source_manifest.json: {exc}", manifest_path)
        return

    if len(manifest) != 21:
        add_issue(warnings, "manifest_record_count", f"expected 21 source records, got {len(manifest)}", manifest_path)

    for record in manifest:
        artifact_id = record.get("artifact_id", "<unknown>")
        status = record.get("status", "")
        if status not in SUCCESS_STATUSES:
            add_issue(warnings, "manifest_status", f"{artifact_id} status={status}")
        local_path = record.get("local_path", "")
        path = REPO_ROOT / local_path
        if not path.exists():
            add_issue(warnings, "missing_raw_snapshot", f"{artifact_id} raw snapshot is absent", path)
            continue
        expected_hash = record.get("sha256")
        if expected_hash:
            actual_hash = sha256_file(path)
            if actual_hash != expected_hash:
                add_issue(
                    warnings,
                    "raw_hash_mismatch",
                    f"{artifact_id} SHA-256 mismatch; likely line-ending or refreshed snapshot drift",
                    path,
                )


def validate_processed(warnings: list[dict[str, Any]], errors: list[dict[str, Any]]) -> list[str]:
    checks: list[str] = []

    monthly = read_csv_checked(PROCESSED_DIR / "p0_monthly_market.csv", errors)
    if not monthly.empty:
        check_no_duplicate(monthly, ["period"], "p0_monthly_market", errors)
        if "month_end" in monthly.columns:
            check_cutoff(monthly["month_end"], "p0_monthly_market.month_end", errors, warnings)
        check_finite(
            monthly,
            ["brent_usd_bbl", "us_crude_stock_month_end_kbbl", "usd_broad_index", "GPR", "cny_per_usd"],
            "p0_monthly_market",
            errors,
        )
        checks.append(f"p0_monthly_market rows={len(monthly)}")

    daily = read_csv_checked(PROCESSED_DIR / "p0_daily_market.csv", errors)
    if not daily.empty:
        check_no_duplicate(daily, ["date"], "p0_daily_market", errors)
        if "date" in daily.columns:
            check_cutoff(daily["date"], "p0_daily_market.date", errors, warnings)
        checks.append(f"p0_daily_market rows={len(daily)}")

    cpi = read_csv_checked(PROCESSED_DIR / "oecd_g20_cpi_monthly.csv", errors)
    if not cpi.empty:
        check_no_duplicate(cpi, ["REF_AREA", "TIME_PERIOD"], "oecd_g20_cpi_monthly", errors)
        if "TIME_PERIOD" in cpi.columns:
            check_cutoff(cpi["TIME_PERIOD"].astype(str) + "-01", "oecd_g20_cpi_monthly.TIME_PERIOD", errors, warnings)
        checks.append(f"oecd_g20_cpi_monthly rows={len(cpi)}")

    ip = read_csv_checked(PROCESSED_DIR / "oecd_kei_ip_monthly.csv", errors)
    if not ip.empty:
        check_no_duplicate(ip, ["REF_AREA", "TIME_PERIOD"], "oecd_kei_ip_monthly", errors)
        if "TIME_PERIOD" in ip.columns:
            check_cutoff(ip["TIME_PERIOD"].astype(str) + "-01", "oecd_kei_ip_monthly.TIME_PERIOD", errors, warnings)
        checks.append(f"oecd_kei_ip_monthly rows={len(ip)}")

    for filename, key in [
        ("germany_eurosuper95_monthly.csv", ["period"]),
        ("japan_regular_gasoline_monthly.csv", ["period"]),
        ("korea_regular_gasoline_monthly.csv", ["period"]),
        ("cn_fuel_policy_events.csv", ["effective_date"]),
    ]:
        frame = read_csv_checked(PROCESSED_DIR / filename, errors)
        if frame.empty:
            continue
        check_no_duplicate(frame, key, filename, errors)
        date_col = "effective_date" if "effective_date" in frame.columns else "month_end"
        if date_col in frame.columns:
            check_cutoff(frame[date_col], f"{filename}.{date_col}", errors, warnings)
        checks.append(f"{filename} rows={len(frame)}")

    return checks


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    validate_raw_manifest(warnings, errors)
    checks = validate_processed(warnings, errors)

    result = {
        "status": "FAIL" if errors else ("WARN" if warnings else "PASS"),
        "cutoff": CUTOFF.strftime("%Y-%m-%d"),
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }
    WARNINGS_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
