"""Build modeling panels for the three oil-shock questions.

The script uses the existing processed P0 layer as the main input. Optional
external enrichments are advisory: if they cannot be fetched, the panels still
build and the issue is recorded in results/data_warnings.json.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
RESULTS_DIR = REPO_ROOT / "results"
CUTOFF = pd.Timestamp("2026-06-30")
START_MONTH = "2010-01"
RANDOM_SEED = 20260730
BARREL_TO_TONNE = 0.1364
EVENT_E1_CALENDAR_START = pd.Timestamp("2026-02-28")
EVENT_E3_CALENDAR_START = pd.Timestamp("2026-06-17")
COUNTRY_META = {
    "CHN": {"name": "China", "fuel_file": "", "fuel_col": "", "unit": "CNY/tonne proxy"},
    "DEU": {"name": "Germany", "fuel_file": "germany_eurosuper95_monthly.csv", "fuel_col": "gasoline_eur_per_l", "unit": "EUR/litre"},
    "FRA": {"name": "France", "fuel_file": "france_eurosuper95_monthly.csv", "fuel_col": "gasoline_eur_per_l", "unit": "EUR/litre"},
    "ITA": {"name": "Italy", "fuel_file": "italy_eurosuper95_monthly.csv", "fuel_col": "gasoline_eur_per_l", "unit": "EUR/litre"},
    "ESP": {"name": "Spain", "fuel_file": "spain_eurosuper95_monthly.csv", "fuel_col": "gasoline_eur_per_l", "unit": "EUR/litre"},
    "JPN": {"name": "Japan", "fuel_file": "japan_regular_gasoline_monthly.csv", "fuel_col": "regular_gasoline_jpy_per_l", "unit": "JPY/litre"},
    "KOR": {"name": "Korea", "fuel_file": "korea_regular_gasoline_monthly.csv", "fuel_col": "regular_gasoline_krw_per_l", "unit": "KRW/litre"},
}
CONTROL_COUNTRY_ORDER = ["DEU", "FRA", "ITA", "ESP", "JPN", "KOR"]

OECD_GDP_URLS = {
    "china_real_gdp_yoy_pct": "https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_GROWTH_OECD/Q.....B1GQ......GY.?startPeriod=2010-Q1&endPeriod=2026-Q2&dimensionAtObservation=AllDimensions&format=csvfile",
    "china_real_gdp_qoq_pct": "https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_GROWTH_OECD/Q.....B1GQ......G1.?startPeriod=2010-Q1&endPeriod=2026-Q2&dimensionAtObservation=AllDimensions&format=csvfile",
}
NBS_2026_Q2_URL = "https://www.stats.gov.cn/sj/zxfb/202607/t20260715_1964121.html"


def read_processed(filename: str, **kwargs: Any) -> pd.DataFrame:
    return pd.read_csv(PROCESSED_DIR / filename, **kwargs)


def save_processed(frame: pd.DataFrame, filename: str) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / filename
    frame.to_csv(path, index=False, encoding="utf-8")
    return path


def update_data_warnings(stage: str, warnings: list[dict[str, Any]]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "data_warnings.json"
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = {}
    payload.setdefault("stage_warnings", {})[stage] = warnings
    has_errors = bool(payload.get("errors"))
    has_warnings = bool(payload.get("warnings")) or any(payload.get("stage_warnings", {}).values())
    payload["status"] = "FAIL" if has_errors else ("WARN" if has_warnings else "PASS")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def zscore(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    std = values.std(skipna=True)
    if not np.isfinite(std) or std == 0:
        return values * np.nan
    return (values - values.mean(skipna=True)) / std


def log_positive(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    result = pd.Series(np.nan, index=series.index, dtype=float)
    mask = values > 0
    result.loc[mask] = np.log(values.loc[mask])
    return result


def month_end_from_period(period: pd.Series) -> pd.Series:
    return pd.to_datetime(period.astype(str) + "-01") + pd.offsets.MonthEnd(0)


def quarter_label(dates: pd.Series) -> pd.Series:
    periods = pd.PeriodIndex(pd.to_datetime(dates), freq="Q")
    return pd.Series([f"{period.year}-Q{period.quarter}" for period in periods], index=dates.index)


def add_event_stage(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    date = pd.to_datetime(result["date"])
    trade_mask = date.ge(EVENT_E1_CALENDAR_START) & result["brent_usd_bbl"].notna() & result["wti_usd_bbl"].notna()
    trading_dates = date.loc[trade_mask].drop_duplicates().sort_values().tolist()
    if len(trading_dates) < 4:
        raise ValueError("Cannot map E1 weekend event to at least four post-event common trading days.")
    e1_start = pd.Timestamp(trading_dates[0])
    e1_car_end = pd.Timestamp(trading_dates[2])
    e2_start = pd.Timestamp(trading_dates[3])
    e3_candidates = date.loc[
        date.ge(EVENT_E3_CALENDAR_START) & result["brent_usd_bbl"].notna() & result["wti_usd_bbl"].notna()
    ]
    if e3_candidates.empty:
        raise ValueError("Cannot map E3 easing event to a common trading day.")
    e3_start = pd.Timestamp(e3_candidates.min())

    result["war_stage"] = "prewar"
    result.loc[date.between(e1_start, e1_car_end), "war_stage"] = "E1_immediate_window"
    result.loc[date.between(e2_start, e3_start - pd.Timedelta(days=1)), "war_stage"] = "E2_disruption"
    result.loc[date >= e3_start, "war_stage"] = "E3_easing"
    result["war_on"] = (date >= e1_start).astype(int)
    result["stage_E1"] = date.between(e1_start, e1_car_end).astype(int)
    result["stage_E2"] = (result["war_stage"].eq("E2_disruption")).astype(int)
    result["stage_E3"] = (result["war_stage"].eq("E3_easing")).astype(int)
    result["event_e1_calendar_start"] = EVENT_E1_CALENDAR_START.strftime("%Y-%m-%d")
    result["event_e1_trading_start"] = e1_start.strftime("%Y-%m-%d")
    result["event_e1_car_end_0_2"] = e1_car_end.strftime("%Y-%m-%d")
    result["event_e2_trading_start"] = e2_start.strftime("%Y-%m-%d")
    result["event_e3_trading_start"] = e3_start.strftime("%Y-%m-%d")
    return result


def fetch_oecd_china_gdp(warnings: list[dict[str, Any]]) -> pd.DataFrame:
    merged: pd.DataFrame | None = None
    source_urls: dict[str, str] = {}
    for value_column, url in OECD_GDP_URLS.items():
        try:
            response = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            frame = pd.read_csv(io.StringIO(response.text))
            frame = frame.loc[frame["REF_AREA"].eq("CHN"), ["TIME_PERIOD", "OBS_VALUE"]].copy()
            frame = frame.rename(columns={"TIME_PERIOD": "quarter", "OBS_VALUE": value_column})
            source_urls[value_column] = url
        except Exception as exc:
            warnings.append({"code": "oecd_gdp_fetch_failed", "message": f"{value_column}: {exc}"})
            frame = pd.DataFrame(columns=["quarter", value_column])
        merged = frame if merged is None else merged.merge(frame, on="quarter", how="outer")

    if merged is None or merged.empty:
        return pd.DataFrame(columns=["quarter", "quarter_end", "china_real_gdp_yoy_pct", "china_real_gdp_qoq_pct", "source_note"])

    if "china_real_gdp_yoy_pct" not in merged.columns:
        merged["china_real_gdp_yoy_pct"] = np.nan
    if "china_real_gdp_qoq_pct" not in merged.columns:
        merged["china_real_gdp_qoq_pct"] = np.nan

    q2_mask = merged["quarter"].eq("2026-Q2")
    if not q2_mask.any():
        merged = pd.concat(
            [
                merged,
                pd.DataFrame(
                    [
                        {
                            "quarter": "2026-Q2",
                            "china_real_gdp_yoy_pct": 4.3,
                            "china_real_gdp_qoq_pct": 0.9,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        warnings.append(
            {
                "code": "nbs_gdp_manual_supplement",
                "message": "2026-Q2 GDP yoy=4.3 and qoq=0.9 added from NBS 2026-07-15 release.",
                "url": NBS_2026_Q2_URL,
            }
        )
    else:
        if merged.loc[q2_mask, "china_real_gdp_yoy_pct"].isna().all():
            merged.loc[q2_mask, "china_real_gdp_yoy_pct"] = 4.3
            warnings.append(
                {
                    "code": "nbs_gdp_yoy_manual_supplement",
                    "message": "OECD GY lacks 2026-Q2; GDP yoy=4.3 added from NBS 2026-07-15 release.",
                    "url": NBS_2026_Q2_URL,
                }
            )
        if merged.loc[q2_mask, "china_real_gdp_qoq_pct"].isna().all():
            merged.loc[q2_mask, "china_real_gdp_qoq_pct"] = 0.9

    merged["quarter_end"] = pd.PeriodIndex(merged["quarter"], freq="Q").to_timestamp(how="end").normalize()
    merged = merged.loc[merged["quarter_end"] <= CUTOFF].sort_values("quarter").reset_index(drop=True)
    merged["source_note"] = "OECD DF_QNA_EXPENDITURE_GROWTH_OECD; 2026-Q2 yoy supplemented from NBS when absent"
    save_processed(merged, "china_real_gdp_quarterly.csv")
    return merged


def build_daily_q1() -> pd.DataFrame:
    daily = read_processed("p0_daily_market.csv", parse_dates=["date"]).sort_values("date")
    daily = daily.loc[daily["date"].le(CUTOFF)].copy()
    for column in ["brent_usd_bbl", "wti_usd_bbl", "usd_broad_index", "cny_per_usd", "jpy_per_usd", "krw_per_usd", "eur_per_usd"]:
        daily[f"log_{column}"] = log_positive(daily[column])
        daily[f"{column}_log_return"] = daily[f"log_{column}"].diff()
    daily = add_event_stage(daily)
    columns = [
        "date",
        "brent_usd_bbl",
        "wti_usd_bbl",
        "usd_broad_index",
        "cny_per_usd",
        "jpy_per_usd",
        "krw_per_usd",
        "eur_per_usd",
        "brent_usd_bbl_log_return",
        "wti_usd_bbl_log_return",
        "usd_broad_index_log_return",
        "cny_per_usd_log_return",
        "war_stage",
        "war_on",
        "stage_E1",
        "stage_E2",
        "stage_E3",
        "event_e1_calendar_start",
        "event_e1_trading_start",
        "event_e1_car_end_0_2",
        "event_e2_trading_start",
        "event_e3_trading_start",
    ]
    output = daily[columns]
    save_processed(output, "model_daily_q1.csv")
    return output


def build_monthly_q1() -> pd.DataFrame:
    monthly = read_processed("p0_monthly_market.csv", parse_dates=["month_end"]).sort_values("period")
    monthly = monthly.loc[monthly["month_end"].le(CUTOFF)].copy()
    monthly["month_start"] = pd.to_datetime(monthly["period"] + "-01")
    for column in ["brent_usd_bbl", "wti_usd_bbl", "usd_broad_index", "cny_per_usd", "us_crude_stock_month_end_kbbl", "GPR"]:
        monthly[f"log_{column}"] = log_positive(monthly[column])
        monthly[f"{column}_log_return"] = monthly[f"log_{column}"].diff()
        monthly[f"{column}_lag1"] = monthly[column].shift(1)
        monthly[f"{column}_log_return_lag1"] = monthly[f"{column}_log_return"].shift(1)
    monthly["GPR_z"] = zscore(monthly["GPR"])
    monthly["GPR_z_lag1"] = monthly["GPR_z"].shift(1)
    monthly["stock_log_lag1"] = monthly["log_us_crude_stock_month_end_kbbl"].shift(1)
    monthly["log_brent"] = monthly["log_brent_usd_bbl"]
    output = monthly[
        [
            "period",
            "month_start",
            "month_end",
            "brent_usd_bbl",
            "wti_usd_bbl",
            "log_brent",
            "brent_usd_bbl_log_return",
            "wti_usd_bbl_log_return",
            "usd_broad_index",
            "usd_broad_index_log_return",
            "usd_broad_index_log_return_lag1",
            "cny_per_usd",
            "cny_per_usd_log_return",
            "jpy_per_usd",
            "krw_per_usd",
            "usd_per_eur",
            "eur_per_usd",
            "stock_reference_date",
            "us_crude_stock_month_end_kbbl",
            "stock_log_lag1",
            "GPR",
            "GPR_z",
            "GPR_z_lag1",
            "GPRT",
            "GPRA",
        ]
    ]
    save_processed(output, "model_monthly_q1.csv")
    return output


def load_china_macro(monthly_q1: pd.DataFrame, warnings: list[dict[str, Any]]) -> pd.DataFrame:
    cpi = read_processed("oecd_g20_cpi_monthly.csv")
    cpi = cpi.loc[cpi["REF_AREA"].eq("CHN"), ["TIME_PERIOD", "OBS_VALUE"]].copy()
    cpi = cpi.rename(columns={"TIME_PERIOD": "period", "OBS_VALUE": "china_cpi_yoy_pct"})

    macro = monthly_q1[
        [
            "period",
            "month_end",
            "brent_usd_bbl",
            "log_brent",
            "brent_usd_bbl_log_return",
            "cny_per_usd",
            "cny_per_usd_log_return",
            "usd_broad_index",
            "usd_broad_index_log_return",
            "GPR",
            "GPR_z",
        ]
    ].merge(cpi, on="period", how="left")
    macro["china_fx_log_change_pct"] = macro["cny_per_usd_log_return"] * 100.0
    macro["covid_phase"] = (
        pd.to_datetime(macro["period"] + "-01").between(pd.Timestamp("2020-02-01"), pd.Timestamp("2022-12-01"))
    ).astype(int)

    optional_files = {
        "nbs_iav_monthly.csv": ("china_iav_yoy_pct", "china_iav_mom_sa_pct"),
        "nbs_ppi_monthly.csv": ("china_ppi_yoy_pct",),
    }
    for filename, columns in optional_files.items():
        path = PROCESSED_DIR / filename
        if not path.exists():
            warnings.append({"code": "optional_china_macro_missing", "message": f"{filename} absent; Q2 will run available CPI/FX/GDP modules."})
            for column in columns:
                macro[column] = np.nan
            continue
        frame = pd.read_csv(path)
        keep = ["period"] + [column for column in columns if column in frame.columns]
        macro = macro.merge(frame[keep], on="period", how="left")

    q1_shocks_path = RESULTS_DIR / "q1_monthly_shocks.csv"
    if q1_shocks_path.exists():
        shocks = pd.read_csv(q1_shocks_path)
        shock_columns = [
            column
            for column in [
                "period",
                "OilShock",
                "ARBaselineGap",
                "OilShock_source",
                "supply_shock",
                "aggregate_demand_shock",
                "oil_specific_risk_shock",
                "reduced_form_shock",
                "source_vintage",
            ]
            if column in shocks.columns
        ]
        macro = macro.merge(shocks[shock_columns], on="period", how="left")
        macro["OilShock_source"] = macro.get("OilShock_source", pd.Series(index=macro.index, dtype=object)).fillna("q1_monthly_forecast_residual")
        if "ARBaselineGap" not in macro.columns:
            macro["ARBaselineGap"] = 0.0
        for column in ["supply_shock", "aggregate_demand_shock", "oil_specific_risk_shock", "reduced_form_shock"]:
            if column not in macro.columns:
                macro[column] = np.nan
        if "source_vintage" not in macro.columns:
            macro["source_vintage"] = ""
    else:
        macro["OilShock"] = zscore(macro["brent_usd_bbl_log_return"])
        macro["ARBaselineGap"] = 0.0
        macro["OilShock_source"] = "proxy_brent_log_return_until_q1_runs"
        macro["supply_shock"] = np.nan
        macro["aggregate_demand_shock"] = np.nan
        macro["oil_specific_risk_shock"] = np.nan
        macro["reduced_form_shock"] = macro["OilShock"]
        macro["source_vintage"] = "fallback_brent_return"
        warnings.append({"code": "q1_shocks_not_yet_available", "message": "Using standardized Brent monthly log return as temporary OilShock proxy."})

    save_processed(macro, "model_monthly_cn.csv")
    return macro


def build_quarterly_cn(monthly_cn: pd.DataFrame, gdp: pd.DataFrame) -> pd.DataFrame:
    frame = monthly_cn.copy()
    frame["quarter"] = quarter_label(frame["period"] + "-01")
    quarterly = (
        frame.groupby("quarter", as_index=False)
        .agg(
            quarter_end=("month_end", "max"),
            OilShock_sum=("OilShock", "sum"),
            OilShock_mean=("OilShock", "mean"),
            supply_shock_sum=("supply_shock", "sum"),
            aggregate_demand_shock_sum=("aggregate_demand_shock", "sum"),
            oil_specific_risk_shock_sum=("oil_specific_risk_shock", "sum"),
            reduced_form_shock_sum=("reduced_form_shock", "sum"),
            ARBaselineGap_mean=("ARBaselineGap", "mean"),
            brent_log_return_sum=("brent_usd_bbl_log_return", "sum"),
            china_cpi_yoy_pct_mean=("china_cpi_yoy_pct", "mean"),
            china_fx_log_change_pct_sum=("china_fx_log_change_pct", "sum"),
        )
        .sort_values("quarter")
    )
    if not gdp.empty:
        quarterly = quarterly.merge(
            gdp[["quarter", "china_real_gdp_yoy_pct", "china_real_gdp_qoq_pct", "source_note"]],
            on="quarter",
            how="left",
        )
    else:
        quarterly["china_real_gdp_yoy_pct"] = np.nan
        quarterly["china_real_gdp_qoq_pct"] = np.nan
        quarterly["source_note"] = "GDP unavailable"
    save_processed(quarterly, "model_quarterly_cn.csv")
    return quarterly


def build_china_policy_monthly(monthly_q1: pd.DataFrame) -> pd.DataFrame:
    policy = read_processed("cn_fuel_policy_events.csv", parse_dates=["effective_date"])
    months = pd.DataFrame({"period": monthly_q1["period"]})
    monthly_policy = policy.copy()
    monthly_policy["period"] = monthly_policy["effective_date"].dt.to_period("M").astype(str)
    monthly_policy = (
        monthly_policy.groupby("period", as_index=False)
        .agg(
            gasoline_actual_adjustment_cny_t=("gasoline_actual_adjustment_cny_t", "sum"),
            gasoline_rule_adjustment_cny_t=("gasoline_rule_adjustment_cny_t", "sum"),
            gasoline_policy_gap_cny_t=("gasoline_policy_gap_cny_t", "sum"),
            diesel_actual_adjustment_cny_t=("diesel_actual_adjustment_cny_t", "sum"),
            diesel_rule_adjustment_cny_t=("diesel_rule_adjustment_cny_t", "sum"),
            diesel_policy_gap_cny_t=("diesel_policy_gap_cny_t", "sum"),
        )
    )
    result = months.merge(monthly_policy, on="period", how="left").fillna(0.0)
    for column in [
        "gasoline_actual_adjustment_cny_t",
        "gasoline_rule_adjustment_cny_t",
        "gasoline_policy_gap_cny_t",
        "diesel_actual_adjustment_cny_t",
        "diesel_rule_adjustment_cny_t",
        "diesel_policy_gap_cny_t",
    ]:
        result[f"cum_{column}"] = result[column].cumsum()
    save_processed(result, "china_fuel_policy_monthly.csv")
    return result


def build_policy_buffer_table() -> pd.DataFrame:
    years = range(2010, 2027)
    rows: list[dict[str, Any]] = []
    for country in COUNTRY_META:
        for year in years:
            rows.append(
                {
                    "country": country,
                    "year": year,
                    "oil_import_dependency": np.nan,
                    "oil_intensity": np.nan,
                    "fuel_price_regulation": 1.0 if country == "CHN" else 0.0,
                    "import_source_hhi": np.nan,
                    "source_url": "institutional coding from official fuel-price sources; quantitative import buffers require separate annual source table",
                    "buffer_note": "CHN=regulated domestic product-price mechanism/proxy scenario; controls=observed retail-price pass-through.",
                }
            )
    result = pd.DataFrame(rows)
    save_processed(result, "country_policy_buffers_annual.csv")
    return result


def make_country_rows(
    country: str,
    country_name: str,
    monthly_q1: pd.DataFrame,
    fuel: pd.DataFrame,
    fuel_column: str,
    fuel_unit: str,
    brent_local: pd.Series,
    fuel_source: str,
    price_measure_type: str,
    observed_or_regulated: str,
    included_in_main_comparison: bool,
    comparability_note: str,
) -> pd.DataFrame:
    rows = monthly_q1[["period", "month_end", "brent_usd_bbl", "GPR", "cny_per_usd", "jpy_per_usd", "krw_per_usd"]].copy()
    rows = rows.merge(fuel[["period", fuel_column]], on="period", how="left")
    rows = rows.rename(columns={fuel_column: "fuel_price_local"})
    rows["country"] = country
    rows["country_name"] = country_name
    rows["fuel_unit"] = fuel_unit
    rows["fuel_source"] = fuel_source
    rows["price_measure_type"] = price_measure_type
    rows["observed_or_regulated"] = observed_or_regulated
    rows["included_in_main_comparison"] = included_in_main_comparison
    rows["comparability_note"] = comparability_note
    rows["brent_local_per_bbl"] = brent_local.to_numpy()
    rows["fuel_log"] = log_positive(rows["fuel_price_local"])
    rows["fuel_log_return"] = rows["fuel_log"].diff()
    rows["brent_local_log"] = log_positive(rows["brent_local_per_bbl"])
    rows["brent_local_log_return"] = rows["brent_local_log"].diff()
    return rows


def build_country_monthly(monthly_q1: pd.DataFrame, monthly_cn: pd.DataFrame, warnings: list[dict[str, Any]]) -> pd.DataFrame:
    cpi = read_processed("oecd_g20_cpi_monthly.csv")
    cpi = cpi[["REF_AREA", "TIME_PERIOD", "OBS_VALUE"]].rename(
        columns={"REF_AREA": "country", "TIME_PERIOD": "period", "OBS_VALUE": "cpi_yoy_pct"}
    )
    ip = read_processed("oecd_kei_ip_monthly.csv")
    ip = ip[["REF_AREA", "TIME_PERIOD", "OBS_VALUE"]].rename(
        columns={"REF_AREA": "country", "TIME_PERIOD": "period", "OBS_VALUE": "ip_index"}
    )

    germany = read_processed("germany_eurosuper95_monthly.csv")
    france = read_processed("france_eurosuper95_monthly.csv")
    italy = read_processed("italy_eurosuper95_monthly.csv")
    spain = read_processed("spain_eurosuper95_monthly.csv")
    japan = read_processed("japan_regular_gasoline_monthly.csv")
    korea = read_processed("korea_regular_gasoline_monthly.csv")

    policy = build_china_policy_monthly(monthly_q1)
    china_fuel = monthly_q1[["period", "brent_usd_bbl", "cny_per_usd"]].merge(policy, on="period", how="left")
    china_fuel["brent_cny_per_tonne_proxy"] = china_fuel["brent_usd_bbl"] * china_fuel["cny_per_usd"] / BARREL_TO_TONNE
    china_fuel["china_gasoline_proxy_cny_t"] = (
        china_fuel["brent_cny_per_tonne_proxy"] - china_fuel["cum_gasoline_policy_gap_cny_t"]
    ).clip(lower=1.0)
    china_fuel["china_gasoline_rule_proxy_cny_t"] = china_fuel["brent_cny_per_tonne_proxy"].clip(lower=1.0)
    warnings.append(
        {
            "code": "china_fuel_price_proxy",
            "message": "China fuel price uses Brent-CNY tonne proxy adjusted by cumulative NDRC policy gaps; it is not an observed retail gasoline series.",
        }
    )

    rows = [
        make_country_rows(
            "CHN",
            "China",
            monthly_q1,
            china_fuel,
            "china_gasoline_proxy_cny_t",
            "CNY/tonne proxy",
            monthly_q1["brent_usd_bbl"] * monthly_q1["cny_per_usd"],
            "Brent-CNY proxy net of NDRC policy gaps",
            "constructed_brent_cny_policy_proxy",
            "proxy_not_observed",
            False,
            "China fuel price is constructed from Brent-CNY minus cumulative NDRC policy gaps; excluded from the main cross-country fuel-price ranking.",
        ),
        make_country_rows(
            "DEU",
            "Germany",
            monthly_q1,
            germany,
            "gasoline_eur_per_l",
            "EUR/litre",
            monthly_q1["brent_usd_bbl"] * monthly_q1["eur_per_usd"],
            "European Commission Weekly Oil Bulletin",
            "observed_retail_gasoline",
            "observed_retail",
            True,
            "Observed Euro-super 95 retail price, monthly average of official weekly data.",
        ),
        make_country_rows(
            "JPN",
            "Japan",
            monthly_q1,
            japan,
            "regular_gasoline_jpy_per_l",
            "JPY/litre",
            monthly_q1["brent_usd_bbl"] * monthly_q1["jpy_per_usd"],
            "Japan METI weekly fuel survey monthly average",
            "observed_retail_gasoline",
            "observed_retail",
            True,
            "Observed regular gasoline retail price, monthly average of official weekly data.",
        ),
        make_country_rows(
            "KOR",
            "Korea",
            monthly_q1,
            korea,
            "regular_gasoline_krw_per_l",
            "KRW/litre",
            monthly_q1["brent_usd_bbl"] * monthly_q1["krw_per_usd"],
            "KOSIS / Korea National Oil Corporation monthly gasoline",
            "observed_retail_gasoline",
            "observed_retail",
            True,
            "Observed regular gasoline national monthly average from KOSIS/KNOC.",
        ),
    ]
    for country, country_name, fuel in [
        ("FRA", "France", france),
        ("ITA", "Italy", italy),
        ("ESP", "Spain", spain),
    ]:
        rows.append(
            make_country_rows(
                country,
                country_name,
                monthly_q1,
                fuel,
                "gasoline_eur_per_l",
                "EUR/litre",
                monthly_q1["brent_usd_bbl"] * monthly_q1["eur_per_usd"],
                "European Commission Weekly Oil Bulletin",
                "observed_retail_gasoline",
                "observed_retail",
                True,
                f"Observed Euro-super 95 retail price for {country_name}, monthly average of official weekly data.",
            )
        )
    panel = pd.concat(rows, ignore_index=True)
    panel["year"] = pd.to_datetime(panel["period"] + "-01").dt.year
    buffers = build_policy_buffer_table()
    panel = panel.merge(buffers, on=["country", "year"], how="left")
    panel = panel.merge(cpi, on=["country", "period"], how="left")
    panel = panel.merge(ip, on=["country", "period"], how="left")
    chn_activity = monthly_cn[["period", "china_iav_yoy_pct"]].rename(columns={"china_iav_yoy_pct": "activity_yoy_pct"})
    panel = panel.merge(chn_activity, on="period", how="left")
    panel.loc[panel["country"].ne("CHN"), "activity_yoy_pct"] = np.nan
    panel["ip_log"] = log_positive(panel["ip_index"])
    panel["ip_yoy_log_change_pct"] = panel.groupby("country")["ip_log"].diff(12) * 100.0
    panel["industrial_activity_yoy_pct"] = panel["ip_yoy_log_change_pct"]
    panel.loc[panel["country"].eq("CHN"), "industrial_activity_yoy_pct"] = panel.loc[panel["country"].eq("CHN"), "activity_yoy_pct"]
    panel = panel.merge(
        monthly_cn[
            [
                "period",
                "OilShock",
                "ARBaselineGap",
                "OilShock_source",
                "supply_shock",
                "aggregate_demand_shock",
                "oil_specific_risk_shock",
                "reduced_form_shock",
                "source_vintage",
            ]
        ],
        on="period",
        how="left",
    )
    panel = panel[
        [
            "country",
            "country_name",
            "year",
            "period",
            "month_end",
            "fuel_price_local",
            "fuel_unit",
            "fuel_source",
            "price_measure_type",
            "observed_or_regulated",
            "included_in_main_comparison",
            "comparability_note",
            "oil_import_dependency",
            "oil_intensity",
            "fuel_price_regulation",
            "import_source_hhi",
            "buffer_note",
            "fuel_log_return",
            "brent_local_per_bbl",
            "brent_local_log_return",
            "cpi_yoy_pct",
            "ip_index",
            "ip_yoy_log_change_pct",
            "activity_yoy_pct",
            "industrial_activity_yoy_pct",
            "OilShock",
            "ARBaselineGap",
            "OilShock_source",
            "supply_shock",
            "aggregate_demand_shock",
            "oil_specific_risk_shock",
            "reduced_form_shock",
            "source_vintage",
            "GPR",
        ]
    ].sort_values(["country", "period"])
    save_processed(panel, "model_country_monthly.csv")
    save_processed(china_fuel, "china_fuel_proxy_monthly.csv")
    return panel


def main() -> int:
    np.random.seed(RANDOM_SEED)
    warnings: list[dict[str, Any]] = []
    daily = build_daily_q1()
    monthly_q1 = build_monthly_q1()
    gdp = fetch_oecd_china_gdp(warnings)
    monthly_cn = load_china_macro(monthly_q1, warnings)
    quarterly_cn = build_quarterly_cn(monthly_cn, gdp)
    country = build_country_monthly(monthly_q1, monthly_cn, warnings)

    summary = {
        "status": "WARN" if warnings else "PASS",
        "random_seed": RANDOM_SEED,
        "cutoff": CUTOFF.strftime("%Y-%m-%d"),
        "outputs": {
            "model_daily_q1.csv": len(daily),
            "model_monthly_q1.csv": len(monthly_q1),
            "model_monthly_cn.csv": len(monthly_cn),
            "model_quarterly_cn.csv": len(quarterly_cn),
            "model_country_monthly.csv": len(country),
        },
        "warnings": warnings,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "model_panel_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    update_data_warnings("build_model_panels", warnings)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
