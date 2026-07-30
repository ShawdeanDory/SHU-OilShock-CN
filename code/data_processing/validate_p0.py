"""Validate P0 source hashes, coverage, keys, cutoffs and derived values."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
SUCCESS_STATUSES = {"DOWNLOADED", "CACHED"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    checks: list[str] = []
    manifest = json.loads(
        (RAW_DIR / "source_manifest.json").read_text(encoding="utf-8")
    )
    require(len(manifest) == 21, f"expected 21 source records, got {len(manifest)}")
    for record in manifest:
        require(
            record["status"] in SUCCESS_STATUSES,
            f"{record['artifact_id']} status={record['status']}",
        )
        path = REPO_ROOT / record["local_path"]
        require(path.exists(), f"missing raw file {path}")
        require(
            sha256_file(path) == record["sha256"],
            f"SHA-256 mismatch for {record['artifact_id']}",
        )
    checks.append("21 source snapshots exist and SHA-256 values match")

    monthly = pd.read_csv(
        PROCESSED_DIR / "p0_monthly_market.csv", parse_dates=["month_end"]
    )
    require(len(monthly) == 198, f"monthly rows={len(monthly)}")
    require(monthly["period"].iloc[0] == "2010-01", "monthly start mismatch")
    require(monthly["period"].iloc[-1] == "2026-06", "monthly end mismatch")
    require(monthly["period"].is_unique, "monthly period is not unique")
    core_columns = [
        "brent_usd_bbl",
        "us_crude_stock_month_end_kbbl",
        "usd_broad_index",
        "GPR",
    ]
    require(not monthly[core_columns].isna().any().any(), "core monthly data have gaps")
    product = monthly["brent_usd_bbl"] * monthly["cny_per_usd"]
    require(
        all(
            math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-10)
            for left, right in zip(product, monthly["brent_cny_per_bbl"], strict=True)
        ),
        "Brent CNY conversion mismatch",
    )
    checks.append("monthly market panel has 198 unique complete core months")

    cpi = pd.read_csv(PROCESSED_DIR / "oecd_g20_cpi_monthly.csv")
    cpi_counts = cpi.groupby("REF_AREA")["TIME_PERIOD"].count().to_dict()
    require(
        cpi_counts == {"CHN": 198, "DEU": 198, "JPN": 198, "KOR": 198},
        f"unexpected CPI counts {cpi_counts}",
    )
    require(
        not cpi.duplicated(["REF_AREA", "TIME_PERIOD"]).any(),
        "duplicate OECD CPI keys",
    )
    checks.append("OECD CPI has 198 observations for each of four countries")

    ip = pd.read_csv(PROCESSED_DIR / "oecd_kei_ip_monthly.csv")
    ip_counts = ip.groupby("REF_AREA")["TIME_PERIOD"].count().to_dict()
    require(
        ip_counts == {"DEU": 197, "JPN": 197, "KOR": 197},
        f"unexpected IP counts {ip_counts}",
    )
    require(
        not ip.duplicated(["REF_AREA", "TIME_PERIOD"]).any(),
        "duplicate OECD IP keys",
    )
    checks.append("OECD industrial production has 197 observations for each control")

    germany = pd.read_csv(
        PROCESSED_DIR / "germany_eurosuper95_monthly.csv",
        parse_dates=["month_end"],
    )
    require(len(germany) == 198, f"Germany monthly rows={len(germany)}")
    require(germany["period"].is_unique, "Germany period is not unique")
    require(
        not germany["gasoline_eur_per_l"].isna().any(),
        "Germany gasoline has missing values",
    )
    checks.append("Germany monthly gasoline series covers all 198 months")

    japan = pd.read_csv(
        PROCESSED_DIR / "japan_regular_gasoline_monthly.csv",
        parse_dates=["month_end"],
    )
    require(len(japan) == 198, f"Japan monthly rows={len(japan)}")
    require(japan["period"].is_unique, "Japan period is not unique")
    require(
        not japan["regular_gasoline_jpy_per_l"].isna().any(),
        "Japan gasoline has missing values",
    )
    checks.append("Japan monthly gasoline series covers all 198 months")

    korea = pd.read_csv(
        PROCESSED_DIR / "korea_regular_gasoline_monthly.csv",
        parse_dates=["month_end"],
    )
    require(len(korea) == 198, f"Korea monthly rows={len(korea)}")
    require(korea["period"].is_unique, "Korea period is not unique")
    require(
        not korea["regular_gasoline_krw_per_l"].isna().any(),
        "Korea gasoline has missing values",
    )
    require(
        math.isclose(
            korea.loc[
                korea["period"].eq("2026-06"),
                "regular_gasoline_krw_per_l",
            ].iat[0],
            2004.67,
            rel_tol=0,
            abs_tol=1e-9,
        ),
        "Korea 2026-06 gasoline value does not match KOSIS",
    )
    checks.append("Korea KOSIS monthly gasoline series covers all 198 months")

    policy = pd.read_csv(PROCESSED_DIR / "cn_fuel_policy_events.csv")
    expected_gasoline = [1045, 380]
    expected_diesel = [1005, 370]
    require(
        policy["gasoline_policy_gap_cny_t"].tolist() == expected_gasoline,
        "gasoline policy gaps do not match NDRC notices",
    )
    require(
        policy["diesel_policy_gap_cny_t"].tolist() == expected_diesel,
        "diesel policy gaps do not match NDRC notices",
    )
    checks.append("NDRC gasoline and diesel policy gaps reproduce exactly")

    steo = pd.read_csv(PROCESSED_DIR / "eia_steo_selected.csv")
    require(
        set(steo["data_status"]) == {"historical", "estimate"},
        f"unexpected STEO statuses after cutoff: {set(steo['data_status'])}",
    )
    require(
        steo["period"].max() == "2026-06",
        "STEO cutoff was not enforced",
    )
    checks.append("STEO forecast rows after the cutoff are excluded and estimates are flagged")

    result = {"status": "PASS", "checks": checks}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
