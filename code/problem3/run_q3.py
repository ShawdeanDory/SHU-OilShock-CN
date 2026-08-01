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
POLICY_BOOTSTRAP_REPS = 2000
POLICY_BOOTSTRAP_BLOCK = 6


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
    for outcome in ["cpi", "ip"]:
        outcome_panel = panel.copy()
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
    """Fail closed while the annual structural-buffer table remains unaudited."""
    buffers = ["oil_import_dependency", "oil_intensity", "import_source_hhi", "fuel_price_regulation"]
    status = pd.DataFrame(
        [
            {
                "buffer": buffer,
                "data_status": "FAIL_FOR_MAIN_UNAUDITED_PROXY",
                "quantitative_result_released": False,
                "reason": "country_policy_buffers_annual.csv is a normalized proxy pending audited official exports",
                "required_replacement": "country-year raw values, formula, official URL/table id, download date and file hash",
            }
            for buffer in buffers
        ]
    )
    save_csv(status, "q3_buffer_data_status.csv")
    columns = [
        "outcome",
        "buffer",
        "horizon",
        "estimate",
        "std_error",
        "lower_95",
        "upper_95",
        "shock",
        "model",
        "data_status",
    ]
    result = pd.DataFrame(columns=columns)
    save_csv(result, "q3_buffer_interactions.csv")
    warnings_log.append(
        {
            "code": "q3_buffer_quantitative_results_withheld",
            "message": "Continuous buffer interactions were withheld because the country-year table is an unaudited proxy.",
        }
    )
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
    kernel_rows: list[dict[str, Any]] = []
    covariance_rows: list[dict[str, Any]] = []
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
        param_terms = ["const"] + lag_terms + [f"{outcome}_lag1", "GPR"]
        kernel_row = {
            "outcome": outcome,
            "outcome_label": label,
            "sample_start": usable["period"].iloc[0],
            "sample_end": usable["period"].iloc[-1],
            "n": int(len(usable)),
            "model": "China_fuel_to_macro_ARDL",
            "specification": "macro yoy outcome on regulated gasoline log-return lags 0..6, lagged outcome and GPR; HAC(6)",
            "fuel_to_macro_cumulative_elasticity": estimate,
        }
        for lag in range(7):
            term = f"fuel_log_return_lag{lag}"
            kernel_row[f"beta_fuel_lag{lag}"] = float(fit.params[term])
            kernel_row[f"se_fuel_lag{lag}"] = float(fit.bse[term])
        kernel_row["phi_outcome_lag1"] = float(fit.params[f"{outcome}_lag1"])
        kernel_row["se_outcome_lag1"] = float(fit.bse[f"{outcome}_lag1"])
        kernel_row["gpr_coefficient"] = float(fit.params["GPR"])
        kernel_row["constant"] = float(fit.params["const"])
        kernel_rows.append(kernel_row)
        full_cov = fit.cov_params()
        for row_term in param_terms:
            for column_term in param_terms:
                covariance_rows.append(
                    {
                        "outcome": outcome,
                        "outcome_label": label,
                        "row_term": row_term,
                        "column_term": column_term,
                        "covariance": float(full_cov.loc[row_term, column_term]),
                        "model": "China_fuel_to_macro_ARDL",
                        "sample_start": usable["period"].iloc[0],
                        "sample_end": usable["period"].iloc[-1],
                        "n": int(len(usable)),
                    }
                )
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
    kernel_columns = [
        "outcome",
        "outcome_label",
        "sample_start",
        "sample_end",
        "n",
        "model",
        "specification",
        "fuel_to_macro_cumulative_elasticity",
        "beta_fuel_lag0",
        "beta_fuel_lag1",
        "beta_fuel_lag2",
        "beta_fuel_lag3",
        "beta_fuel_lag4",
        "beta_fuel_lag5",
        "beta_fuel_lag6",
        "phi_outcome_lag1",
        "gpr_coefficient",
        "constant",
        "se_fuel_lag0",
        "se_fuel_lag1",
        "se_fuel_lag2",
        "se_fuel_lag3",
        "se_fuel_lag4",
        "se_fuel_lag5",
        "se_fuel_lag6",
        "se_outcome_lag1",
    ]
    covariance_columns = [
        "outcome",
        "outcome_label",
        "row_term",
        "column_term",
        "covariance",
        "model",
        "sample_start",
        "sample_end",
        "n",
    ]
    save_csv(pd.DataFrame(kernel_rows, columns=kernel_columns), "q3_policy_macro_kernel.csv")
    save_csv(pd.DataFrame(covariance_rows, columns=covariance_columns), "q3_policy_macro_covariance.csv")
    return pd.DataFrame(rows)


