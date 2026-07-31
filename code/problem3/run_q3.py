"""Question 3: cross-country buffers and China policy counterfactuals."""

from __future__ import annotations

import argparse
import json
import sys
import warnings as py_warnings
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from linearmodels.panel import PanelOLS
from linearmodels.panel.utility import AbsorbingEffectWarning
from scipy.stats import norm


REPO_ROOT = Path(__file__).resolve().parents[2]
CODE_DIR = REPO_ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from utils.plot_style import PALETTE, apply_paper_style, finish_figure, save_figure, style_axis

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROCESSED_DIR = REPO_ROOT / "data" / "processed"
RESULTS_DIR = REPO_ROOT / "results"
FIGURES_DIR = REPO_ROOT / "figures"
RANDOM_SEED = 20260730


COUNTRY_ORDER = ["CHN", "DEU", "FRA", "ITA", "ESP", "JPN", "KOR"]
MAIN_CONTROL_COUNTRIES = ["DEU", "FRA", "ITA", "ESP", "JPN", "KOR"]
COUNTRY_LABEL_ZH = {
    "CHN": "中国",
    "DEU": "德国",
    "FRA": "法国",
    "ITA": "意大利",
    "ESP": "西班牙",
    "JPN": "日本",
    "KOR": "韩国",
}
OUTCOME_LABELS = {
    "fuel": "燃油价格累计对数变化，百分点",
    "cpi": "CPI同比，百分点",
    "ip": "工业生产同比对数变化，百分点",
}


def ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)


def save_csv(frame: pd.DataFrame, filename: str) -> Path:
    path = RESULTS_DIR / filename
    frame.to_csv(path, index=False, encoding="utf-8")
    return path


