"""Question 1: oil-price forecasts and war-shock counterfactuals."""

from __future__ import annotations

import argparse
import json
import math
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
from scipy.optimize import minimize
from scipy.stats import norm
from statsmodels.tools.sm_exceptions import ValueWarning
from statsmodels.tsa.forecasting.theta import ThetaModel
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX


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
CUTOFF = pd.Timestamp("2026-06-30")
RANDOM_SEED = 20260730
EVAL_START = "2020-01"
EVENT_E1_CALENDAR_START = pd.Timestamp("2026-02-28")
EVENT_E3_CALENDAR_START = pd.Timestamp("2026-06-17")
EVENT_TERMS = ["stage_E1", "stage_E2", "stage_E3"]


def ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)


def save_csv(frame: pd.DataFrame, filename: str) -> Path:
    path = RESULTS_DIR / filename
    frame.to_csv(path, index=False, encoding="utf-8")
    return path


def json_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return json.loads(frame.where(pd.notna(frame), None).to_json(orient="records"))


def zscore(series: pd.Series) -> pd.Series:
    std = series.std(skipna=True)
    if not np.isfinite(std) or std == 0:
        return series * np.nan
    return (series - series.mean(skipna=True)) / std


def log_positive(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    result = pd.Series(np.nan, index=series.index, dtype=float)
    mask = values > 0
    result.loc[mask] = np.log(values.loc[mask])
    return result


def fit_sarimax(
    y: pd.Series,
    order: tuple[int, int, int],
    exog: pd.DataFrame | None = None,
) -> Any:
    with py_warnings.catch_warnings():
        py_warnings.simplefilter("ignore")
        model = SARIMAX(
            y,
            order=order,
            exog=exog,
            trend="c",
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        return model.fit(disp=False, maxiter=200)


def common_trading_dates(daily: pd.DataFrame, price_prefix: str = "brent_usd_bbl") -> list[pd.Timestamp]:
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    other_price = "wti_usd_bbl" if price_prefix == "brent_usd_bbl" and "wti_usd_bbl" in frame.columns else price_prefix
    mask = frame[price_prefix].notna() & frame[other_price].notna()
    return [pd.Timestamp(value) for value in frame.loc[mask, "date"].drop_duplicates().sort_values().tolist()]


def first_trading_date_on_or_after(daily: pd.DataFrame, date: pd.Timestamp, price_prefix: str = "brent_usd_bbl") -> pd.Timestamp:
    candidates = [value for value in common_trading_dates(daily, price_prefix) if value >= date]
    if not candidates:
        raise ValueError(f"No common trading date on or after {date.date()} for {price_prefix}.")
    return candidates[0]


def trading_day_shift(daily: pd.DataFrame, start: pd.Timestamp, shift_days: int, price_prefix: str = "brent_usd_bbl") -> pd.Timestamp:
    dates = common_trading_dates(daily, price_prefix)
    try:
        idx = dates.index(start)
    except ValueError as exc:
        raise ValueError(f"{start.date()} is not a common trading date for {price_prefix}.") from exc
    shifted_idx = idx + shift_days
    if shifted_idx < 0 or shifted_idx >= len(dates):
        raise ValueError(f"Trading-day shift {shift_days:+d} from {start.date()} is outside the observed sample.")
    return dates[shifted_idx]


def assign_event_stages(daily: pd.DataFrame, e1_start: pd.Timestamp | None = None, price_prefix: str = "brent_usd_bbl") -> tuple[pd.DataFrame, dict[str, str]]:
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    e1_start = e1_start or first_trading_date_on_or_after(frame, EVENT_E1_CALENDAR_START, price_prefix)
    dates = common_trading_dates(frame, price_prefix)
    idx = dates.index(e1_start)
    if idx + 3 >= len(dates):
        raise ValueError("E1 event window lacks enough post-event trading days.")
    e1_car_end = dates[idx + 2]
    e2_start = dates[idx + 3]
    e3_start = first_trading_date_on_or_after(frame, EVENT_E3_CALENDAR_START, price_prefix)

    date = frame["date"]
    frame["war_stage"] = "prewar"
    frame.loc[date.between(e1_start, e1_car_end), "war_stage"] = "E1_immediate_window"
    frame.loc[date.between(e2_start, e3_start - pd.Timedelta(days=1)), "war_stage"] = "E2_disruption"
    frame.loc[date >= e3_start, "war_stage"] = "E3_easing"
    frame["war_on"] = (date >= e1_start).astype(int)
    frame["stage_E1"] = date.between(e1_start, e1_car_end).astype(int)
    frame["stage_E2"] = frame["war_stage"].eq("E2_disruption").astype(int)
    frame["stage_E3"] = frame["war_stage"].eq("E3_easing").astype(int)
    event_meta = {
        "e1_calendar_start": EVENT_E1_CALENDAR_START.strftime("%Y-%m-%d"),
        "e1_trading_start": e1_start.strftime("%Y-%m-%d"),
        "e1_car_end_0_2": e1_car_end.strftime("%Y-%m-%d"),
        "e2_trading_start": e2_start.strftime("%Y-%m-%d"),
        "e3_trading_start": e3_start.strftime("%Y-%m-%d"),
    }
    return frame, event_meta


def dm_hln_test(loss_model: pd.Series, loss_benchmark: pd.Series, horizon: int) -> tuple[float, float]:
    diff = pd.Series(loss_model.to_numpy(dtype=float) - loss_benchmark.to_numpy(dtype=float)).dropna()
    n = len(diff)
    if n <= horizon + 1 or float(diff.var(ddof=1)) == 0.0:
        return np.nan, np.nan
    mean_diff = float(diff.mean())
    centered = diff - mean_diff
    max_lag = max(0, horizon - 1)
    gamma0 = float((centered @ centered) / n)
    long_run_var = gamma0
    for lag in range(1, max_lag + 1):
        gamma = float((centered.iloc[lag:].to_numpy() @ centered.iloc[:-lag].to_numpy()) / n)
        long_run_var += 2.0 * (1.0 - lag / (max_lag + 1.0)) * gamma
    if long_run_var <= 0 or not np.isfinite(long_run_var):
        return np.nan, np.nan
    dm_stat = mean_diff / math.sqrt(long_run_var / n)
    hln_scale = math.sqrt((n + 1 - 2 * horizon + horizon * (horizon - 1) / n) / n)
    stat = dm_stat * hln_scale
    pvalue = 2.0 * (1.0 - norm.cdf(abs(stat)))
    return float(stat), float(pvalue)


def classify_forecast_model(model: str, rel_rmse: float, dm_stat: float, dm_pvalue: float) -> str:
    if model == "no_change":
        return "PASS"
    significantly_worse = np.isfinite(dm_stat) and np.isfinite(dm_pvalue) and dm_stat > 0 and dm_pvalue < 0.10
    if np.isfinite(rel_rmse) and rel_rmse < 1.00 and not significantly_worse:
        return "PASS"
    if significantly_worse or (np.isfinite(rel_rmse) and rel_rmse > 1.05):
        return "FAIL"
    return "CONDITIONAL"


def select_orders(monthly: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> tuple[tuple[int, int, int], tuple[int, int, int], pd.DataFrame]:
    train = monthly.loc[monthly["period"].lt(EVAL_START)].dropna(subset=["log_brent"])
    exog_cols = ["stock_log_lag1", "usd_broad_index_log_return_lag1", "GPR_z_lag1"]
    train_exog = train[exog_cols]
    train_full = train.dropna(subset=["log_brent"] + exog_cols)
    rows: list[dict[str, Any]] = []
    best_arima = ((1, 1, 1), math.inf)
    best_sarimax = ((1, 1, 1), math.inf)
    for p in range(3):
        for q in range(3):
            order = (p, 1, q)
            try:
                result = fit_sarimax(train["log_brent"], order)
                rows.append({"model": "ARIMA", "order": str(order), "aic": float(result.aic)})
                if result.aic < best_arima[1]:
                    best_arima = (order, float(result.aic))
            except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                rows.append({"model": "ARIMA", "order": str(order), "aic": np.nan, "error": str(exc)})
            try:
                result = fit_sarimax(train_full["log_brent"], order, train_exog.loc[train_full.index])
                rows.append({"model": "SARIMAX", "order": str(order), "aic": float(result.aic)})
                if result.aic < best_sarimax[1]:
                    best_sarimax = (order, float(result.aic))
            except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                rows.append({"model": "SARIMAX", "order": str(order), "aic": np.nan, "error": str(exc)})
    if not np.isfinite(best_arima[1]):
        warnings_log.append({"code": "arima_order_grid_failed", "message": "ARIMA grid failed; using (1,1,1)."})
        best_arima = ((1, 1, 1), np.nan)
    if not np.isfinite(best_sarimax[1]):
        warnings_log.append({"code": "sarimax_order_grid_failed", "message": "SARIMAX grid failed; using (1,1,1)."})
        best_sarimax = ((1, 1, 1), np.nan)
    grid = pd.DataFrame(rows)
    save_csv(grid, "q1_order_grid.csv")
    return best_arima[0], best_sarimax[0], grid


def forecast_interval(prediction: float, sigma: float, horizon: int, alpha: float) -> tuple[float, float]:
    width = norm.ppf(1 - alpha / 2) * sigma * math.sqrt(horizon)
    return prediction - width, prediction + width


def monthly_forecasts(monthly: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    exog_cols = ["stock_log_lag1", "usd_broad_index_log_return_lag1", "GPR_z_lag1"]
    arima_order, sarimax_order, _ = select_orders(monthly, warnings_log)
    rows: list[dict[str, Any]] = []
    periods = monthly["period"].tolist()
    eval_periods = [period for period in periods if period >= EVAL_START]

    for target_period in eval_periods:
        target_idx = periods.index(target_period)
        for horizon in [1, 3, 6]:
            origin_idx = target_idx - horizon
            if origin_idx < 60:
                continue
            train = monthly.iloc[: origin_idx + 1].copy()
            target = monthly.iloc[target_idx]
            if pd.isna(target["log_brent"]):
                continue
            origin = monthly.iloc[origin_idx]
            sample_start = train["period"].iloc[0]
            sample_end = train["period"].iloc[-1]

            residual = train["log_brent"].diff().dropna()
            sigma = float(residual.std()) if len(residual) > 2 else 0.1
            no_change = float(origin["log_brent"])
            for alpha, prefix in [(0.20, "80"), (0.05, "95")]:
                pass
            lower_80, upper_80 = forecast_interval(no_change, sigma, horizon, 0.20)
            lower_95, upper_95 = forecast_interval(no_change, sigma, horizon, 0.05)
            rows.append(
                {
                    "origin_period": str(origin["period"]),
                    "origin_price": float(origin["brent_usd_bbl"]),
                    "origin_log_price": float(origin["log_brent"]),
                    "period": target_period,
                    "horizon": horizon,
                    "model": "no_change",
                    "actual": float(target["log_brent"]),
                    "prediction": no_change,
                    "actual_change": float(target["log_brent"] - origin["log_brent"]),
                    "predicted_change": float(no_change - origin["log_brent"]),
                    "lower_80": lower_80,
                    "upper_80": upper_80,
                    "lower_95": lower_95,
                    "upper_95": upper_95,
                    "actual_price": float(target["brent_usd_bbl"]),
                    "prediction_price": float(np.exp(no_change)),
                    "sample_start": sample_start,
                    "sample_end": sample_end,
                    "specification": "last observed log Brent",
                }
            )

            for model_name, order, use_exog in [
                ("ARIMA", arima_order, False),
                ("SARIMAX", sarimax_order, True),
            ]:
                try:
                    fit_train = train.dropna(subset=["log_brent"] + (exog_cols if use_exog else []))
                    exog_train = fit_train[exog_cols] if use_exog else None
                    result = fit_sarimax(fit_train["log_brent"], order, exog_train)
                    if use_exog:
                        last_exog = fit_train[exog_cols].iloc[-1].to_numpy(dtype=float)
                        future_exog = pd.DataFrame([last_exog] * horizon, columns=exog_cols)
                        forecast = result.get_forecast(steps=horizon, exog=future_exog)
                    else:
                        forecast = result.get_forecast(steps=horizon)
                    mean = float(forecast.predicted_mean.iloc[-1])
                    ci80 = forecast.conf_int(alpha=0.20).iloc[-1].to_numpy(dtype=float)
                    ci95 = forecast.conf_int(alpha=0.05).iloc[-1].to_numpy(dtype=float)
                    rows.append(
                        {
                            "origin_period": str(origin["period"]),
                            "origin_price": float(origin["brent_usd_bbl"]),
                            "origin_log_price": float(origin["log_brent"]),
                            "period": target_period,
                            "horizon": horizon,
                            "model": model_name,
                            "actual": float(target["log_brent"]),
                            "prediction": mean,
                            "actual_change": float(target["log_brent"] - origin["log_brent"]),
                            "predicted_change": float(mean - origin["log_brent"]),
                            "lower_80": float(ci80[0]),
                            "upper_80": float(ci80[1]),
                            "lower_95": float(ci95[0]),
                            "upper_95": float(ci95[1]),
                            "actual_price": float(target["brent_usd_bbl"]),
                            "prediction_price": float(np.exp(mean)),
                            "sample_start": sample_start,
                            "sample_end": sample_end,
                            "specification": f"order={order}; future exog held at origin" if use_exog else f"order={order}",
                        }
                    )
                except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                    warnings_log.append(
                        {
                            "code": "monthly_forecast_model_failed",
                            "message": f"{model_name} h={horizon} target={target_period}: {exc}",
                        }
                    )
            fit_train = train.dropna(subset=["log_brent"]).copy()
            fit_series = pd.Series(
                fit_train["log_brent"].to_numpy(dtype=float),
                index=pd.PeriodIndex(fit_train["period"], freq="M").to_timestamp(),
            ).asfreq("MS")
            for model_name in ["ETS", "Theta"]:
                try:
                    if model_name == "ETS":
                        fitted = ExponentialSmoothing(
                            fit_series,
                            trend="add",
                            damped_trend=True,
                            seasonal=None,
                            initialization_method="estimated",
                        ).fit(optimized=True)
                        pred_values = fitted.forecast(horizon)
                    else:
                        fitted = ThetaModel(fit_series, period=12, deseasonalize=False).fit()
                        pred_values = fitted.forecast(horizon)
                    mean = float(pred_values.iloc[-1])
                    lower_80, upper_80 = forecast_interval(mean, sigma, horizon, 0.20)
                    lower_95, upper_95 = forecast_interval(mean, sigma, horizon, 0.05)
                    rows.append(
                        {
                            "origin_period": str(origin["period"]),
                            "origin_price": float(origin["brent_usd_bbl"]),
                            "origin_log_price": float(origin["log_brent"]),
                            "period": target_period,
                            "horizon": horizon,
                            "model": model_name,
                            "actual": float(target["log_brent"]),
                            "prediction": mean,
                            "actual_change": float(target["log_brent"] - origin["log_brent"]),
                            "predicted_change": float(mean - origin["log_brent"]),
                            "lower_80": lower_80,
                            "upper_80": upper_80,
                            "lower_95": lower_95,
                            "upper_95": upper_95,
                            "actual_price": float(target["brent_usd_bbl"]),
                            "prediction_price": float(np.exp(mean)),
                            "sample_start": sample_start,
                            "sample_end": sample_end,
                            "specification": "Holt damped ETS" if model_name == "ETS" else "ThetaModel period=12",
                        }
                    )
                except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                    warnings_log.append(
                        {
                            "code": "monthly_forecast_model_failed",
                            "message": f"{model_name} h={horizon} target={target_period}: {exc}",
                        }
                    )

    forecasts = pd.DataFrame(rows)
    forecasts = add_equal_weight_combination(forecasts)
    save_csv(forecasts, "q1_forecasts.csv")
    metrics = forecast_metrics(forecasts)
    save_csv(metrics, "q1_forecast_metrics.csv")
    return forecasts, metrics


def add_equal_weight_combination(forecasts: pd.DataFrame) -> pd.DataFrame:
    if forecasts.empty:
        return forecasts
    members = ["no_change", "ARIMA", "SARIMAX", "ETS", "Theta"]
    rows: list[dict[str, Any]] = []
    for (_, _), group in forecasts.groupby(["period", "horizon"]):
        available = group.loc[group["model"].isin(members)].copy()
        if len(available) < 2:
            continue
        template = available.iloc[0].to_dict()
        prediction = float(available["prediction"].mean())
        for column in ["lower_80", "upper_80", "lower_95", "upper_95"]:
            template[column] = float(available[column].mean())
        template.update(
            {
                "model": "EqualWeight",
                "prediction": prediction,
                "prediction_price": float(np.exp(prediction)),
                "predicted_change": prediction - float(template["origin_log_price"]),
                "specification": "equal-weight average of available no_change/ARIMA/SARIMAX/ETS/Theta forecasts",
            }
        )
        rows.append(template)
    if not rows:
        return forecasts
    return pd.concat([forecasts, pd.DataFrame(rows)], ignore_index=True, sort=False)


def forecast_metrics(forecasts: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if forecasts.empty:
        return pd.DataFrame()
    forecasts = forecasts.sort_values(["model", "horizon", "period"]).copy()
    forecasts["error"] = forecasts["actual"] - forecasts["prediction"]
    forecasts["abs_error"] = forecasts["error"].abs()
    forecasts["squared_error"] = forecasts["error"] ** 2
    forecasts["covered_80"] = forecasts["actual"].between(forecasts["lower_80"], forecasts["upper_80"])
    forecasts["covered_95"] = forecasts["actual"].between(forecasts["lower_95"], forecasts["upper_95"])
    for (model, horizon), group in forecasts.groupby(["model", "horizon"]):
        group = group.sort_values("period")
        benchmark = forecasts.loc[
            forecasts["model"].eq("no_change") & forecasts["horizon"].eq(horizon),
            ["period", "abs_error", "squared_error"],
        ].rename(columns={"abs_error": "benchmark_abs_error", "squared_error": "benchmark_squared_error"})
        paired = group.merge(benchmark, on="period", how="inner")
        benchmark_mae = float(paired["benchmark_abs_error"].mean()) if not paired.empty else np.nan
        benchmark_rmse = float(np.sqrt(paired["benchmark_squared_error"].mean())) if not paired.empty else np.nan
        mae = float(group["abs_error"].mean())
        rmse = float(np.sqrt(group["squared_error"].mean()))
        rel_mae = mae / benchmark_mae if np.isfinite(benchmark_mae) and benchmark_mae > 0 else np.nan
        rel_rmse = rmse / benchmark_rmse if np.isfinite(benchmark_rmse) and benchmark_rmse > 0 else np.nan
        dm_rmse_stat, dm_rmse_pvalue = dm_hln_test(paired["squared_error"], paired["benchmark_squared_error"], int(horizon))
        dm_mae_stat, dm_mae_pvalue = dm_hln_test(paired["abs_error"], paired["benchmark_abs_error"], int(horizon))
        if {"actual_change", "predicted_change"}.issubset(group.columns):
            directional = group[["actual_change", "predicted_change"]].dropna()
            direction_accuracy = (
                float(np.sign(directional["actual_change"]).eq(np.sign(directional["predicted_change"])).mean())
                if not directional.empty
                else np.nan
            )
        else:
            actual_dir = np.sign(group["actual"].diff())
            pred_dir = np.sign(group["prediction"].diff())
            direction_accuracy = float((actual_dir.eq(pred_dir)).iloc[1:].mean()) if len(group) > 2 else np.nan
        status = classify_forecast_model(str(model), rel_rmse, dm_rmse_stat, dm_rmse_pvalue)
        rows.append(
            {
                "model": model,
                "horizon": int(horizon),
                "n": int(len(group)),
                "MAE": mae,
                "RMSE": rmse,
                "relative_MAE_vs_no_change": rel_mae,
                "relative_RMSE_vs_no_change": rel_rmse,
                "dm_hln_stat_rmse_loss": dm_rmse_stat,
                "dm_hln_pvalue_rmse_loss": dm_rmse_pvalue,
                "dm_hln_stat_mae_loss": dm_mae_stat,
                "dm_hln_pvalue_mae_loss": dm_mae_pvalue,
                "direction_accuracy": direction_accuracy,
                "coverage_80": float(group["covered_80"].mean()),
                "coverage_95": float(group["covered_95"].mean()),
                "model_status": status,
            }
        )
    return pd.DataFrame(rows)


def monthly_shock_residuals(monthly: pd.DataFrame) -> pd.DataFrame:
    exog_cols = ["log_brent_lag1", "stock_log_lag1", "usd_broad_index_log_return_lag1", "GPR_z_lag1"]
    frame = monthly.copy()
    frame["log_brent_lag1"] = frame["log_brent"].shift(1)
    usable = frame.dropna(subset=["log_brent"] + exog_cols).copy()
    x = sm.add_constant(usable[exog_cols], has_constant="add")
    model = sm.OLS(usable["log_brent"], x).fit(cov_type="HAC", cov_kwds={"maxlags": 3})
    usable["OilShock_raw"] = model.resid
    usable["OilShock"] = zscore(usable["OilShock_raw"])
    result = frame[["period", "month_end", "brent_usd_bbl", "log_brent", "brent_usd_bbl_log_return"]].merge(
        usable[["period", "OilShock_raw", "OilShock"]],
        on="period",
        how="left",
    )
    result["OilShock_source"] = "ARX_one_step_residual_lagged_information"
    return result


def stage_effect_regression(daily: pd.DataFrame, price_prefix: str, specification: str) -> pd.DataFrame:
    return_col = f"{price_prefix}_log_return"
    frame = daily.loc[pd.to_datetime(daily["date"]).between(pd.Timestamp("2024-01-01"), CUTOFF)].copy()
    for lag in [1, 2, 3]:
        frame[f"{return_col}_lag{lag}"] = frame[return_col].shift(lag)
    regressors = [f"{return_col}_lag{lag}" for lag in [1, 2, 3]] + ["usd_broad_index_log_return"] + EVENT_TERMS
    usable = frame.dropna(subset=[return_col] + regressors)
    if usable.empty:
        return pd.DataFrame()
    x = sm.add_constant(usable[regressors], has_constant="add")
    for term in EVENT_TERMS:
        event_count = int(usable[term].sum())
        if event_count == 0 or event_count == len(usable):
            raise ValueError(f"{term} is not identifiable for {price_prefix}: event_count={event_count}, n={len(usable)}.")
    rank = int(np.linalg.matrix_rank(x.to_numpy(dtype=float)))
    if rank < x.shape[1]:
        raise ValueError(f"Event-stage design is rank deficient for {price_prefix}: rank={rank}, columns={x.shape[1]}.")
    fit = sm.OLS(usable[return_col], x).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    rows: list[dict[str, Any]] = []
    for term in ["stage_E1", "stage_E2", "stage_E3"]:
        estimate = float(fit.params.get(term, np.nan))
        se = float(fit.bse.get(term, np.nan))
        descriptive_only = term == "stage_E1"
        rows.append(
            {
                "stage_id": term.replace("stage_", ""),
                "model": f"{price_prefix}_stage_dummy",
                "specification": specification,
                "estimate_log_return": estimate,
                "std_error": np.nan if descriptive_only else se,
                "lower_80": np.nan if descriptive_only else estimate - norm.ppf(0.90) * se,
                "upper_80": np.nan if descriptive_only else estimate + norm.ppf(0.90) * se,
                "lower_95": np.nan if descriptive_only else estimate - norm.ppf(0.975) * se,
                "upper_95": np.nan if descriptive_only else estimate + norm.ppf(0.975) * se,
                "pvalue": np.nan if descriptive_only else float(fit.pvalues.get(term, np.nan)),
                "sample_start": str(usable["date"].min().date()),
                "sample_end": str(usable["date"].max().date()),
                "n": int(len(usable)),
                "event_observations": int(usable[term].sum()),
                "identification_status": "DESCRIPTIVE_ONLY" if descriptive_only else "PASS",
            }
        )
    return pd.DataFrame(rows)


def event_car_rows(daily: pd.DataFrame, price_prefix: str, event_start: pd.Timestamp, model_label: str) -> pd.DataFrame:
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    return_col = f"{price_prefix}_log_return"
    for lag in [1, 2, 3]:
        frame[f"{return_col}_lag{lag}"] = frame[return_col].shift(lag)
    dates = [value for value in common_trading_dates(frame, price_prefix) if value >= event_start]
    if len(dates) < 3:
        return pd.DataFrame()
    event_dates = dates[:3]
    train = frame.loc[frame["date"].lt(event_start)].dropna(
        subset=[return_col, "usd_broad_index_log_return", f"{return_col}_lag1", f"{return_col}_lag2", f"{return_col}_lag3"]
    )
    if len(train) < 80:
        return pd.DataFrame()
    train = train.tail(520)
    regressors = [f"{return_col}_lag{lag}" for lag in [1, 2, 3]] + ["usd_broad_index_log_return"]
    fit = sm.OLS(train[return_col], sm.add_constant(train[regressors].astype(float), has_constant="add")).fit(
        cov_type="HAC",
        cov_kwds={"maxlags": 5},
    )
    sigma = float(fit.resid.std(ddof=1))
    rows: list[dict[str, Any]] = []
    cumulative_actual = 0.0
    cumulative_expected = 0.0
    recursive_lags = [float(train[return_col].iloc[-lag]) for lag in [1, 2, 3]]
    pre_event_usd = float(train["usd_broad_index_log_return"].iloc[-1])
    for horizon, event_date in enumerate(event_dates):
        event_row = frame.loc[frame["date"].eq(event_date)].dropna(subset=[return_col])
        if event_row.empty:
            continue
        x = pd.DataFrame(
            [
                {
                    f"{return_col}_lag1": recursive_lags[0],
                    f"{return_col}_lag2": recursive_lags[1],
                    f"{return_col}_lag3": recursive_lags[2],
                    "usd_broad_index_log_return": pre_event_usd,
                }
            ]
        )
        x = sm.add_constant(x[regressors].astype(float), has_constant="add")
        expected = float(fit.predict(x).iloc[0])
        actual = float(event_row[return_col].iloc[0])
        cumulative_actual += actual
        cumulative_expected += expected
        recursive_lags = [expected, *recursive_lags[:2]]
        abnormal = cumulative_actual - cumulative_expected
        se = sigma * math.sqrt(horizon + 1)
        rows.append(
            {
                "stage_id": f"E1_CAR_0_{horizon}" if horizon else "E1_CAR_0",
                "model": model_label,
                "specification": "recursive AR(3)+pre-event USD expected-return CAR; E1 mapped to first common trading day",
                "estimate_log_return": abnormal,
                "actual_cumulative_log_return": cumulative_actual,
                "expected_cumulative_log_return": cumulative_expected,
                "std_error": se,
                "lower_80": abnormal - norm.ppf(0.90) * se,
                "upper_80": abnormal + norm.ppf(0.90) * se,
                "lower_95": abnormal - norm.ppf(0.975) * se,
                "upper_95": abnormal + norm.ppf(0.975) * se,
                "pvalue": 2.0 * (1.0 - norm.cdf(abs(abnormal / se))) if se > 0 else np.nan,
                "sample_start": str(train["date"].min().date()),
                "sample_end": str(train["date"].max().date()),
                "n": int(len(train)),
                "event_observations": horizon + 1,
                "event_trading_start": event_start.strftime("%Y-%m-%d"),
                "event_window_end": event_date.strftime("%Y-%m-%d"),
                "identification_status": "PASS",
            }
        )
    return pd.DataFrame(rows)


def finite_sample_empirical_pvalue(distribution: pd.Series, threshold: float) -> float:
    values = pd.to_numeric(distribution, errors="coerce").dropna().abs()
    if values.empty:
        return np.nan
    exceedances = int(values.ge(abs(threshold)).sum())
    return float((exceedances + 1) / (len(values) + 1))


def placebo_distribution(daily: pd.DataFrame, actual_car: pd.DataFrame) -> pd.DataFrame:
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    weekend_calendar = pd.date_range("2024-01-06", "2025-12-28", freq="W-SAT")
    excluded_event_dates = [
        pd.Timestamp("2024-04-13"),
        pd.Timestamp("2024-10-01"),
        pd.Timestamp("2025-06-13"),
    ]
    seen_starts: set[pd.Timestamp] = set()
    pieces: list[pd.DataFrame] = []
    for block_id, pseudo_calendar in enumerate(weekend_calendar):
        if any(abs((pseudo_calendar - event_date).days) <= 7 for event_date in excluded_event_dates):
            continue
        start = first_trading_date_on_or_after(frame, pd.Timestamp(pseudo_calendar), "brent_usd_bbl")
        if start in seen_starts:
            continue
        seen_starts.add(start)
        car = event_car_rows(frame, "brent_usd_bbl", start, "brent_weekend_placebo_car")
        if car.empty:
            continue
        car["pseudo_calendar_date"] = pseudo_calendar.strftime("%Y-%m-%d")
        car["placebo_block_id"] = block_id
        pieces.append(car)
    placebo = pd.concat(pieces, ignore_index=True, sort=False) if pieces else pd.DataFrame()
    if placebo.empty or actual_car.empty:
        save_csv(placebo, "q1_placebo_distribution.csv")
        return placebo
    actual = actual_car.loc[actual_car["model"].eq("brent_usd_bbl_event_car")].copy()
    empirical: dict[str, float] = {}
    for stage_id, group in placebo.groupby("stage_id"):
        actual_row = actual.loc[actual["stage_id"].eq(stage_id)]
        if actual_row.empty:
            continue
        threshold = abs(float(actual_row["estimate_log_return"].iloc[0]))
        empirical[stage_id] = finite_sample_empirical_pvalue(group["estimate_log_return"], threshold)
    placebo["actual_empirical_pvalue"] = placebo["stage_id"].map(empirical)
    save_csv(placebo, "q1_placebo_distribution.csv")
    return placebo


def add_empirical_pvalues(actual_car: pd.DataFrame, placebo: pd.DataFrame) -> pd.DataFrame:
    if actual_car.empty or placebo.empty:
        return actual_car
    result = actual_car.copy()
    result["pvalue_empirical"] = np.nan
    for idx, row in result.iterrows():
        if row["model"] != "brent_usd_bbl_event_car":
            continue
        dist = placebo.loc[placebo["stage_id"].eq(row["stage_id"]), "estimate_log_return"].dropna()
        if dist.empty:
            continue
        threshold = abs(float(row["estimate_log_return"]))
        result.loc[idx, "pvalue_empirical"] = finite_sample_empirical_pvalue(dist, threshold)
    return result


def shifted_event_regression(daily: pd.DataFrame, shift_trading_days: int) -> pd.DataFrame:
    main_start = first_trading_date_on_or_after(daily, EVENT_E1_CALENDAR_START, "brent_usd_bbl")
    shifted_start = trading_day_shift(daily, main_start, shift_trading_days, "brent_usd_bbl")
    frame, _ = assign_event_stages(daily, shifted_start, "brent_usd_bbl")
    result = stage_effect_regression(frame, "brent_usd_bbl", f"event dates shifted by {shift_trading_days} trading days")
    if not result.empty:
        result["model"] = f"brent_alt_event_shift_{shift_trading_days:+d}td"
        result["event_trading_start"] = shifted_start.strftime("%Y-%m-%d")
    return result


def robustness_summary(forecasts: pd.DataFrame, effects: pd.DataFrame, daily: pd.DataFrame, placebos: pd.DataFrame) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    if not forecasts.empty:
        for start in ["2021-01", "2022-01"]:
            metrics = forecast_metrics(forecasts.loc[forecasts["period"].ge(start)].copy())
            if not metrics.empty:
                metrics["robustness_type"] = f"evaluation_start_{start}"
                pieces.append(metrics)
    wti = effects.loc[effects["model"].eq("wti_usd_bbl_stage_dummy")].copy()
    if not wti.empty:
        wti["robustness_type"] = "WTI_event_price"
        pieces.append(wti)
    if not placebos.empty:
        summary = (
            placebos.groupby("stage_id", as_index=False)
            .agg(
                placebo_mean=("estimate_log_return", "mean"),
                placebo_p05=("estimate_log_return", lambda s: float(np.quantile(s.dropna(), 0.05))),
                placebo_p95=("estimate_log_return", lambda s: float(np.quantile(s.dropna(), 0.95))),
                placebo_events=("estimate_log_return", "count"),
                actual_empirical_pvalue=("actual_empirical_pvalue", "first"),
            )
        )
        summary["robustness_type"] = "matched_weekend_placebo_distribution"
        summary["model"] = "brent_weekend_placebo_car"
        pieces.append(summary)
    for shift in [-5, 5]:
        alt = shifted_event_regression(daily, shift)
        if not alt.empty:
            alt["robustness_type"] = f"event_shift_{shift:+d}trading_days"
            pieces.append(alt)
    result = pd.concat(pieces, ignore_index=True, sort=False) if pieces else pd.DataFrame()
    save_csv(result, "q1_robustness.csv")
    return result


def daily_counterfactual(daily: pd.DataFrame) -> pd.DataFrame:
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["log_brent"] = log_positive(frame["brent_usd_bbl"])
    ret_col = "brent_usd_bbl_log_return"
    train = frame.loc[frame["date"].between(pd.Timestamp("2024-01-01"), pd.Timestamp("2026-02-27"))].copy()
    for lag in [1, 2, 3]:
        train[f"ret_lag{lag}"] = train[ret_col].shift(lag)
    fit_data = train.dropna(subset=[ret_col, "usd_broad_index_log_return", "ret_lag1", "ret_lag2", "ret_lag3"])
    x = sm.add_constant(fit_data[["ret_lag1", "ret_lag2", "ret_lag3", "usd_broad_index_log_return"]], has_constant="add")
    fit = sm.OLS(fit_data[ret_col], x).fit(cov_type="HAC", cov_kwds={"maxlags": 5})

    event_start = first_trading_date_on_or_after(frame, EVENT_E1_CALENDAR_START, "brent_usd_bbl")
    event = frame.loc[frame["date"].between(event_start, CUTOFF)].copy()
    event = event.dropna(subset=["brent_usd_bbl"]).reset_index(drop=True)
    if event.empty:
        return pd.DataFrame()
    history_returns = train[ret_col].dropna().tail(3).tolist()
    cf_log = float(train["log_brent"].dropna().iloc[-1])
    rows: list[dict[str, Any]] = []
    sigma = float(fit.resid.std())
    for _, row in event.iterrows():
        usd_return = 0.0 if pd.isna(row["usd_broad_index_log_return"]) else float(row["usd_broad_index_log_return"])
        reg = pd.DataFrame(
            [
                {
                    "const": 1.0,
                    "ret_lag1": history_returns[-1],
                    "ret_lag2": history_returns[-2],
                    "ret_lag3": history_returns[-3],
                    "usd_broad_index_log_return": usd_return,
                }
            ]
        )
        pred_ret = float(fit.predict(reg).iloc[0])
        cf_log += pred_ret
        history_returns.append(pred_ret)
        actual_log = float(np.log(row["brent_usd_bbl"]))
        prediction = float(np.exp(cf_log))
        baseline_gap = float(row["brent_usd_bbl"] - prediction)
        lower_80_log, upper_80_log = forecast_interval(cf_log, sigma, len(rows) + 1, 0.20)
        lower_95_log, upper_95_log = forecast_interval(cf_log, sigma, len(rows) + 1, 0.05)
        rows.append(
            {
                "date": row["date"].strftime("%Y-%m-%d"),
                "period": row["date"].to_period("M").strftime("%Y-%m"),
                "actual": float(row["brent_usd_bbl"]),
                "prediction": prediction,
                "response": baseline_gap,
                "lower_80": float(np.exp(lower_80_log)),
                "upper_80": float(np.exp(upper_80_log)),
                "lower_95": float(np.exp(lower_95_log)),
                "upper_95": float(np.exp(upper_95_log)),
                "actual_log": actual_log,
                "ar_baseline_log": cf_log,
                "ar_baseline_gap_usd_bbl": baseline_gap,
                "war_stage": row["war_stage"],
                "model": "AR3_plus_USD_baseline_scenario",
                "horizon": len(rows) + 1,
                "specification": "descriptive AR(3)+USD baseline trained 2024-01-01 to 2026-02-27; not a causal no-war counterfactual",
                "sample_start": "2024-01-01",
                "sample_end": "2026-02-27",
            }
        )
    counterfactual = pd.DataFrame(rows)
    save_csv(counterfactual, "q1_daily_counterfactual.csv")
    return counterfactual


def residualize(series: pd.Series, controls: pd.DataFrame) -> pd.Series:
    frame = pd.concat([series.rename("target"), controls], axis=1).dropna()
    result = pd.Series(np.nan, index=series.index, dtype=float)
    if len(frame) < controls.shape[1] + 12:
        return result
    fit = sm.OLS(frame["target"], sm.add_constant(frame.drop(columns=["target"]).astype(float), has_constant="add")).fit()
    result.loc[frame.index] = fit.resid
    return result


def structural_shock_decomposition(monthly: pd.DataFrame) -> pd.DataFrame:
    steo_path = PROCESSED_DIR / "eia_steo_selected.csv"
    base = monthly[["period", "month_end", "brent_usd_bbl_log_return", "GPR_z"]].copy()
    if not steo_path.exists():
        result = base[["period"]].copy()
        for column in ["supply_shock", "aggregate_demand_shock", "oil_specific_risk_shock"]:
            result[column] = np.nan
        result["reduced_form_shock"] = np.nan
        result["source_vintage"] = "EIA_STEO_missing"
        save_csv(result, "q1_structural_shocks.csv")
        return result
    steo = pd.read_csv(steo_path)
    pivot = steo.pivot_table(index="period", columns="variable_id", values="value", aggfunc="first").reset_index()
    frame = base.merge(pivot, on="period", how="left").sort_values("period").reset_index(drop=True)
    frame["supply_growth"] = np.log(frame["world_liquids_supply_mbd"]).diff()
    frame["demand_growth"] = np.log(frame["world_liquids_demand_mbd"]).diff()
    frame["inventory_change"] = np.log(frame["oecd_commercial_liquids_stocks_mmbbl"]).diff()
    controls = pd.DataFrame(
        {
            "supply_lag1": frame["supply_growth"].shift(1),
            "demand_lag1": frame["demand_growth"].shift(1),
            "inventory_lag1": frame["inventory_change"].shift(1),
            "price_lag1": frame["brent_usd_bbl_log_return"].shift(1),
        }
    )
    supply_resid = residualize(frame["supply_growth"], controls)
    demand_resid = residualize(frame["demand_growth"], pd.concat([controls, supply_resid.rename("supply_resid")], axis=1))
    risk_controls = pd.concat(
        [
            controls,
            supply_resid.rename("supply_resid"),
            demand_resid.rename("demand_resid"),
            frame["inventory_change"].rename("inventory_change"),
            frame["GPR_z"].rename("GPR_z"),
        ],
        axis=1,
    )
    risk_resid = residualize(frame["brent_usd_bbl_log_return"], risk_controls)
    result = frame[["period"]].copy()
    result["supply_shock"] = zscore(-supply_resid)
    result["aggregate_demand_shock"] = zscore(demand_resid)
    result["oil_specific_risk_shock"] = zscore(risk_resid)
    result["reduced_form_shock"] = zscore(frame["brent_usd_bbl_log_return"])
    result["source_vintage"] = "EIA_STEO_July_2026_ex_post_2022plus"
    save_csv(result, "q1_structural_shocks.csv")
    return result


def gjr_garch_variance(returns: pd.Series) -> tuple[np.ndarray, dict[str, float]]:
    y = returns.dropna().to_numpy(dtype=float)
    y = y - np.mean(y)
    if len(y) < 80:
        raise ValueError("GJR-GARCH needs at least 80 daily return observations.")
    sample_var = float(np.var(y, ddof=1))

    def neg_loglike(params: np.ndarray) -> float:
        omega, alpha, gamma, beta = params
        if omega <= 0 or alpha < 0 or gamma < 0 or beta < 0 or alpha + 0.5 * gamma + beta >= 0.999:
            return 1e12
        h = np.empty_like(y)
        h[0] = sample_var
        for idx in range(1, len(y)):
            lag_eps = y[idx - 1]
            h[idx] = omega + alpha * lag_eps**2 + gamma * (lag_eps < 0) * lag_eps**2 + beta * h[idx - 1]
            if h[idx] <= 0 or not np.isfinite(h[idx]):
                return 1e12
        return float(0.5 * np.sum(np.log(2 * np.pi) + np.log(h) + y**2 / h))

    constraints = ({"type": "ineq", "fun": lambda p: 0.999 - p[1] - 0.5 * p[2] - p[3]},)
    fit = minimize(
        neg_loglike,
        x0=np.array([0.02 * sample_var, 0.05, 0.05, 0.88]),
        bounds=[(1e-9, None), (0.0, 1.0), (0.0, 1.0), (0.0, 0.999)],
        constraints=constraints,
        method="SLSQP",
        options={"maxiter": 500, "ftol": 1e-9},
    )
    if not fit.success:
        raise RuntimeError(f"GJR-GARCH optimization failed: {fit.message}")
    omega, alpha, gamma, beta = fit.x
    h = np.empty_like(y)
    h[0] = sample_var
    for idx in range(1, len(y)):
        lag_eps = y[idx - 1]
        h[idx] = omega + alpha * lag_eps**2 + gamma * (lag_eps < 0) * lag_eps**2 + beta * h[idx - 1]
    return h, {"omega": float(omega), "alpha": float(alpha), "gamma": float(gamma), "beta": float(beta)}


def volatility_module(daily: pd.DataFrame, event_start: pd.Timestamp) -> pd.DataFrame:
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.loc[frame["date"].between(pd.Timestamp("2024-01-01"), CUTOFF)].sort_values("date").copy()
    frame["return_pct"] = frame["brent_usd_bbl_log_return"] * 100.0
    usable = frame.dropna(subset=["return_pct"]).copy()
    train = usable.loc[usable["date"].lt(event_start)].copy()
    h_train, params = gjr_garch_variance(train["return_pct"])
    omega, alpha, gamma, beta = params["omega"], params["alpha"], params["gamma"], params["beta"]
    y = usable["return_pct"].to_numpy(dtype=float)
    y = y - float(train["return_pct"].mean())
    h = np.empty(len(y), dtype=float)
    h[: len(h_train)] = h_train
    for idx in range(len(h_train), len(y)):
        lag_eps = y[idx - 1]
        h[idx] = omega + alpha * lag_eps**2 + gamma * (lag_eps < 0) * lag_eps**2 + beta * h[idx - 1]
    usable["conditional_vol_pct"] = np.sqrt(h)
    pre_median = float(np.nanmedian(usable.loc[usable["date"].lt(event_start), "conditional_vol_pct"]))
    usable["abnormal_vol_ratio_vs_pre_median"] = usable["conditional_vol_pct"] / pre_median - 1.0
    usable["model"] = "GJR_GARCH_1_1"
    usable["specification"] = "normal-likelihood GJR-GARCH(1,1) fitted on pre-E1 Brent daily returns"
    for key, value in params.items():
        usable[key] = value
    output = usable[
        [
            "date",
            "return_pct",
            "conditional_vol_pct",
            "abnormal_vol_ratio_vs_pre_median",
            "model",
            "specification",
            "omega",
            "alpha",
            "gamma",
            "beta",
        ]
    ]
    save_csv(output, "q1_volatility.csv")
    return output


def make_q1_shocks(monthly: pd.DataFrame, counterfactual: pd.DataFrame) -> pd.DataFrame:
    shocks = monthly_shock_residuals(monthly)
    structural = structural_shock_decomposition(monthly)
    shocks = shocks.merge(structural, on="period", how="left")
    if counterfactual.empty:
        baseline = pd.DataFrame({"period": shocks["period"], "ARBaselineGap": 0.0})
    else:
        baseline = (
            counterfactual.groupby("period", as_index=False)
            .agg(ARBaselineGap=("ar_baseline_gap_usd_bbl", "mean"), ARBaselineGap_days=("ar_baseline_gap_usd_bbl", "count"))
        )
    shocks = shocks.merge(baseline, on="period", how="left")
    shocks["ARBaselineGap"] = shocks["ARBaselineGap"].fillna(0.0)
    shocks["ARBaselineGap_days"] = shocks["ARBaselineGap_days"].fillna(0).astype(int) if "ARBaselineGap_days" in shocks else 0
    shocks["random_seed"] = RANDOM_SEED
    save_csv(shocks, "q1_monthly_shocks.csv")
    return shocks


def plot_forecasts(forecasts: pd.DataFrame) -> None:
    if forecasts.empty:
        return
    one = forecasts.loc[forecasts["horizon"].eq(1)].copy()
    if one.empty:
        return
    one["date"] = pd.to_datetime(one["period"] + "-01") + pd.offsets.MonthEnd(0)
    pivot = one.pivot_table(index="date", columns="model", values="prediction_price", aggfunc="first")
    actual = one.drop_duplicates("date").set_index("date")["actual_price"]
    fig, ax = plt.subplots(figsize=(9.2, 5.1))
    ax.plot(actual.index, actual, label="实际 Brent", color=PALETTE["ink"], linewidth=2.0)
    style_map = {
        "no_change": (PALETTE["slate"], (0, (2, 2)), "不变预测"),
        "ARIMA": (PALETTE["gold"], (0, (4, 2)), "ARIMA"),
        "SARIMAX": (PALETTE["blue"], "solid", "SARIMAX"),
    }
    for model in ["no_change", "ARIMA", "SARIMAX"]:
        if model in pivot.columns:
            color, linestyle, label = style_map[model]
            ax.plot(pivot.index, pivot[model], label=label, color=color, linestyle=linestyle, linewidth=1.55)
    style_axis(ax, ylabel="美元/桶")
    ax.legend(loc="upper left", ncol=2, handlelength=2.8)
    finish_figure(
        fig,
        title="问题一：Brent 一个月期滚动预测",
        subtitle="月度 Brent 现货价，滚动起点评估区间为 2020-01 至 2026-06。",
        source="来源：FRED/EIA 处理面板；由 code/problem1/run_q1.py 生成。",
    )
    save_figure(fig, FIGURES_DIR / "q1_forecast_1m")
    plt.close(fig)


def plot_counterfactual(counterfactual: pd.DataFrame) -> None:
    if counterfactual.empty:
        return
    frame = counterfactual.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    fig, ax = plt.subplots(figsize=(9.2, 5.1))
    ax.plot(frame["date"], frame["actual"], label="实际 Brent", color=PALETTE["ink"], linewidth=2.0)
    ax.plot(frame["date"], frame["prediction"], label="AR基准情景路径", color=PALETTE["blue"], linewidth=1.65)
    ax.fill_between(
        frame["date"],
        frame["lower_80"],
        frame["upper_80"],
        color=PALETTE["blue_light"],
        alpha=0.28,
        linewidth=0,
        label="80%区间",
    )
    for event_date, label, ypos in [
        (pd.Timestamp("2026-03-02"), "E1", 0.95),
        (pd.Timestamp("2026-03-05"), "E2", 0.88),
        (pd.Timestamp("2026-06-17"), "E3", 0.95),
    ]:
        ax.axvline(event_date, color=PALETTE["muted"], linewidth=0.7, linestyle=(0, (2, 2)))
        ax.text(
            event_date,
            ypos,
            label,
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=8.5,
            color=PALETTE["muted"],
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.2, "alpha": 0.85},
        )
    style_axis(ax, ylabel="美元/桶")
    ax.legend(loc="upper left", ncol=3, handlelength=2.8)
    finish_figure(
        fig,
        title="问题一：事件后 Brent 油价与 AR 基准路径",
        subtitle="日度 AR(3)+美元基准情景，事件窗口 2026-03-02 至 2026-06-30；不作战争因果贡献解释。",
        source="来源：FRED Brent 与广义美元指数；由 code/problem1/run_q1.py 生成。",
    )
    save_figure(fig, FIGURES_DIR / "q1_war_counterfactual")
    plt.close(fig)


def refresh_placebo_pvalues() -> dict[str, Any]:
    placebo_path = RESULTS_DIR / "q1_placebo_distribution.csv"
    effects_path = RESULTS_DIR / "q1_event_effects.csv"
    summary_path = RESULTS_DIR / "q1_summary.json"
    robustness_path = RESULTS_DIR / "q1_robustness.csv"
    if not placebo_path.exists() or not effects_path.exists() or not summary_path.exists():
        raise FileNotFoundError("Saved Q1 placebo, event-effect, and summary outputs are required.")

    placebos = pd.read_csv(placebo_path)
    effects = pd.read_csv(effects_path)
    actual = effects.loc[effects["model"].eq("brent_usd_bbl_event_car")].copy()
    empirical: dict[str, float] = {}
    for stage_id, group in placebos.groupby("stage_id"):
        actual_row = actual.loc[actual["stage_id"].eq(stage_id)]
        if actual_row.empty:
            continue
        empirical[stage_id] = finite_sample_empirical_pvalue(
            group["estimate_log_return"],
            float(actual_row["estimate_log_return"].iloc[0]),
        )

    placebos["actual_empirical_pvalue"] = placebos["stage_id"].map(empirical)
    event_mask = effects["model"].eq("brent_usd_bbl_event_car")
    effects.loc[event_mask, "pvalue_empirical"] = effects.loc[event_mask, "stage_id"].map(empirical)
    save_csv(placebos, "q1_placebo_distribution.csv")
    save_csv(effects, "q1_event_effects.csv")

    if robustness_path.exists():
        robustness = pd.read_csv(robustness_path)
        placebo_mask = robustness.get("robustness_type", pd.Series(index=robustness.index, dtype=object)).eq(
            "matched_weekend_placebo_distribution"
        )
        if "actual_empirical_pvalue" in robustness.columns:
            robustness.loc[placebo_mask, "actual_empirical_pvalue"] = robustness.loc[placebo_mask, "stage_id"].map(empirical)
            save_csv(robustness, "q1_robustness.csv")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["placebo_min_empirical_pvalue"] = min(empirical.values()) if empirical else None
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "PASS",
        "mode": "refresh-placebo-only",
        "empirical_pvalues": empirical,
        "placebo_rows": int(len(placebos)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh-placebo-only",
        action="store_true",
        help="Apply finite-sample empirical-p corrections to saved Q1 outputs without refitting models.",
    )
    parser.add_argument("--plots-only", action="store_true", help="Regenerate Q1 figures from saved result tables.")
    args = parser.parse_args(argv)

    np.random.seed(RANDOM_SEED)
    apply_paper_style()
    py_warnings.filterwarnings("ignore", category=ValueWarning)
    py_warnings.filterwarnings("ignore", category=FutureWarning, message="No supported index*")
    ensure_dirs()
    if args.refresh_placebo_only:
        payload = refresh_placebo_pvalues()
        print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    if args.plots_only:
        forecasts = pd.read_csv(RESULTS_DIR / "q1_forecasts.csv")
        counterfactual = pd.read_csv(RESULTS_DIR / "q1_daily_counterfactual.csv")
        plot_forecasts(forecasts)
        plot_counterfactual(counterfactual)
        print(json.dumps({"status": "PASS", "mode": "plots-only", "figures": 2}, ensure_ascii=False, indent=2))
        return 0

    warnings_log: list[dict[str, Any]] = []
    monthly = pd.read_csv(PROCESSED_DIR / "model_monthly_q1.csv", parse_dates=["month_end"])
    daily = pd.read_csv(PROCESSED_DIR / "model_daily_q1.csv", parse_dates=["date"])
    daily, event_meta = assign_event_stages(daily, None, "brent_usd_bbl")

    forecasts, metrics = monthly_forecasts(monthly, warnings_log)
    stage_effects = pd.concat(
        [
            stage_effect_regression(daily, "brent_usd_bbl", "main Brent event-stage dummy with Newey-West SE"),
            stage_effect_regression(daily, "wti_usd_bbl", "WTI robustness event-stage dummy with Newey-West SE"),
        ],
        ignore_index=True,
    )
    event_start = pd.Timestamp(event_meta["e1_trading_start"])
    car_effects_raw = pd.concat(
        [
            event_car_rows(daily, "brent_usd_bbl", event_start, "brent_usd_bbl_event_car"),
            event_car_rows(daily, "wti_usd_bbl", event_start, "wti_usd_bbl_event_car"),
        ],
        ignore_index=True,
    )
    placebos = placebo_distribution(daily, car_effects_raw)
    car_effects = add_empirical_pvalues(car_effects_raw, placebos)
    effects = pd.concat([stage_effects, car_effects], ignore_index=True, sort=False)
    save_csv(effects, "q1_event_effects.csv")
    volatility = volatility_module(daily, event_start)
    counterfactual = daily_counterfactual(daily)
    shocks = make_q1_shocks(monthly, counterfactual)
    robustness = robustness_summary(forecasts, effects, daily, placebos)
    plot_forecasts(forecasts)
    plot_counterfactual(counterfactual)

    advanced_non_pass = []
    if not metrics.empty and "model_status" in metrics.columns:
        advanced_non_pass = metrics.loc[
            metrics["model"].ne("no_change") & metrics["model_status"].ne("PASS"),
            ["model", "horizon", "relative_RMSE_vs_no_change", "model_status"],
        ]
        advanced_non_pass = json_records(advanced_non_pass)
    placebo_min_p = (
        float(car_effects.loc[car_effects["model"].eq("brent_usd_bbl_event_car"), "pvalue_empirical"].dropna().min())
        if "pvalue_empirical" in car_effects and not car_effects.loc[car_effects["model"].eq("brent_usd_bbl_event_car"), "pvalue_empirical"].dropna().empty
        else np.nan
    )
    status = "PASS"
    if warnings_log:
        status = "CONDITIONAL"
    summary = {
        "status": status,
        "random_seed": RANDOM_SEED,
        "event_calendar": event_meta,
        "selected_forecast_model": "no_change",
        "forecast_model_non_pass": advanced_non_pass,
        "placebo_min_empirical_pvalue": placebo_min_p if np.isfinite(placebo_min_p) else None,
        "forecast_rows": int(len(forecasts)),
        "metric_rows": int(len(metrics)),
        "event_effect_rows": int(len(effects)),
        "placebo_rows": int(len(placebos)),
        "shock_rows": int(len(shocks)),
        "volatility_rows": int(len(volatility)),
        "robustness_rows": int(len(robustness)),
        "warnings": warnings_log,
        "main_metric_best_rmse": json_records(metrics.sort_values("RMSE").head(1)) if not metrics.empty else [],
    }
    (RESULTS_DIR / "q1_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