def circular_block_indices(n: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    indices: list[int] = []
    while len(indices) < n:
        start = int(rng.integers(0, n))
        indices.extend((start + offset) % n for offset in range(block_length))
    return np.asarray(indices[:n], dtype=int)


def policy_macro_model_frames() -> dict[str, tuple[pd.DataFrame, list[str]]]:
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
    model_frames: dict[str, tuple[pd.DataFrame, list[str]]] = {}
    for outcome in ["china_ppi_yoy_pct", "china_cpi_yoy_pct", "china_iav_yoy_pct"]:
        frame[f"{outcome}_lag1"] = frame[outcome].shift(1)
        regressors = [f"fuel_log_return_lag{lag}" for lag in range(7)] + [f"{outcome}_lag1", "GPR"]
        usable = frame.dropna(subset=[outcome] + regressors).copy()
        model_frames[outcome] = (usable[["period", outcome] + regressors], regressors)
    return model_frames


def joint_block_bootstrap_macro_draws(warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    """Use the same circular time blocks for the PPI, CPI and IAV equations."""
    model_frames = policy_macro_model_frames()
    common_periods = sorted(
        set.intersection(*(set(frame["period"].astype(str)) for frame, _ in model_frames.values()))
    )
    if len(common_periods) < 48:
        raise ValueError("Q3 joint policy bootstrap has fewer than 48 common monthly observations.")
    aligned: dict[str, tuple[pd.DataFrame, list[str]]] = {}
    for outcome, (frame, regressors) in model_frames.items():
        aligned_frame = frame.loc[frame["period"].isin(common_periods)].set_index("period").loc[common_periods].reset_index()
        aligned[outcome] = (aligned_frame, regressors)
    rng = np.random.default_rng(RANDOM_SEED + 31)
    rows: list[dict[str, Any]] = []
    accepted = 0
    attempts = 0
    max_attempts = int(POLICY_BOOTSTRAP_REPS * 1.20)
    while accepted < POLICY_BOOTSTRAP_REPS and attempts < max_attempts:
        attempts += 1
        sampled = circular_block_indices(len(common_periods), POLICY_BOOTSTRAP_BLOCK, rng)
        draw_rows: list[dict[str, Any]] = []
        valid = True
        for outcome, (frame, regressors) in aligned.items():
            sample = frame.iloc[sampled]
            x = sm.add_constant(sample[regressors].astype(float), has_constant="add")
            try:
                fit = sm.OLS(sample[outcome].astype(float), x).fit()
            except (ValueError, np.linalg.LinAlgError):
                valid = False
                break
            phi = float(fit.params[f"{outcome}_lag1"])
            betas = [float(fit.params[f"fuel_log_return_lag{lag}"]) for lag in range(7)]
            if not np.isfinite([*betas, phi]).all() or abs(phi) >= 0.995:
                valid = False
                break
            draw_rows.append(
                {
                    "draw": accepted,
                    "outcome": outcome,
                    **{f"beta_fuel_lag{lag}": betas[lag] for lag in range(7)},
                    "phi_outcome_lag1": phi,
                    "common_sample_start": common_periods[0],
                    "common_sample_end": common_periods[-1],
                    "common_n": len(common_periods),
                    "block_length": POLICY_BOOTSTRAP_BLOCK,
                }
            )
        if valid:
            rows.extend(draw_rows)
            accepted += 1
    if accepted != POLICY_BOOTSTRAP_REPS:
        raise ValueError(f"Q3 joint policy bootstrap accepted {accepted}/{POLICY_BOOTSTRAP_REPS} required draws.")
    warnings_log.append(
        {
            "code": "q3_policy_joint_bootstrap",
            "message": f"Accepted {accepted} joint three-equation moving-block draws from {attempts} attempts.",
        }
    )
    result = pd.DataFrame(rows)
    save_csv(result, "q3_policy_macro_bootstrap_draws.csv")
    return result


def dynamic_macro_gap(fuel_return_gap: np.ndarray, beta: np.ndarray, phi: float) -> np.ndarray:
    result = np.zeros(len(fuel_return_gap), dtype=float)
    for t in range(len(fuel_return_gap)):
        distributed = 0.0
        for lag in range(7):
            if t - lag >= 0:
                distributed += float(beta[lag]) * float(fuel_return_gap[t - lag])
        result[t] = distributed + (float(phi) * result[t - 1] if t > 0 else 0.0)
    return result


def validate_dynamic_macro_identity() -> None:
    fuel = np.array([0.10, 0.0, 0.0, 0.0], dtype=float)
    beta = np.array([1.0, 2.0, 3.0, 4.0, 0.0, 0.0, 0.0], dtype=float)
    phi = 0.5
    observed = dynamic_macro_gap(fuel, beta, phi)
    expected = np.array([0.10, 0.25, 0.425, 0.6125], dtype=float)
    if not np.allclose(observed, expected, atol=1e-12, rtol=1e-12):
        raise AssertionError("Q3 distributed-lag policy identity test failed.")


def policy_counterfactual(country_panel: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    official_path = PROCESSED_DIR / "china_regulated_gasoline_monthly.csv"
    if not official_path.exists():
        raise FileNotFoundError("china_regulated_gasoline_monthly.csv is required for the regulated-price proxy counterfactual.")
    official = pd.read_csv(official_path)
    policy = pd.read_csv(PROCESSED_DIR / "china_fuel_policy_monthly.csv")
    full_frame = official.merge(
        policy[["period", "gasoline_policy_gap_cny_t", "diesel_policy_gap_cny_t", "cum_gasoline_policy_gap_cny_t", "cum_diesel_policy_gap_cny_t"]],
        on="period",
        how="left",
        suffixes=("", "_policy"),
    )
    full_frame = full_frame.sort_values("period").copy()
    elasticities = china_fuel_to_macro_elasticities(warnings_log)
    validate_dynamic_macro_identity()
    bootstrap_draws = joint_block_bootstrap_macro_draws(warnings_log)
    full_frame["actual_log"] = log_positive(full_frame["china_regulated_gasoline_cny_per_ton"])
    full_frame["no_control_log"] = log_positive(full_frame["no_temporary_control_gasoline_cny_per_ton"])
    full_frame["actual_fuel_log_return"] = full_frame["actual_log"].diff()
    full_frame["no_control_fuel_log_return"] = full_frame["no_control_log"].diff()
    full_frame["fuel_return_gap"] = full_frame["no_control_fuel_log_return"] - full_frame["actual_fuel_log_return"]
    full_frame["fuel_return_gap"] = full_frame["fuel_return_gap"].fillna(0.0)
    frame = full_frame.loc[full_frame["period"].between("2026-02", "2026-06")].copy()
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
    frame["fuel_return_gap"] = full_frame.loc[frame.index, "fuel_return_gap"].to_numpy()
    macro_rows: list[dict[str, Any]] = []
    event_gap = frame["fuel_return_gap"].to_numpy(dtype=float)
    kernel = pd.read_csv(RESULTS_DIR / "q3_policy_macro_kernel.csv")
    for elastic in elasticities.to_dict("records"):
        outcome = str(elastic["outcome"])
        kernel_row = kernel.loc[kernel["outcome"].eq(outcome)].iloc[0]
        beta = np.array([float(kernel_row[f"beta_fuel_lag{lag}"]) for lag in range(7)], dtype=float)
        phi = float(kernel_row["phi_outcome_lag1"])
        point_path = dynamic_macro_gap(event_gap, beta, phi)
        outcome_draws = bootstrap_draws.loc[bootstrap_draws["outcome"].eq(outcome)].sort_values("draw")
        draw_paths = np.vstack(
            [
                dynamic_macro_gap(
                    event_gap,
                    np.array([float(row[f"beta_fuel_lag{lag}"]) for lag in range(7)], dtype=float),
                    float(row["phi_outcome_lag1"]),
                )
                for row in outcome_draws.to_dict("records")
            ]
        )
        for t, period_row in enumerate(frame.to_dict("records")):
            gap = float(point_path[t])
            lower, upper = np.quantile(draw_paths[:, t], [0.025, 0.975])
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
                    "fuel_return_gap": period_row["fuel_return_gap"],
                    "macro_counterfactual_gap_pctpt": gap,
                    "lower_95": float(lower),
                    "upper_95": float(upper),
                    "model": "China_proxy_fuel_dynamic_ARDL_counterfactual",
                    "horizon": t,
                    "specification": "monthly convolution of no-control minus actual proxy fuel returns through lags 0..6 with recursive outcome AR(1); joint three-equation circular block bootstrap",
                    "sample_start": elastic["sample_start"],
                    "sample_end": elastic["sample_end"],
                    "n": elastic["n"],
                    "price_layer_status": "regulated_gasoline_adjustment_index_proxy_with_2026_notice_gaps",
                    "evidence_status": "CONDITIONAL_DYNAMIC_PROXY_SCENARIO",
                    "bootstrap_reps": POLICY_BOOTSTRAP_REPS,
                    "bootstrap_block_length": POLICY_BOOTSTRAP_BLOCK,
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
        "fuel_return_gap",
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
        "bootstrap_reps",
        "bootstrap_block_length",
    ]
    macro_counterfactual = pd.DataFrame(macro_rows, columns=macro_columns)
    save_csv(macro_counterfactual, "q3_policy_macro_counterfactual.csv")
    cpi_macro = macro_counterfactual.loc[macro_counterfactual["outcome"].eq("china_cpi_yoy_pct"), ["period", "macro_counterfactual_gap_pctpt", "lower_95", "upper_95"]]
    frame = frame.drop(columns=[column for column in ["lower_95", "upper_95"] if column in frame.columns])
    frame = frame.merge(cpi_macro.rename(columns={"macro_counterfactual_gap_pctpt": "cpi_counterfactual_gap_pctpt"}), on="period", how="left")
    frame["model"] = "China_policy_counterfactual"
    frame["horizon"] = np.arange(len(frame), dtype=int)
    frame["specification"] = "add separately audited 2026 NDRC policy gaps to the reconstructed regulated-gasoline adjustment-index proxy; dynamic macro propagation is written to q3_policy_macro_counterfactual.csv"
    frame["evidence_status"] = np.where(frame["policy_adjusted_official_cny_t"].notna(), "CONDITIONAL_PROXY_PRICE_LAYER", "CONDITIONAL_DATA_COVERAGE")
    frame["price_layer_status"] = "regulated_gasoline_adjustment_index_proxy_with_2026_notice_gaps"
    frame["sample_start"] = "2013-03"
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
            "fuel_return_gap",
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
    """Report exactly three economic dimensions and fail closed on invalid joint intervals."""
    rows: list[dict[str, Any]] = []
    fuel_h6 = pass_through.loc[pass_through["horizon"].eq(6)].copy()
    china = fuel_h6.loc[fuel_h6["country"].eq("CHN")]
    controls = fuel_h6.loc[fuel_h6["country"].isin(MAIN_CONTROL_COUNTRIES)]
    rows.append(
        {
            "dimension": "fuel_price",
            "metric": "six_month_pass_through_proxy_sensitivity",
            "horizon": 6,
            "china_value": float(china["response"].iloc[0]) if not china.empty else np.nan,
            "control_median": float(controls["response"].median()) if not controls.empty else np.nan,
            "china_vs_control_median_diff": np.nan,
            "diff_lower_95": np.nan,
            "diff_upper_95": np.nan,
            "judgement": "CONDITIONAL_PROXY",
            "interpretation": "China is reported as an adjustment-index proxy sensitivity and is excluded from the formal retail-price ranking; no invalid median interval is constructed.",
        }
    )
    for outcome, dimension in [("cpi", "consumer_prices"), ("ip", "industrial_activity")]:
        sub = panel_irf.loc[panel_irf["outcome"].eq(outcome)].copy()
        if sub.empty:
            continue
        grouped = sub.groupby("horizon", as_index=False).agg(median_relative_response=("response", "median"))
        row = grouped.loc[grouped["median_relative_response"].abs().idxmax()]
        rows.append(
            {
                "dimension": dimension,
                "metric": f"control_minus_china_{outcome}_relative_response",
                "horizon": int(row["horizon"]),
                "china_value": np.nan,
                "control_median": float(row["median_relative_response"]),
                "china_vs_control_median_diff": float(row["median_relative_response"]),
                "diff_lower_95": np.nan,
                "diff_upper_95": np.nan,
                "judgement": "INCONCLUSIVE",
                "interpretation": "Only the control-minus-China relative point estimate is shown; China is not set to zero and no confidence claim is made without a joint country-time bootstrap.",
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
    overall = "INCONCLUSIVE"
    if not result.empty:
        result["overall_china_resilience_judgement"] = overall
    save_csv(result, "q3_resilience_metrics.csv")
    return result


def robustness_checks(panel: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    main_panel = panel.loc[bool_series(panel["included_in_main_comparison"])].copy() if "included_in_main_comparison" in panel else panel.copy()
    main_countries = [country for country in COUNTRY_ORDER if country in set(main_panel["country"])]
    warnings_log.append(
        {
            "code": "q3_fuel_panel_leave_one_withheld",
            "message": "Fuel panel leave-one-country inference is withheld because China is a proxy and excluded from the formal price-level panel.",
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
    ax.plot(x, frame["actual"], marker="o", color=PALETTE["blue"], label="政策调整后调价指数代理")
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
        subtitle="阴影代表将单独核验的2026政策差额加回历史调价指数代理；宏观传播为条件动态情景。",
        source="来源：国家发展改革委2026调价公告、公开历史调价镜像及处理说明；由 code/problem3/run_q3.py 生成。",
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
                "note": "formal ranking covers six comparable control countries; China adjustment-index proxy is retained only as sensitivity",
            },
            {
                "component": "PanelLP",
                "rows": len(panel_irf),
                "status": "PASS" if len(panel_irf) else "WARN",
                "note": "CPI and industrial-activity LP coefficients are control-country minus China relative responses with country and full year-month fixed effects",
            },
            {
                "component": "BufferInteractions",
                "rows": len(buffer_irf),
                "status": "WITHHELD_UNAUDITED_PROXY",
                "note": "continuous buffer interactions are not released until the country-year source table is independently auditable",
            },
            {
                "component": "ChinaPolicyCounterfactual",
                "rows": len(counterfactual),
                "status": "PASS" if len(counterfactual) and len(macro_counterfactual) else "WARN",
                "note": "2026 notice gaps are propagated through a dynamic ARDL kernel on a reconstructed adjustment-index proxy with joint time-block uncertainty",
            },
            {
                "component": "ResilienceMetrics",
                "rows": len(resilience),
                "status": "PASS" if len(resilience) else "WARN",
                "note": "exactly three economic dimensions; overall judgement fails closed because the fuel layer is a proxy and joint cross-country intervals are not claimed",
            },
            {
                "component": "Robustness",
                "rows": len(robustness),
                "status": "PASS" if len(robustness) else "WARN",
                "note": "USD-Brent sensitivity and diesel policy-layer checks; invalid fuel panel leave-one inference is withheld",
            },
        ]
    )
    save_csv(summary, "q3_summary.csv")
    payload = {
        "status": "CONDITIONAL",
        "execution_status": "PASS" if len(pass_through) and len(panel_irf) and len(counterfactual) else "WARN",
        "evidence_status": str(resilience["overall_china_resilience_judgement"].dropna().iloc[0]) if "overall_china_resilience_judgement" in resilience and not resilience["overall_china_resilience_judgement"].dropna().empty else "INCONCLUSIVE",
        "allowed_claims": [
            "China historical fuel pass-through is a proxy sensitivity and is excluded from the formal retail-price ranking",
            "Panel LP coefficients are relative to China under full year-month fixed effects",
            "The 2026 conditional policy scenario propagates proxy fuel-return gaps dynamically through PPI/CPI/IAV kernels with a common time-block bootstrap",
        ],
        "forbidden_claims": [
            "China is better solely because Brent-CNY proxy pass-through is lower",
            "fuel price smoothing is welfare-improving without considering cumulative policy gap costs",
            "unaudited structural-buffer proxies support quantitative policy-interaction effects",
        ],
        "random_seed": RANDOM_SEED,
        "comparability_guardrail": "China uses a reconstructed regulated-gasoline adjustment-index proxy and is excluded from the formal cross-country retail-price ranking; 2026 policy notices are audited separately.",
        "warnings": warnings_log,
        "rows": {
            "q3_country_pass_through.csv": int(len(pass_through)),
            "q3_panel_irf.csv": int(len(panel_irf)),
            "q3_buffer_interactions.csv": int(len(buffer_irf)),
            "q3_buffer_data_status.csv": 4,
            "q3_policy_counterfactual.csv": int(len(counterfactual)),
            "q3_policy_macro_counterfactual.csv": int(len(macro_counterfactual)),
            "q3_policy_macro_bootstrap_draws.csv": POLICY_BOOTSTRAP_REPS * 3,
            "q3_resilience_metrics.csv": int(len(resilience)),
            "q3_robustness.csv": int(len(robustness)),
        },
    }
    (RESULTS_DIR / "q3_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