def read_csv_result(filename: str) -> pd.DataFrame:
    path = RESULTS_DIR / filename
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def log_positive(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    result = pd.Series(np.nan, index=series.index, dtype=float)
    mask = values > 0
    result.loc[mask] = np.log(values.loc[mask])
    return result


def add_lags(frame: pd.DataFrame, column: str, max_lag: int) -> pd.DataFrame:
    result = frame.copy()
    for lag in range(max_lag + 1):
        result[f"{column}_lag{lag}"] = result[column].shift(lag)
    return result


def bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series
    return series.astype(str).str.lower().isin(["true", "1", "yes"])


def shock_column(frame: pd.DataFrame) -> str:
    for column in ["oil_specific_risk_shock", "supply_shock", "aggregate_demand_shock", "OilShock"]:
        if column in frame.columns and pd.to_numeric(frame[column], errors="coerce").notna().sum() >= 24:
            return column
    raise ValueError("Q3 panel lacks an auditable oil shock column.")


def fit_country_pass_through(panel: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for country in COUNTRY_ORDER:
        frame = panel.loc[panel["country"].eq(country)].sort_values("period").copy()
        frame = add_lags(frame, "brent_local_log_return", 6)
        regressors = [f"brent_local_log_return_lag{lag}" for lag in range(7)]
        frame["fuel_lag1"] = frame["fuel_log_return"].shift(1)
        usable = frame.dropna(subset=["fuel_log_return", "fuel_lag1"] + regressors)
        if len(usable) < 48:
            warnings_log.append({"code": "q3_pass_through_limited", "message": f"{country}: insufficient fuel observations."})
            continue
        included = bool(bool_series(frame["included_in_main_comparison"]).iloc[0]) if "included_in_main_comparison" in frame else country != "CHN"
        measure_type = frame["price_measure_type"].iloc[0] if "price_measure_type" in frame else ""
        observed_or_regulated = frame["observed_or_regulated"].iloc[0] if "observed_or_regulated" in frame else ""
        comparability_note = frame["comparability_note"].iloc[0] if "comparability_note" in frame else ""
        x = sm.add_constant(usable[regressors + ["fuel_lag1"]].astype(float), has_constant="add")
        fit = sm.OLS(usable["fuel_log_return"], x).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
        for horizon in [1, 3, 6]:
            lag_terms = [f"brent_local_log_return_lag{lag}" for lag in range(horizon + 1)]
            estimate = float(fit.params[lag_terms].sum())
            cov = fit.cov_params().loc[lag_terms, lag_terms]
            se = float(np.sqrt(np.ones(len(lag_terms)) @ cov.to_numpy() @ np.ones(len(lag_terms))))
            rows.append(
                {
                    "country": country,
                    "country_name": frame["country_name"].iloc[0],
                    "horizon": horizon,
                    "response": estimate,
                    "std_error": se,
                    "lower_80": estimate - norm.ppf(0.90) * se,
                    "upper_80": estimate + norm.ppf(0.90) * se,
                    "lower_95": estimate - norm.ppf(0.975) * se,
                    "upper_95": estimate + norm.ppf(0.975) * se,
                    "model": "distributed_lag_pass_through",
                    "specification": "fuel log return on local-currency Brent log-return lags 0..6 and fuel lag",
                    "sample_start": usable["period"].iloc[0],
                    "sample_end": usable["period"].iloc[-1],
                    "n": int(len(usable)),
                    "fuel_source": frame["fuel_source"].iloc[0],
                    "fuel_unit": frame["fuel_unit"].iloc[0],
                    "price_measure_type": measure_type,
                    "observed_or_regulated": observed_or_regulated,
                    "included_in_main_comparison": included,
                    "comparability_note": comparability_note,
                }
            )
    result = pd.DataFrame(rows)
    save_csv(result, "q3_country_pass_through.csv")
    return result


def panel_design(frame: pd.DataFrame, outcome: str, horizon: int) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame, str]:
    data = frame.copy()
    shock = shock_column(data)
    data["shock"] = pd.to_numeric(data[shock], errors="coerce")
    if outcome == "fuel":
        data["target"] = data.groupby("country")["fuel_log"].shift(-horizon) - data.groupby("country")["fuel_log"].shift(1)
        data["target"] = data["target"] * 100.0
        needed = ["target", "shock", "fuel_log"]
    elif outcome == "cpi":
        data["target"] = data.groupby("country")["cpi_yoy_pct"].shift(-horizon)
        needed = ["target", "shock", "cpi_yoy_pct"]
    else:
        activity_col = "industrial_activity_yoy_pct" if "industrial_activity_yoy_pct" in data.columns else "ip_yoy_log_change_pct"
        data["target"] = data.groupby("country")[activity_col].shift(-horizon)
        needed = ["target", "shock", activity_col]
    data["trend"] = data.groupby("country").cumcount()
    for country in MAIN_CONTROL_COUNTRIES:
        data[f"oil_diff_{country}_vs_CHN"] = np.where(data["country"].eq(country), data["shock"], 0.0)
        data[f"trend_{country}_vs_CHN"] = np.where(data["country"].eq(country), data["trend"], 0.0)
    needed += [f"oil_diff_{country}_vs_CHN" for country in MAIN_CONTROL_COUNTRIES]
    x_cols = [f"oil_diff_{country}_vs_CHN" for country in MAIN_CONTROL_COUNTRIES] + [
        f"trend_{country}_vs_CHN" for country in MAIN_CONTROL_COUNTRIES
    ]
    usable = data.dropna(subset=needed).copy()
    usable["month_index"] = pd.PeriodIndex(usable["period"], freq="M").to_timestamp()
    usable = usable.set_index(["country", "month_index"]).sort_index()
    y = usable["target"].astype(float)
    x = usable[x_cols].astype(float)
    return y, x, usable.reset_index(), shock


def buffer_design(frame: pd.DataFrame, outcome: str, horizon: int, buffer: str) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame, str, str]:
    data = frame.copy()
    shock = shock_column(data)
    data["shock"] = pd.to_numeric(data[shock], errors="coerce")
    if buffer not in data.columns:
        raise ValueError(f"country_policy_buffers_annual.csv lacks {buffer}.")
    data[buffer] = pd.to_numeric(data[buffer], errors="coerce")
    if buffer != "fuel_price_regulation":
        std = data[buffer].std(skipna=True)
        if not np.isfinite(std) or std <= 0:
            raise ValueError(f"{buffer} has zero variation.")
        data[f"{buffer}_standardized"] = (data[buffer] - data[buffer].mean(skipna=True)) / std
        buffer_col = f"{buffer}_standardized"
    else:
        buffer_col = buffer
    if outcome == "fuel":
        data["target"] = data.groupby("country")["fuel_log"].shift(-horizon) - data.groupby("country")["fuel_log"].shift(1)
        data["target"] = data["target"] * 100.0
        needed = ["target", "shock", "fuel_log", buffer_col]
    elif outcome == "cpi":
        data["target"] = data.groupby("country")["cpi_yoy_pct"].shift(-horizon)
        needed = ["target", "shock", "cpi_yoy_pct", buffer_col]
    else:
        activity_col = "industrial_activity_yoy_pct" if "industrial_activity_yoy_pct" in data.columns else "ip_yoy_log_change_pct"
        data["target"] = data.groupby("country")[activity_col].shift(-horizon)
        needed = ["target", "shock", activity_col, buffer_col]
    term = f"shock_x_{buffer}"
    data[term] = data["shock"] * data[buffer_col]
    usable = data.dropna(subset=needed + [term]).copy()
    usable = usable.loc[usable[term].notna()].copy()
    usable["month_index"] = pd.PeriodIndex(usable["period"], freq="M").to_timestamp()
    usable = usable.set_index(["country", "month_index"]).sort_index()
    y = usable["target"].astype(float)
    x = usable[[term]].astype(float)
    return y, x, usable.reset_index(), shock, term


