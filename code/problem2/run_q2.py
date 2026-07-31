"""Question 2: transmission of oil shocks to China's macro variables."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
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
BOOTSTRAP_REPS = 2000
SHOCK_SPECS = {
    "supply_shock": "adverse_supply_shock_from_EIA_recursive_decomposition",
    "aggregate_demand_shock": "aggregate_demand_shock_from_EIA_recursive_decomposition",
    "oil_specific_risk_shock": "oil_specific_risk_shock_from_EIA_recursive_decomposition",
    "OilShock": "reduced_form_ARX_oil_price_innovation_robustness",
}


OUTCOME_SPECS = {
    "china_iav_yoy_pct": "中国规模以上工业增加值同比，百分点",
    "china_ppi_yoy_pct": "中国PPI同比，百分点",
    "china_cpi_yoy_pct": "中国CPI同比，百分点",
    "china_fx_log_change_pct": "人民币兑美元月度对数变化，百分点",
}


def ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)


def save_csv(frame: pd.DataFrame, filename: str) -> Path:
    path = RESULTS_DIR / filename
    frame.to_csv(path, index=False, encoding="utf-8")
    return path


def available_outcomes(frame: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> list[str]:
    outcomes: list[str] = []
    for column, label in OUTCOME_SPECS.items():
        if column not in frame.columns or frame[column].dropna().shape[0] < 48:
            warnings_log.append({"code": "q2_outcome_skipped", "message": f"{label} skipped: insufficient usable monthly history."})
            continue
        outcomes.append(column)
    return outcomes


def available_shocks(frame: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> list[str]:
    shocks: list[str] = []
    for column in SHOCK_SPECS:
        if column not in frame.columns or frame[column].dropna().shape[0] < 36:
            warnings_log.append({"code": "q2_shock_skipped", "message": f"{column} skipped: insufficient usable shock history."})
            continue
        shocks.append(column)
    return shocks


def main_shock_column(frame: pd.DataFrame) -> str:
    for column in ["oil_specific_risk_shock", "supply_shock", "OilShock"]:
        if column in frame.columns and frame[column].dropna().shape[0] >= 36:
            return column
    return "OilShock"


def add_month_dummies(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["month"] = pd.to_datetime(result["period"] + "-01").dt.month
    dummies = pd.get_dummies(result["month"], prefix="month", drop_first=True, dtype=float)
    return pd.concat([result, dummies], axis=1)


def fit_ols_hac(y: pd.Series, x: pd.DataFrame, maxlags: int) -> Any:
    x = sm.add_constant(x, has_constant="add")
    return sm.OLS(y, x).fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})


def make_lags(frame: pd.DataFrame, column: str, max_lag: int, prefix: str | None = None) -> pd.DataFrame:
    result = frame.copy()
    prefix = prefix or column
    for lag in range(max_lag + 1):
        result[f"{prefix}_lag{lag}"] = result[column].shift(lag)
    return result


def quarter_label(dates: pd.Series) -> pd.Series:
    periods = pd.PeriodIndex(pd.to_datetime(dates), freq="Q")
    return pd.Series([f"{period.year}-Q{period.quarter}" for period in periods], index=dates.index)


def ardl_baseline(monthly: pd.DataFrame, outcomes: list[str], warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    base = add_month_dummies(monthly)
    shock_col = main_shock_column(base)
    month_cols = [column for column in base.columns if column.startswith("month_") and column != "month_end"]
    control_cols = ["usd_broad_index_log_return", "GPR_z", "covid_phase"] + month_cols
    for outcome in outcomes:
        frame = make_lags(base, shock_col, 6, prefix="shock")
        frame[f"{outcome}_lag1"] = frame[outcome].shift(1)
        regressors = [f"shock_lag{lag}" for lag in range(7)] + [f"{outcome}_lag1"] + control_cols
        usable = frame.dropna(subset=[outcome] + regressors).copy()
        if len(usable) < len(regressors) + 12:
            warnings_log.append({"code": "q2_ardl_skipped", "message": f"{outcome}: too few observations after lags."})
            continue
        fit = fit_ols_hac(usable[outcome], usable[regressors].astype(float), maxlags=6)
        lag_terms = [f"shock_lag{lag}" for lag in range(7)]
        cumulative = float(fit.params[lag_terms].sum())
        cov = fit.cov_params().loc[lag_terms, lag_terms]
        cumulative_se = float(np.sqrt(np.ones(len(lag_terms)) @ cov.to_numpy() @ np.ones(len(lag_terms))))
        y_lag = float(fit.params.get(f"{outcome}_lag1", np.nan))
        long_run = cumulative / (1.0 - y_lag) if np.isfinite(y_lag) and abs(1.0 - y_lag) > 1e-6 else np.nan
        long_run_se = np.nan
        if np.isfinite(long_run):
            lr_terms = lag_terms + [f"{outcome}_lag1"]
            lr_cov = fit.cov_params().loc[lr_terms, lr_terms].to_numpy()
            grad = np.array([1.0 / (1.0 - y_lag)] * len(lag_terms) + [cumulative / (1.0 - y_lag) ** 2])
            long_run_se = float(np.sqrt(grad @ lr_cov @ grad))
        for term_type, estimate, se in [
            ("short_run_lag0", float(fit.params["shock_lag0"]), float(fit.bse["shock_lag0"])),
            ("cumulative_lag0_6", cumulative, cumulative_se),
            ("long_run_multiplier", long_run, long_run_se),
        ]:
            rows.append(
                {
                    "outcome": outcome,
                    "term": term_type,
                    "estimate": estimate,
                    "std_error": se,
                    "lower_80": estimate - norm.ppf(0.90) * se if np.isfinite(se) else np.nan,
                    "upper_80": estimate + norm.ppf(0.90) * se if np.isfinite(se) else np.nan,
                    "lower_95": estimate - norm.ppf(0.975) * se if np.isfinite(se) else np.nan,
                    "upper_95": estimate + norm.ppf(0.975) * se if np.isfinite(se) else np.nan,
                    "pvalue": float(fit.pvalues["shock_lag0"]) if term_type == "short_run_lag0" else np.nan,
                    "model": "ARDL",
                    "horizon": 0,
                    "shock": shock_col,
                    "specification": f"y_lag1 + {shock_col} lags 0..6 + USD + GPR + month + COVID",
                    "sample_start": usable["period"].iloc[0],
                    "sample_end": usable["period"].iloc[-1],
                    "n": int(len(usable)),
                }
            )
    result = pd.DataFrame(rows)
    save_csv(result, "q2_ardl_baseline.csv")
    return result


def block_bootstrap_coefs(
    usable: pd.DataFrame,
    y_col: str,
    x_cols: list[str],
    term: str,
    maxlags: int,
    block_len: int = 12,
    reps: int = BOOTSTRAP_REPS,
) -> np.ndarray:
    rng = np.random.default_rng(RANDOM_SEED + maxlags + len(usable))
    n = len(usable)
    starts = np.arange(0, max(1, n - block_len + 1))
    values: list[float] = []
    for _ in range(reps):
        take: list[int] = []
        while len(take) < n:
            start = int(rng.choice(starts))
            take.extend(range(start, min(start + block_len, n)))
        sample = usable.iloc[take[:n]].copy()
        x = sm.add_constant(sample[x_cols].astype(float), has_constant="add").to_numpy(dtype=float)
        y = sample[y_col].to_numpy(dtype=float)
        if np.linalg.matrix_rank(x) < x.shape[1] or not np.isfinite(x).all() or not np.isfinite(y).all():
            values.append(np.nan)
            continue
        beta = np.linalg.lstsq(x, y, rcond=None)[0]
        columns = ["const"] + x_cols
        values.append(float(beta[columns.index(term)]))
    return np.asarray(values, dtype=float)


def joint_lp_bootstrap(
    usable: pd.DataFrame,
    target_cols: list[str],
    regressors: list[str],
    term: str,
    block_len: int = 12,
    reps: int = BOOTSTRAP_REPS,
) -> tuple[np.ndarray, np.ndarray]:
    x = sm.add_constant(usable[regressors].astype(float), has_constant="add").to_numpy(dtype=float)
    y = usable[target_cols].to_numpy(dtype=float)
    if np.linalg.matrix_rank(x) < x.shape[1] or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise np.linalg.LinAlgError("LP design is rank deficient or non-finite.")
    columns = ["const"] + regressors
    term_idx = columns.index(term)
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    point = beta[term_idx, :]
    rng = np.random.default_rng(RANDOM_SEED + len(usable) + len(regressors) + sum(ord(ch) for ch in term))
    n = len(usable)
    starts = np.arange(0, max(1, n - block_len + 1))
    boot = np.full((reps, len(target_cols)), np.nan, dtype=float)
    for rep in range(reps):
        take: list[int] = []
        while len(take) < n:
            start = int(rng.choice(starts))
            take.extend(range(start, min(start + block_len, n)))
        idx = take[:n]
        xs = x[idx, :]
        ys = y[idx, :]
        if not np.isfinite(xs).all() or not np.isfinite(ys).all():
            continue
        boot[rep, :] = np.linalg.lstsq(xs, ys, rcond=None)[0][term_idx, :]
    success = np.isfinite(boot).all(axis=1)
    if success.sum() < max(100, int(0.80 * reps)):
        raise RuntimeError(f"LP bootstrap finite-draw rate too low: {success.mean():.3f}")
    return point, boot[success, :]


def local_projection(monthly: pd.DataFrame, outcomes: list[str], warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    base = add_month_dummies(monthly)
    base["fx_level_pct"] = np.log(base["cny_per_usd"]) * 100.0
    month_cols = [column for column in base.columns if column.startswith("month_") and column != "month_end"]
    shocks = available_shocks(base, warnings_log)
    for shock_col in shocks:
        base[f"{shock_col}_lag1"] = base[shock_col].shift(1)

    for outcome in outcomes:
        for shock_col in shocks:
            frame = base.copy()
            frame[f"{outcome}_lag1"] = frame[outcome].shift(1)
            target_cols: list[str] = []
            for horizon in range(13):
                target_col = f"target_h{horizon}"
                target_cols.append(target_col)
                if outcome == "china_fx_log_change_pct":
                    frame[target_col] = frame["fx_level_pct"].shift(-horizon) - frame["fx_level_pct"].shift(1)
                else:
                    frame[target_col] = frame[outcome].shift(-horizon)
            regressors = [
                shock_col,
                f"{outcome}_lag1",
                f"{shock_col}_lag1",
                "usd_broad_index_log_return",
                "GPR_z",
                "covid_phase",
            ] + month_cols
            usable = frame.dropna(subset=target_cols + regressors).copy()
            if len(usable) < len(regressors) + 16:
                warnings_log.append({"code": "q2_lp_skipped", "message": f"{outcome} {shock_col}: too few observations for joint h=0..12 LP."})
                continue
            point, boot = joint_lp_bootstrap(usable, target_cols, regressors, shock_col)
            se = np.nanstd(boot, axis=0, ddof=1)
            lower_80, upper_80 = np.quantile(boot, [0.10, 0.90], axis=0)
            lower_95, upper_95 = np.quantile(boot, [0.025, 0.975], axis=0)
            t_boot = (boot - point) / se
            sup_t = np.nanquantile(np.nanmax(np.abs(t_boot), axis=1), 0.95)
            joint_lower = point - sup_t * se
            joint_upper = point + sup_t * se
            for horizon in range(13):
                bh = boot[:, horizon]
                p_boot = min(
                    1.0,
                    2.0
                    * min(
                        float((1 + np.sum(bh <= 0.0)) / (len(bh) + 1)),
                        float((1 + np.sum(bh >= 0.0)) / (len(bh) + 1)),
                    ),
                )
                rows.append(
                    {
                        "outcome": outcome,
                        "shock": shock_col,
                        "horizon": horizon,
                        "response": float(point[horizon]),
                        "std_error": float(se[horizon]),
                        "lower_80": float(lower_80[horizon]),
                        "upper_80": float(upper_80[horizon]),
                        "lower_95": float(lower_95[horizon]),
                        "upper_95": float(upper_95[horizon]),
                        "joint_lower_95": float(joint_lower[horizon]),
                        "joint_upper_95": float(joint_upper[horizon]),
                        "pvalue": float(p_boot),
                        "bootstrap_reps": int(len(boot)),
                        "model": "LocalProjection",
                        "specification": "joint h=0..12 LP with one moving-block bootstrap sample source; lagged outcome, lagged shock, USD, GPR, month and COVID controls",
                        "shock_identification": SHOCK_SPECS[shock_col],
                        "sample_start": usable["period"].iloc[0],
                        "sample_end": usable["period"].iloc[-1],
                        "n": int(len(usable)),
                    }
                )
    result = pd.DataFrame(rows)
    result = annotate_lp_inference(result)
    save_csv(result, "q2_irf.csv")
    return result


def benjamini_hochberg(pvalues: pd.Series) -> pd.Series:
    p = pd.to_numeric(pvalues, errors="coerce")
    q = pd.Series(np.nan, index=p.index, dtype=float)
    valid = p.dropna().sort_values()
    m = len(valid)
    if m == 0:
        return q
    adjusted = valid * m / np.arange(1, m + 1)
    adjusted = adjusted.iloc[::-1].cummin().iloc[::-1].clip(upper=1.0)
    q.loc[adjusted.index] = adjusted
    return q


def annotate_lp_inference(irf: pd.DataFrame) -> pd.DataFrame:
    if irf.empty:
        return irf
    result = irf.copy()
    result["ci95_contains_zero"] = result["lower_95"].le(0) & result["upper_95"].ge(0)
    if {"joint_lower_95", "joint_upper_95"}.issubset(result.columns):
        result["joint_ci95_contains_zero"] = result["joint_lower_95"].le(0) & result["joint_upper_95"].ge(0)
    else:
        result["joint_ci95_contains_zero"] = result["ci95_contains_zero"]
    result["pre_specified_horizon"] = result["horizon"].isin([0, 6, 12])
    result["fdr_qvalue"] = np.nan
    group_cols = ["outcome", "shock"] if "shock" in result.columns else ["outcome"]
    for _, group in result.groupby(group_cols):
        result.loc[group.index, "fdr_qvalue"] = benjamini_hochberg(group["pvalue"])
    result["fdr_significant_10pct"] = result["fdr_qvalue"].le(0.10)
    result["supports_growth_loss_language"] = (
        result["outcome"].isin(["china_iav_yoy_pct", "china_real_gdp_yoy_pct"])
        & result["response"].lt(0)
        & ~result["joint_ci95_contains_zero"]
    )
    return result


def asymmetry_check(monthly: pd.DataFrame, outcomes: list[str], warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    base = add_month_dummies(monthly)
    shock_col = main_shock_column(base)
    base["shock_pos"] = base[shock_col].clip(lower=0)
    base["shock_neg"] = base[shock_col].clip(upper=0)
    month_cols = [column for column in base.columns if column.startswith("month_") and column != "month_end"]
    for outcome in outcomes:
        frame = base.copy()
        frame[f"{outcome}_lag1"] = frame[outcome].shift(1)
        regressors = ["shock_pos", "shock_neg", f"{outcome}_lag1", "usd_broad_index_log_return", "GPR_z", "covid_phase"] + month_cols
        usable = frame.dropna(subset=[outcome] + regressors)
        if len(usable) < len(regressors) + 12:
            continue
        fit = fit_ols_hac(usable[outcome], usable[regressors].astype(float), maxlags=6)
        for term in ["shock_pos", "shock_neg"]:
            estimate = float(fit.params[term])
            se = float(fit.bse[term])
            rows.append(
                {
                    "outcome": outcome,
                    "term": term,
                    "shock": shock_col,
                    "estimate": estimate,
                    "std_error": se,
                    "lower_95": estimate - norm.ppf(0.975) * se,
                    "upper_95": estimate + norm.ppf(0.975) * se,
                    "model": "sign_asymmetry_DL",
                    "specification": f"positive and negative {shock_col} split; not a full NARDL/ECM",
                    "sample_start": usable["period"].iloc[0],
                    "sample_end": usable["period"].iloc[-1],
                    "n": int(len(usable)),
                }
            )
    result = pd.DataFrame(rows)
    save_csv(result, "q2_asymmetry.csv")
    return result


def lag_and_covid_robustness(monthly: pd.DataFrame, outcomes: list[str], warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    base_all = add_month_dummies(monthly)
    shock_col = main_shock_column(base_all)
    month_cols = [column for column in base_all.columns if column.startswith("month_") and column != "month_end"]
    for lag_max in [3, 6, 12]:
        for exclude_covid in [False, True]:
            base = base_all.loc[~base_all["covid_phase"].eq(1)].copy() if exclude_covid else base_all.copy()
            controls = ["usd_broad_index_log_return", "GPR_z"] + ([] if exclude_covid else ["covid_phase"]) + month_cols
            for outcome in outcomes:
                frame = make_lags(base, shock_col, lag_max, prefix="shock")
                frame[f"{outcome}_lag1"] = frame[outcome].shift(1)
                lag_terms = [f"shock_lag{lag}" for lag in range(lag_max + 1)]
                regressors = lag_terms + [f"{outcome}_lag1"] + controls
                usable = frame.dropna(subset=[outcome] + regressors)
                if len(usable) < len(regressors) + 12:
                    warnings_log.append(
                        {
                            "code": "q2_robustness_skipped",
                            "message": f"{outcome} lag={lag_max} exclude_covid={exclude_covid}: too few observations.",
                        }
                    )
                    continue
                fit = fit_ols_hac(usable[outcome], usable[regressors].astype(float), maxlags=lag_max)
                estimate = float(fit.params[lag_terms].sum())
                cov = fit.cov_params().loc[lag_terms, lag_terms]
                se = float(np.sqrt(np.ones(len(lag_terms)) @ cov.to_numpy() @ np.ones(len(lag_terms))))
                rows.append(
                    {
                        "outcome": outcome,
                        "shock": shock_col,
                        "lag_max": lag_max,
                        "exclude_covid": exclude_covid,
                        "estimate": estimate,
                        "std_error": se,
                        "lower_95": estimate - norm.ppf(0.975) * se,
                        "upper_95": estimate + norm.ppf(0.975) * se,
                        "model": "ARDL_robustness",
                        "specification": f"{shock_col} lags 0..{lag_max}; exclude_covid={exclude_covid}",
                        "sample_start": usable["period"].iloc[0],
                        "sample_end": usable["period"].iloc[-1],
                        "n": int(len(usable)),
                    }
                )
    result = pd.DataFrame(rows)
    save_csv(result, "q2_robustness.csv")
    return result


def gdp_validation(quarterly: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    frame = quarterly.copy()
    frame["gdp_lag1"] = frame["china_real_gdp_yoy_pct"].shift(1)
    shock_sum_col = "oil_specific_risk_shock_sum" if "oil_specific_risk_shock_sum" in frame.columns and frame["oil_specific_risk_shock_sum"].dropna().shape[0] >= 8 else "OilShock_sum"
    usable = frame.dropna(subset=["china_real_gdp_yoy_pct", "gdp_lag1", shock_sum_col, "GPR_z_mean"]) if "GPR_z_mean" in frame.columns else pd.DataFrame()
    if "GPR_z_mean" not in frame.columns:
        monthly = pd.read_csv(PROCESSED_DIR / "model_monthly_cn.csv")
        monthly["quarter"] = quarter_label(monthly["period"] + "-01")
        gpr_q = monthly.groupby("quarter", as_index=False).agg(GPR_z_mean=("GPR_z", "mean"))
        frame = frame.merge(gpr_q, on="quarter", how="left")
        usable = frame.dropna(subset=["china_real_gdp_yoy_pct", "gdp_lag1", shock_sum_col, "GPR_z_mean"])
    if len(usable) < 16:
        warnings_log.append({"code": "q2_gdp_validation_limited", "message": "Too few GDP validation observations after lags."})
        result = pd.DataFrame(
            [
                {
                    "outcome": "china_real_gdp_yoy_pct",
                    "model": "quarterly_validation",
                    "estimate": np.nan,
                    "std_error": np.nan,
                    "lower_95": np.nan,
                    "upper_95": np.nan,
                    "evidence_status": "INCONCLUSIVE",
                    "shock": shock_sum_col,
                    "correlation": float(frame[["china_real_gdp_yoy_pct", shock_sum_col]].dropna().corr().iloc[0, 1]) if frame[["china_real_gdp_yoy_pct", shock_sum_col]].dropna().shape[0] > 3 else np.nan,
                    "n": int(frame[["china_real_gdp_yoy_pct", shock_sum_col]].dropna().shape[0]),
                    "sample_start": "",
                    "sample_end": "",
                    "specification": "insufficient observations for regression; correlation shown if available",
                }
            ]
        )
        save_csv(result, "q2_gdp_validation.csv")
        return result
    regressors = [shock_sum_col, "gdp_lag1", "GPR_z_mean"]
    fit = fit_ols_hac(usable["china_real_gdp_yoy_pct"], usable[regressors].astype(float), maxlags=2)
    estimate = float(fit.params[shock_sum_col])
    se = float(fit.bse[shock_sum_col])
    lower_95 = estimate - norm.ppf(0.975) * se
    upper_95 = estimate + norm.ppf(0.975) * se
    result = pd.DataFrame(
        [
            {
                "outcome": "china_real_gdp_yoy_pct",
                "model": "quarterly_validation",
                "estimate": estimate,
                "std_error": se,
                "lower_80": estimate - norm.ppf(0.90) * se,
                "upper_80": estimate + norm.ppf(0.90) * se,
                "lower_95": lower_95,
                "upper_95": upper_95,
                "pvalue": float(fit.pvalues[shock_sum_col]),
                "evidence_status": "SUPPORTED" if lower_95 > 0 or upper_95 < 0 else "INCONCLUSIVE",
                "shock": shock_sum_col,
                "correlation": float(usable[["china_real_gdp_yoy_pct", shock_sum_col]].corr().iloc[0, 1]),
                "n": int(len(usable)),
                "sample_start": usable["quarter"].iloc[0],
                "sample_end": usable["quarter"].iloc[-1],
                "specification": f"GDP yoy on quarterly {shock_sum_col}, lagged GDP yoy and GPR",
            }
        ]
    )
    save_csv(result, "q2_gdp_validation.csv")
    return result


def plot_irf(irf: pd.DataFrame) -> None:
    if irf.empty:
        return
    plot_shock = "oil_specific_risk_shock" if "oil_specific_risk_shock" in set(irf.get("shock", pd.Series(dtype=str))) else str(irf.get("shock", pd.Series(["OilShock"])).dropna().iloc[0])
    irf = irf.loc[irf.get("shock", pd.Series(plot_shock, index=irf.index)).eq(plot_shock)].copy()
    outcomes = irf["outcome"].unique().tolist()
    fig, axes = plt.subplots(len(outcomes), 1, figsize=(8.8, max(4.2, 3.0 * len(outcomes))), sharex=True)
    if len(outcomes) == 1:
        axes = [axes]
    for ax, outcome in zip(axes, outcomes, strict=False):
        frame = irf.loc[irf["outcome"].eq(outcome)].sort_values("horizon")
        ax.axhline(0, color=PALETTE["muted"], linewidth=0.8)
        ax.plot(frame["horizon"], frame["response"], marker="o", color=PALETTE["blue"], label="估计响应")
        ax.fill_between(
            frame["horizon"],
            frame["lower_95"],
            frame["upper_95"],
            color=PALETTE["blue_light"],
            alpha=0.30,
            linewidth=0,
            label="95%置信区间",
        )
        label = OUTCOME_SPECS.get(outcome, outcome)
        ax.text(0.0, 0.91, label, transform=ax.transAxes, ha="left", va="top", fontsize=10.2, color=PALETTE["ink"])
        style_axis(ax, ylabel="响应")
    axes[-1].set_xlabel("油价冲击后月份")
    axes[0].legend(loc="upper right", handlelength=2.4)
    finish_figure(
        fig,
        title="问题二：中国宏观变量对约化形式油价冲击的响应",
        subtitle=f"月度中国变量；主图冲击为 {plot_shock}；阴影为同源移动块bootstrap 95%逐期区间。",
        source="来源：问题一结构冲击接口、OECD CPI、FRED 汇率/美元/GPR；由 code/problem2/run_q2.py 生成。",
        rect=(0.09, 0.12, 0.98, 0.84),
    )
    save_figure(fig, FIGURES_DIR / "q2_irf")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plots-only", action="store_true", help="Regenerate Q2 figures from saved result tables.")
    args = parser.parse_args(argv)

    np.random.seed(RANDOM_SEED)
    apply_paper_style()
    ensure_dirs()
    if args.plots_only:
        irf = pd.read_csv(RESULTS_DIR / "q2_irf.csv")
        plot_irf(irf)
        print(json.dumps({"status": "PASS", "mode": "plots-only", "figures": 1}, ensure_ascii=False, indent=2))
        return 0

    warnings_log: list[dict[str, Any]] = []
    monthly = pd.read_csv(PROCESSED_DIR / "model_monthly_cn.csv")
    quarterly = pd.read_csv(PROCESSED_DIR / "model_quarterly_cn.csv")
    outcomes = available_outcomes(monthly, warnings_log)
    ardl = ardl_baseline(monthly, outcomes, warnings_log)
    irf = local_projection(monthly, outcomes, warnings_log)
    asymmetry = asymmetry_check(monthly, outcomes, warnings_log)
    robustness = lag_and_covid_robustness(monthly, outcomes, warnings_log)
    gdp = gdp_validation(quarterly, warnings_log)
    plot_irf(irf)
    gdp_status = "INCONCLUSIVE"
    if not gdp.empty and "evidence_status" in gdp.columns:
        gdp_status = str(gdp["evidence_status"].dropna().iloc[0]) if not gdp["evidence_status"].dropna().empty else "INCONCLUSIVE"

    summary = pd.DataFrame(
        [
            {
                "component": "ARDL",
                "rows": len(ardl),
                "status": "CONDITIONAL" if warnings_log else ("PASS" if len(ardl) else "WARN"),
                "note": "available monthly outcomes only; OilShock is reduced-form innovation",
            },
            {
                "component": "LocalProjection",
                "rows": len(irf),
                "status": "CONDITIONAL" if warnings_log else ("PASS" if len(irf) else "WARN"),
                "note": "horizons 0..12 where estimable; reports FDR and zero-crossing flags",
            },
            {
                "component": "GDPValidation",
                "rows": len(gdp),
                "status": gdp_status,
                "note": "quarterly GDP check; no monthly interpolation",
            },
            {
                "component": "Asymmetry",
                "rows": len(asymmetry),
                "status": "PASS" if len(asymmetry) else "WARN",
                "note": "positive and negative shock split; not a full NARDL",
            },
            {
                "component": "LagCovidRobustness",
                "rows": len(robustness),
                "status": "PASS" if len(robustness) else "WARN",
                "note": "lag 3/6/12 and exclude-COVID specifications",
            },
        ]
    )
    save_csv(summary, "q2_summary.csv")
    payload = {
        "status": "CONDITIONAL" if warnings_log else "PASS",
        "execution_status": "PASS" if len(irf) or len(ardl) else "WARN",
        "evidence_status": "INCONCLUSIVE",
        "random_seed": RANDOM_SEED,
        "outcomes": outcomes,
        "shock_identification": "LP main interface estimates supply, aggregate-demand and oil-specific-risk shocks from the EIA STEO ex-post decomposition when available; OilShock remains a reduced-form robustness shock.",
        "conclusion_guardrail": "Current estimates do not support a clear aggregate growth-loss statement unless negative responses jointly exclude zero.",
        "warnings": warnings_log,
        "rows": {
            "q2_ardl_baseline.csv": int(len(ardl)),
            "q2_irf.csv": int(len(irf)),
            "q2_gdp_validation.csv": int(len(gdp)),
            "q2_asymmetry.csv": int(len(asymmetry)),
            "q2_robustness.csv": int(len(robustness)),
        },
    }
    (RESULTS_DIR / "q2_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