def fit_panel_lp(panel: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    from linearmodels.panel import PanelOLS

    rows: list[dict[str, Any]] = []
    for outcome in ["fuel", "cpi", "ip"]:
        outcome_panel = panel.loc[bool_series(panel["included_in_main_comparison"])].copy() if outcome == "fuel" and "included_in_main_comparison" in panel else panel.copy()
        for horizon in range(13):
            y, x, usable, shock = panel_design(outcome_panel, outcome, horizon)
            if len(y) < x.shape[1] + 20 or y.index.get_level_values(0).nunique() < 3:
                warnings_log.append({"code": "q3_panel_lp_skipped", "message": f"{outcome} h={horizon}: insufficient panel support."})
                continue
            fit = PanelOLS(y, x, entity_effects=True, time_effects=True, drop_absorbed=True, check_rank=False).fit(
                cov_type="kernel",
                kernel="bartlett",
                bandwidth=max(1, horizon + 1),
            )
            for country in MAIN_CONTROL_COUNTRIES:
                term = f"oil_diff_{country}_vs_CHN"
                if term not in fit.params.index:
                    continue
                estimate = float(fit.params[term])
                se = float(fit.std_errors[term])
                rows.append(
                    {
                        "outcome": outcome,
                        "country": country,
                        "reference_country": "CHN",
                        "horizon": horizon,
                        "response": estimate,
                        "std_error": se,
                        "lower_80": estimate - norm.ppf(0.90) * se,
                        "upper_80": estimate + norm.ppf(0.90) * se,
                        "lower_95": estimate - norm.ppf(0.975) * se,
                        "upper_95": estimate + norm.ppf(0.975) * se,
                        "pvalue": float(fit.pvalues[term]),
                        "shock": shock,
                        "model": "stacked_panel_LP_time_FE_relative_to_CHN",
                        "response_type": "control_country_minus_china_relative_response",
                        "specification": "country FE, full year-month FE, control-country shock interactions relative to China, control-country trends, Driscoll-Kraay covariance",
                        "sample_start": usable["period"].min(),
                        "sample_end": usable["period"].max(),
                        "n": int(len(usable)),
                    }
                )
    result = pd.DataFrame(rows)
    save_csv(result, "q3_panel_irf.csv")
    return result


def fit_buffer_interactions(panel: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    buffers = ["fuel_price_regulation", "oil_import_dependency", "oil_intensity", "import_source_hhi"]
    for outcome in ["fuel", "cpi", "ip"]:
        outcome_panel = panel.loc[bool_series(panel["included_in_main_comparison"])].copy() if outcome == "fuel" and "included_in_main_comparison" in panel else panel.copy()
        for buffer in buffers:
            for horizon in range(13):
                y, x, usable, shock, term = buffer_design(outcome_panel, outcome, horizon, buffer)
                country_count = y.index.get_level_values(0).nunique()
                if len(y) < 48 or country_count < 3 or float(x[term].var()) <= 1e-12:
                    warnings_log.append({"code": "q3_buffer_lp_skipped", "message": f"{outcome} {buffer} h={horizon}: buffer interaction is not identifiable with current comparable data."})
                    continue
                fit = PanelOLS(y, x, entity_effects=True, time_effects=True, drop_absorbed=True, check_rank=False).fit(
                    cov_type="kernel",
                    kernel="bartlett",
                    bandwidth=max(1, horizon + 1),
                )
                if term not in fit.params.index:
                    warnings_log.append({"code": "q3_buffer_lp_absorbed", "message": f"{outcome} {buffer} h={horizon}: interaction was absorbed."})
                    continue
                estimate = float(fit.params[term])
                se = float(fit.std_errors[term])
                rows.append(
                    {
                        "outcome": outcome,
                        "buffer": buffer,
                        "horizon": horizon,
                        "estimate": estimate,
                        "std_error": se,
                        "lower_80": estimate - norm.ppf(0.90) * se,
                        "upper_80": estimate + norm.ppf(0.90) * se,
                        "lower_95": estimate - norm.ppf(0.975) * se,
                        "upper_95": estimate + norm.ppf(0.975) * se,
                        "pvalue": float(fit.pvalues[term]),
                        "shock": shock,
                        "model": "buffer_interaction_panel_LP_time_FE",
                        "specification": "country FE, full year-month FE, shock x lagged annual buffer; common shock level absorbed by time FE",
                        "sample_start": usable["period"].min(),
                        "sample_end": usable["period"].max(),
                        "countries": int(country_count),
                        "n": int(len(usable)),
                        "identification_note": "MECHANISM_ONLY_single_strong_treatment_country" if buffer == "fuel_price_regulation" else "continuous lagged annual buffer interaction",
                    }
                )
    result = pd.DataFrame(rows)
    save_csv(result, "q3_buffer_interactions.csv")
    return result


def china_fuel_to_macro_elasticities(warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    official = pd.read_csv(PROCESSED_DIR / "china_regulated_gasoline_monthly.csv")
    macro = pd.read_csv(PROCESSED_DIR / "model_monthly_cn.csv")
    frame = macro.merge(
        official[["period", "china_regulated_gasoline_cny_per_ton"]],
        on="period",
        how="left",
    ).sort_values("period")
    frame["fuel_log"] = log_positive(frame["china_regulated_gasoline_cny_per_ton"])
    frame["fuel_log_return"] = frame["fuel_log"].diff()
    frame = add_lags(frame, "fuel_log_return", 6)
    outcomes = {
        "china_ppi_yoy_pct": "PPI",
        "china_cpi_yoy_pct": "CPI",
        "china_iav_yoy_pct": "IAV",
    }
    rows: list[dict[str, Any]] = []
    for outcome, label in outcomes.items():
        if outcome not in frame.columns:
            warnings_log.append({"code": "q3_policy_macro_outcome_missing", "message": f"{outcome} missing for policy propagation."})
            continue
        frame[f"{outcome}_lag1"] = frame[outcome].shift(1)
        lag_terms = [f"fuel_log_return_lag{lag}" for lag in range(7)]
        regressors = lag_terms + [f"{outcome}_lag1", "GPR"]
        usable = frame.dropna(subset=[outcome] + regressors).copy()
        if len(usable) < 48:
            warnings_log.append({"code": "q3_policy_macro_elasticity_limited", "message": f"{outcome}: only {len(usable)} usable observations."})
            continue
        fit = sm.OLS(usable[outcome], sm.add_constant(usable[regressors].astype(float), has_constant="add")).fit(
            cov_type="HAC",
            cov_kwds={"maxlags": 6},
        )
        estimate = float(fit.params[lag_terms].sum())
        cov = fit.cov_params().loc[lag_terms, lag_terms]
        se = float(np.sqrt(np.ones(len(lag_terms)) @ cov.to_numpy() @ np.ones(len(lag_terms))))
        rows.append(
            {
                "outcome": outcome,
                "outcome_label": label,
                "fuel_to_macro_cumulative_elasticity": estimate,
                "std_error": se,
                "sample_start": usable["period"].iloc[0],
                "sample_end": usable["period"].iloc[-1],
                "n": int(len(usable)),
                "model": "China_fuel_to_macro_ARDL",
                "specification": "macro yoy outcome on regulated gasoline log-return lags 0..6, lagged outcome and GPR; HAC(6)",
            }
        )
    return pd.DataFrame(rows)


def policy_counterfactual(country_panel: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    official_path = PROCESSED_DIR / "china_regulated_gasoline_monthly.csv"
    if not official_path.exists():
        raise FileNotFoundError("china_regulated_gasoline_monthly.csv is required for the official-price policy counterfactual.")
    official = pd.read_csv(official_path)
    policy = pd.read_csv(PROCESSED_DIR / "china_fuel_policy_monthly.csv")
    frame = official.merge(
        policy[["period", "gasoline_policy_gap_cny_t", "diesel_policy_gap_cny_t", "cum_gasoline_policy_gap_cny_t", "cum_diesel_policy_gap_cny_t"]],
        on="period",
        how="left",
        suffixes=("", "_policy"),
    )
    frame = frame.loc[frame["period"].between("2026-02", "2026-06")].copy()
    elasticities = china_fuel_to_macro_elasticities(warnings_log)
    frame["policy_adjusted_official_cny_l"] = frame.get("china_regulated_gasoline_cny_per_l", pd.Series(np.nan, index=frame.index))
    frame["no_temporary_control_official_cny_l"] = frame.get("no_temporary_control_gasoline_cny_per_l", pd.Series(np.nan, index=frame.index))
    frame["policy_adjusted_official_cny_t"] = frame["china_regulated_gasoline_cny_per_ton"]
    frame["no_temporary_control_official_cny_t"] = frame["no_temporary_control_gasoline_cny_per_ton"]
    frame["incremental_gasoline_gap_cny_t"] = frame["gasoline_policy_gap_cny_t"]
    frame["cumulative_gasoline_gap_cny_t"] = frame["cum_gasoline_policy_gap_cny_t"]
    frame["actual"] = frame["policy_adjusted_official_cny_t"]
    frame["prediction"] = frame["no_temporary_control_official_cny_t"]
    frame["response"] = frame["cumulative_gasoline_gap_cny_t"]
    frame["fuel_log_gap"] = np.log(frame["prediction"] / frame["actual"])
    macro_rows: list[dict[str, Any]] = []
    for period_row in frame.to_dict("records"):
        for elastic in elasticities.to_dict("records"):
            gap = float(period_row["fuel_log_gap"]) * float(elastic["fuel_to_macro_cumulative_elasticity"])
            width = norm.ppf(0.975) * abs(float(period_row["fuel_log_gap"])) * float(elastic["std_error"])
            macro_rows.append(
                {
                    "period": period_row["period"],
                    "outcome": elastic["outcome"],
                    "outcome_label": elastic["outcome_label"],
                    "policy_adjusted_official_cny_t": period_row["policy_adjusted_official_cny_t"],
                    "no_temporary_control_official_cny_t": period_row["no_temporary_control_official_cny_t"],
                    "incremental_gasoline_gap_cny_t": period_row["incremental_gasoline_gap_cny_t"],
                    "cumulative_gasoline_gap_cny_t": period_row["cumulative_gasoline_gap_cny_t"],
                    "fuel_log_gap": period_row["fuel_log_gap"],
                    "macro_counterfactual_gap_pctpt": gap,
                    "lower_95": gap - width,
                    "upper_95": gap + width,
                    "model": elastic["model"],
                    "horizon": 6,
                    "specification": elastic["specification"],
                    "sample_start": elastic["sample_start"],
                    "sample_end": elastic["sample_end"],
                    "n": elastic["n"],
                    "price_layer_status": "official_regulated_finished_fuel_price_layer",
                    "evidence_status": "MACRO_PROPAGATED_WITH_PARAMETER_UNCERTAINTY",
                }
            )
    macro_columns = [
        "period",
        "outcome",
        "outcome_label",
        "policy_adjusted_official_cny_t",
        "no_temporary_control_official_cny_t",
        "incremental_gasoline_gap_cny_t",
        "cumulative_gasoline_gap_cny_t",
        "fuel_log_gap",
        "macro_counterfactual_gap_pctpt",
        "lower_95",
        "upper_95",
        "model",
        "horizon",
        "specification",
        "sample_start",
        "sample_end",
        "n",
        "price_layer_status",
        "evidence_status",
    ]
    macro_counterfactual = pd.DataFrame(macro_rows, columns=macro_columns)
    save_csv(macro_counterfactual, "q3_policy_macro_counterfactual.csv")
    cpi_macro = macro_counterfactual.loc[macro_counterfactual["outcome"].eq("china_cpi_yoy_pct"), ["period", "macro_counterfactual_gap_pctpt", "lower_95", "upper_95"]]
    frame = frame.drop(columns=[column for column in ["lower_95", "upper_95"] if column in frame.columns])
    frame = frame.merge(cpi_macro.rename(columns={"macro_counterfactual_gap_pctpt": "cpi_counterfactual_gap_pctpt"}), on="period", how="left")
    frame["model"] = "China_policy_counterfactual"
    frame["horizon"] = 6
    frame["specification"] = "add cumulative NDRC gasoline policy gap back to the regulated standard gasoline cap path; macro propagation is written to q3_policy_macro_counterfactual.csv"
    frame["evidence_status"] = np.where(frame["policy_adjusted_official_cny_t"].notna(), "PRICE_LAYER_SUPPORTED", "CONDITIONAL_DATA_COVERAGE")
    frame["price_layer_status"] = "official_regulated_finished_fuel_price_layer"
    frame["sample_start"] = "2010-01"
    frame["sample_end"] = "2026-06"
    result = frame[
        [
            "period",
            "actual",
            "prediction",
            "response",
            "policy_adjusted_official_cny_l",
            "no_temporary_control_official_cny_l",
            "policy_adjusted_official_cny_t",
            "no_temporary_control_official_cny_t",
            "incremental_gasoline_gap_cny_t",
            "cumulative_gasoline_gap_cny_t",
            "fuel_log_gap",
            "cpi_counterfactual_gap_pctpt",
            "lower_95",
            "upper_95",
            "gasoline_policy_gap_cny_t",
            "diesel_policy_gap_cny_t",
            "cum_gasoline_policy_gap_cny_t",
            "model",
            "horizon",
            "specification",
            "evidence_status",
            "price_layer_status",
            "sample_start",
            "sample_end",
        ]
    ]
    save_csv(result, "q3_policy_counterfactual.csv")
    return result


def classify_better(diff: float, lower: float, upper: float, better_when_positive: bool = True) -> str:
    if not np.isfinite(diff):
        return "INCONCLUSIVE"
    point_better = diff > 0 if better_when_positive else diff < 0
    interval_better = lower > 0 if better_when_positive else upper < 0
    if interval_better:
        return "SUPPORTED"
    if point_better:
        return "PARTIAL"
    return "NOT_SUPPORTED"


def build_resilience_metrics(pass_through: pd.DataFrame, panel_irf: pd.DataFrame, macro_counterfactual: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    main_pass = pass_through.loc[bool_series(pass_through["included_in_main_comparison"])].copy() if "included_in_main_comparison" in pass_through else pass_through.copy()
    for horizon in [1, 3, 6]:
        sub = main_pass.loc[main_pass["horizon"].eq(horizon)].copy()
        chn = sub.loc[sub["country"].eq("CHN")]
        controls = sub.loc[sub["country"].isin(MAIN_CONTROL_COUNTRIES)]
        if chn.empty or controls.empty:
            continue
        chn_row = chn.iloc[0]
        control_median = float(controls["response"].median())
        diff = control_median - float(chn_row["response"])
        lower = control_median - float(chn_row["upper_95"])
        upper = control_median - float(chn_row["lower_95"])
        rows.append(
            {
                "dimension": "fuel_pass_through",
                "metric": f"fuel_{horizon}m_cumulative_pass_through",
                "horizon": horizon,
                "china_value": float(chn_row["response"]),
                "control_median": control_median,
                "china_vs_control_median_diff": diff,
                "diff_lower_95": lower,
                "diff_upper_95": upper,
                "judgement": classify_better(diff, lower, upper, True),
                "interpretation": "positive diff means China has lower fuel-price pass-through than the six-country median",
            }
        )
    for outcome, dimension, better_positive in [("cpi", "cpi_peak_response", True), ("ip", "industrial_activity_trough", False)]:
        sub = panel_irf.loc[panel_irf["outcome"].eq(outcome)].copy()
        if sub.empty:
            continue
        grouped = sub.groupby("horizon", as_index=False).agg(
            median_relative_response=("response", "median"),
            lower_95=("lower_95", "median"),
            upper_95=("upper_95", "median"),
        )
        if outcome == "cpi":
            row = grouped.loc[grouped["median_relative_response"].abs().idxmax()]
        else:
            row = grouped.loc[grouped["median_relative_response"].idxmin()]
        diff = float(row["median_relative_response"])
        rows.append(
            {
                "dimension": dimension,
                "metric": f"{outcome}_relative_to_china",
                "horizon": int(row["horizon"]),
                "china_value": 0.0,
                "control_median": diff,
                "china_vs_control_median_diff": diff,
                "diff_lower_95": float(row["lower_95"]),
                "diff_upper_95": float(row["upper_95"]),
                "judgement": classify_better(diff, float(row["lower_95"]), float(row["upper_95"]), better_positive),
                "interpretation": "panel response is control minus China; sign direction is evaluated by the metric definition",
            }
        )
    if not macro_counterfactual.empty:
        for outcome, group in macro_counterfactual.groupby("outcome"):
            max_gap = group.loc[group["macro_counterfactual_gap_pctpt"].abs().idxmax()]
            rows.append(
                {
                    "dimension": "policy_counterfactual_macro",
                    "metric": outcome,
                    "horizon": int(max_gap.get("horizon", 6)),
                    "china_value": float(max_gap["macro_counterfactual_gap_pctpt"]),
                    "control_median": np.nan,
                    "china_vs_control_median_diff": np.nan,
                    "diff_lower_95": float(max_gap["lower_95"]),
                    "diff_upper_95": float(max_gap["upper_95"]),
                    "judgement": "POLICY_SCENARIO",
                    "interpretation": "macro gap if 2026 temporary fuel-price controls are mechanically removed from the official regulated price path",
                }
            )
    result = pd.DataFrame(rows)
    core = result.loc[result["judgement"].isin(["SUPPORTED", "PARTIAL", "NOT_SUPPORTED"])].copy()
    supported = int(core["judgement"].eq("SUPPORTED").sum())
    point_better = int(core["judgement"].isin(["SUPPORTED", "PARTIAL"]).sum())
    reverse = int(core["judgement"].eq("NOT_SUPPORTED").sum())
    if supported >= 2 and reverse == 0:
        overall = "SUPPORTED"
    elif point_better >= 2:
        overall = "PARTIAL"
    else:
        overall = "NOT_SUPPORTED"
    if not result.empty:
        result["overall_china_resilience_judgement"] = overall
    save_csv(result, "q3_resilience_metrics.csv")
    return result


def robustness_checks(panel: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    from linearmodels.panel import PanelOLS

    rows: list[dict[str, Any]] = []
    main_panel = panel.loc[bool_series(panel["included_in_main_comparison"])].copy() if "included_in_main_comparison" in panel else panel.copy()
    main_countries = [country for country in COUNTRY_ORDER if country in set(main_panel["country"])]
    for omitted in [country for country in main_countries if country != "CHN"]:
        subset = main_panel.loc[main_panel["country"].ne(omitted)].copy()
        y, x, usable, shock = panel_design(subset, "fuel", 6)
        if len(y) < x.shape[1] + 20 or y.index.get_level_values(0).nunique() < 3:
            warnings_log.append({"code": "q3_leave_one_skipped", "message": f"omit {omitted}: insufficient panel support."})
            continue
        fit = PanelOLS(y, x, entity_effects=True, time_effects=True, drop_absorbed=True, check_rank=False).fit(
            cov_type="kernel",
            kernel="bartlett",
            bandwidth=7,
        )
        for country in MAIN_CONTROL_COUNTRIES:
            term = f"oil_diff_{country}_vs_CHN"
            if term in fit.params.index:
                rows.append(
                    {
                        "robustness_type": "leave_one_country_panel_fuel_h6",
                        "omitted_country": omitted,
                        "country": country,
                        "horizon": 6,
                        "estimate": float(fit.params[term]),
                        "std_error": float(fit.std_errors[term]),
                        "model": "stacked_panel_LP_time_FE_relative_to_CHN",
                        "specification": "fuel h=6 relative-to-China panel LP with country FE and full year-month FE after omitting one control country",
                        "shock": shock,
                        "n": int(len(usable)),
                    }
                )

    monthly = pd.read_csv(PROCESSED_DIR / "model_monthly_q1.csv")
    usd_panel = main_panel.merge(monthly[["period", "brent_usd_bbl_log_return"]], on="period", how="left")
    for country in main_countries:
        frame = usd_panel.loc[usd_panel["country"].eq(country)].sort_values("period").copy()
        frame = add_lags(frame, "brent_usd_bbl_log_return", 6)
        frame["fuel_lag1"] = frame["fuel_log_return"].shift(1)
        regressors = [f"brent_usd_bbl_log_return_lag{lag}" for lag in range(7)] + ["fuel_lag1"]
        usable = frame.dropna(subset=["fuel_log_return"] + regressors)
        if len(usable) < 48:
            continue
        fit = sm.OLS(
            usable["fuel_log_return"],
            sm.add_constant(usable[regressors].astype(float), has_constant="add"),
        ).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
        lag_terms = [f"brent_usd_bbl_log_return_lag{lag}" for lag in range(7)]
        estimate = float(fit.params[lag_terms].sum())
        rows.append(
            {
                "robustness_type": "usd_brent_fx_ignored_pass_through_h6",
                "omitted_country": "",
                "country": country,
                "horizon": 6,
                "estimate": estimate,
                "std_error": np.nan,
                "model": "distributed_lag_pass_through",
                "specification": "uses USD Brent instead of local-currency Brent",
                "n": int(len(usable)),
            }
        )

    policy = pd.read_csv(PROCESSED_DIR / "china_fuel_policy_monthly.csv")
    policy = policy.loc[policy["period"].between("2026-02", "2026-06")].copy()
    for _, row in policy.iterrows():
        rows.append(
            {
                "robustness_type": "diesel_policy_layer_gap",
                "omitted_country": "",
                "country": "CHN",
                "horizon": 0,
                "estimate": float(row["cum_diesel_policy_gap_cny_t"]),
                "std_error": np.nan,
                "model": "policy_price_layer",
                "specification": f"cumulative diesel policy gap through {row['period']}",
                "n": 1,
            }
        )
    result = pd.DataFrame(rows)
    save_csv(result, "q3_robustness.csv")
    return result


def plot_pass_through(pass_through: pd.DataFrame) -> None:
    if pass_through.empty:
        return
    frame = pass_through.loc[pass_through["horizon"].eq(6)].copy()
    if "included_in_main_comparison" in frame:
        frame = frame.loc[bool_series(frame["included_in_main_comparison"])].copy()
    frame["country_label"] = frame["country"].map(COUNTRY_LABEL_ZH).fillna(frame["country"])
    frame["err_low"] = frame["response"] - frame["lower_95"]
    frame["err_high"] = frame["upper_95"] - frame["response"]
    color_cycle = [PALETTE["gold"], PALETTE["olive"], PALETTE["rose"], PALETTE["slate"], PALETTE["sand"], PALETTE["blue_light"]]
    colors = [color_cycle[idx % len(color_cycle)] for idx in range(len(frame))]
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    ax.bar(
        frame["country_label"],
        frame["response"],
        color=colors,
        edgecolor="white",
        linewidth=0.8,
        width=0.62,
        yerr=[frame["err_low"], frame["err_high"]],
        error_kw={"ecolor": PALETTE["ink"], "elinewidth": 0.8, "capsize": 3},
    )
    ax.axhline(0, color=PALETTE["muted"], linewidth=0.8)
    style_axis(ax, ylabel="累计传导系数")
    finish_figure(
        fig,
        title="问题三：六个月燃油价格传导率",
        subtitle="仅纳入覆盖充分的可观测或官方受管制零售汽油价格；中国覆盖不足时不参与主排名。",
        source="来源：欧盟周度油价公报、日本METI、韩国KOSIS/KNOC、北京市发改委与 FRED；由 code/problem3/run_q3.py 生成。",
        rect=(0.10, 0.13, 0.98, 0.84),
    )
    save_figure(fig, FIGURES_DIR / "q3_pass_through_6m")
    plt.close(fig)


def plot_panel_irf(panel_irf: pd.DataFrame) -> None:
    if panel_irf.empty:
        return
    frame = panel_irf.loc[panel_irf["outcome"].eq("fuel")].copy()
    if frame.empty:
        frame = panel_irf.copy()
    fig, ax = plt.subplots(figsize=(8.8, 5.1))
    style_map = {
        "CHN": (PALETTE["blue"], "solid", "o"),
        "DEU": (PALETTE["gold"], (0, (4, 2)), "s"),
        "FRA": (PALETTE["olive"], (0, (2, 2)), "^"),
        "ITA": (PALETTE["rose"], (0, (1, 2)), "D"),
        "ESP": (PALETTE["slate"], (0, (6, 2)), "v"),
        "JPN": (PALETTE["sand"], (0, (3, 1, 1, 1)), "P"),
        "KOR": (PALETTE["blue_light"], (0, (1, 1)), "X"),
    }
    for country in COUNTRY_ORDER:
        sub = frame.loc[frame["country"].eq(country)].sort_values("horizon")
        if sub.empty:
            continue
        color, linestyle, marker = style_map.get(country, (PALETTE["muted"], "solid", "o"))
        ax.plot(sub["horizon"], sub["response"], color=color, linestyle=linestyle, marker=marker, label=COUNTRY_LABEL_ZH.get(country, country))
    ax.axhline(0, color=PALETTE["muted"], linewidth=0.8)
    style_axis(ax, xlabel="油价冲击后月份", ylabel="响应")
    ax.legend(loc="upper left", ncol=4, handlelength=2.6)
    finish_figure(
        fig,
        title="问题三：跨国面板 LP 响应",
        subtitle="完整年月固定效应吸收共同冲击，因此曲线表示国家相对响应差异；燃油主图仅纳入覆盖充分国家。",
        source="来源：model_country_monthly.csv 与 q1_monthly_shocks.csv；由 code/problem3/run_q3.py 生成。",
    )
    save_figure(fig, FIGURES_DIR / "q3_panel_irf")
    plt.close(fig)


def plot_policy(counterfactual: pd.DataFrame) -> None:
    if counterfactual.empty:
        return
    frame = counterfactual.copy()
    x = np.arange(len(frame))
    fig, ax = plt.subplots(figsize=(7.8, 4.8))
    ax.plot(x, frame["actual"], marker="o", color=PALETTE["blue"], label="政策调整后官方零售价")
    ax.plot(x, frame["prediction"], marker="s", color=PALETTE["gold"], linestyle=(0, (4, 2)), label="无临时调控规则路径")
    ax.fill_between(x, frame["actual"], frame["prediction"], color=PALETTE["gold_light"], alpha=0.26, linewidth=0)
    ax.set_xticks(x)
    ax.set_xticklabels(frame["period"])
    for tick, row in enumerate(frame.itertuples(index=False)):
        if getattr(row, "cumulative_gasoline_gap_cny_t") > 0:
            label = f"累计差额 {row.cumulative_gasoline_gap_cny_t:.0f}"
            if getattr(row, "incremental_gasoline_gap_cny_t") > 0 and row.period == "2026-04":
                label = f"累计差额 {row.cumulative_gasoline_gap_cny_t:.0f}\n4月新增 {row.incremental_gasoline_gap_cny_t:.0f}"
            ax.text(tick, max(row.actual, row.prediction), label, ha="center", va="bottom", fontsize=8.4, color=PALETTE["muted"])
    style_axis(ax, ylabel="元/吨")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=2, handlelength=2.6)
    finish_figure(
        fig,
        title="问题三：中国成品油调控政策情景",
        subtitle="阴影代表累计政策差额加回官方受管制汽油标准品价格；宏观传播见 q3_policy_macro_counterfactual.csv。",
        source="来源：北京市发改委92号汽油价格公告与国家发展改革委调价事件；由 code/problem3/run_q3.py 生成。",
        rect=(0.10, 0.13, 0.98, 0.94),
    )
    save_figure(fig, FIGURES_DIR / "q3_policy_counterfactual")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plots-only", action="store_true", help="Regenerate Q3 figures from saved result tables.")
    args = parser.parse_args(argv)

    np.random.seed(RANDOM_SEED)
    apply_paper_style()
    ensure_dirs()
    if args.plots_only:
        pass_through = read_csv_result("q3_country_pass_through.csv")
        panel_irf = read_csv_result("q3_panel_irf.csv")
        counterfactual = read_csv_result("q3_policy_counterfactual.csv")
        plot_pass_through(pass_through)
        plot_panel_irf(panel_irf)
        plot_policy(counterfactual)
        print(json.dumps({"status": "PASS", "mode": "plots-only", "figures": 3}, ensure_ascii=False, indent=2))
        return 0

    from linearmodels.panel.utility import AbsorbingEffectWarning

    warnings_log: list[dict[str, Any]] = []
    panel = pd.read_csv(PROCESSED_DIR / "model_country_monthly.csv")
    panel["fuel_log"] = log_positive(panel["fuel_price_local"])
    py_warnings.filterwarnings("ignore", category=AbsorbingEffectWarning)
    pass_through = fit_country_pass_through(panel, warnings_log)
    panel_irf = fit_panel_lp(panel, warnings_log)
    buffer_irf = fit_buffer_interactions(panel, warnings_log)
    counterfactual = policy_counterfactual(panel, warnings_log)
    macro_counterfactual = read_csv_result("q3_policy_macro_counterfactual.csv")
    resilience = build_resilience_metrics(pass_through, panel_irf, macro_counterfactual)
    robustness = robustness_checks(panel, warnings_log)
    plot_pass_through(pass_through)
    plot_panel_irf(panel_irf)
    plot_policy(counterfactual)

    summary = pd.DataFrame(
        [
            {
                "component": "CountryPassThrough",
                "rows": len(pass_through),
                "status": "PASS" if len(pass_through) else "WARN",
                "note": "main ranking includes China only after the official regulated retail-price series reaches minimum coverage; distributed lag, 1/3/6 month cumulative response",
            },
            {
                "component": "PanelLP",
                "rows": len(panel_irf),
                "status": "PASS" if len(panel_irf) else "WARN",
                "note": "fuel LP excludes countries without sufficient official/observed retail-price coverage; country FE and full year-month FE absorb common shocks",
            },
            {
                "component": "BufferInteractions",
                "rows": len(buffer_irf),
                "status": "PASS" if len(buffer_irf) else "WARN",
                "note": "Shock×fuel_price_regulation with country FE and full year-month FE; interprets buffer differences, not absolute China ranking",
            },
            {
                "component": "ChinaPolicyCounterfactual",
                "rows": len(counterfactual),
                "status": "PASS" if len(counterfactual) and len(macro_counterfactual) else "WARN",
                "note": "official regulated finished-fuel price layer is used; macro propagation remains conditional until enough official China price history is available",
            },
            {
                "component": "ResilienceMetrics",
                "rows": len(resilience),
                "status": "PASS" if len(resilience) else "WARN",
                "note": "fuel, CPI, industrial-activity and policy-scenario metrics with China-relative judgement",
            },
            {
                "component": "Robustness",
                "rows": len(robustness),
                "status": "PASS" if len(robustness) else "WARN",
                "note": "leave-one-country, USD Brent and diesel policy-layer checks",
            },
        ]
    )
    save_csv(summary, "q3_summary.csv")
    payload = {
        "status": "PASS" if len(pass_through) and len(panel_irf) and len(buffer_irf) and len(counterfactual) and len(macro_counterfactual) and len(resilience) else "CONDITIONAL",
        "execution_status": "PASS" if len(pass_through) and len(panel_irf) and len(counterfactual) else "WARN",
        "evidence_status": str(resilience["overall_china_resilience_judgement"].dropna().iloc[0]) if "overall_china_resilience_judgement" in resilience and not resilience["overall_china_resilience_judgement"].dropna().empty else "INCONCLUSIVE",
        "allowed_claims": [
            "China enters the main fuel comparison only through an official regulated fuel-price layer",
            "Panel LP coefficients are relative to China under full year-month fixed effects",
            "Policy counterfactuals remove 2026 temporary-control gaps on the regulated finished-fuel price layer and propagate to PPI/CPI/IAV",
        ],
        "forbidden_claims": [
            "China is better solely because Brent-CNY proxy pass-through is lower",
            "fuel price smoothing is welfare-improving without considering cumulative policy gap costs",
            "fuel_price_regulation interaction is a general causal effect when China is the single strong treatment country",
        ],
        "random_seed": RANDOM_SEED,
        "comparability_guardrail": "China uses the official regulated fuel-price layer when available, but it enters the main cross-country fuel ranking only after the official series has sufficient history.",
        "warnings": warnings_log,
        "rows": {
            "q3_country_pass_through.csv": int(len(pass_through)),
            "q3_panel_irf.csv": int(len(panel_irf)),
            "q3_buffer_interactions.csv": int(len(buffer_irf)),
            "q3_policy_counterfactual.csv": int(len(counterfactual)),
            "q3_policy_macro_counterfactual.csv": int(len(macro_counterfactual)),
            "q3_resilience_metrics.csv": int(len(resilience)),
            "q3_robustness.csv": int(len(robustness)),
        },
    }
    (RESULTS_DIR / "q3_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
