"""Question 1: oil-price forecasts and war-shock counterfactuals."""

from __future__ import annotations

import json
import math
import warnings as py_warnings
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm
from statsmodels.tools.sm_exceptions import ValueWarning
from statsmodels.tsa.statespace.sarimax import SARIMAX


REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
RESULTS_DIR = REPO_ROOT / "results"
FIGURES_DIR = REPO_ROOT / "figures"
CUTOFF = pd.Timestamp("2026-06-30")
RANDOM_SEED = 20260730
EVAL_START = "2020-01"


def ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)


def save_csv(frame: pd.DataFrame, filename: str) -> Path:
    path = RESULTS_DIR / filename
    frame.to_csv(path, index=False, encoding="utf-8")
    return path


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
            except Exception as exc:
                rows.append({"model": "ARIMA", "order": str(order), "aic": np.nan, "error": str(exc)})
            try:
                result = fit_sarimax(train_full["log_brent"], order, train_exog.loc[train_full.index])
                rows.append({"model": "SARIMAX", "order": str(order), "aic": float(result.aic)})
                if result.aic < best_sarimax[1]:
                    best_sarimax = (order, float(result.aic))
            except Exception as exc:
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
                    "period": target_period,
                    "horizon": horizon,
                    "model": "no_change",
                    "actual": float(target["log_brent"]),
                    "prediction": no_change,
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
                            "period": target_period,
                            "horizon": horizon,
                            "model": model_name,
                            "actual": float(target["log_brent"]),
                            "prediction": mean,
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
                except Exception as exc:
                    warnings_log.append(
                        {
                            "code": "monthly_forecast_model_failed",
                            "message": f"{model_name} h={horizon} target={target_period}: {exc}",
                        }
                    )

    forecasts = pd.DataFrame(rows)
    save_csv(forecasts, "q1_forecasts.csv")
    metrics = forecast_metrics(forecasts)
    save_csv(metrics, "q1_forecast_metrics.csv")
    return forecasts, metrics


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
        actual_dir = np.sign(group["actual"].diff())
        pred_dir = np.sign(group["prediction"].diff())
        direction_accuracy = float((actual_dir.eq(pred_dir)).iloc[1:].mean()) if len(group) > 2 else np.nan
        rows.append(
            {
                "model": model,
                "horizon": int(horizon),
                "n": int(len(group)),
                "MAE": float(group["abs_error"].mean()),
                "RMSE": float(np.sqrt(group["squared_error"].mean())),
                "direction_accuracy": direction_accuracy,
                "coverage_80": float(group["covered_80"].mean()),
                "coverage_95": float(group["covered_95"].mean()),
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
    regressors = [f"{return_col}_lag{lag}" for lag in [1, 2, 3]] + ["usd_broad_index_log_return", "stage_E1", "stage_E2", "stage_E3"]
    usable = frame.dropna(subset=[return_col] + regressors)
    if usable.empty:
        return pd.DataFrame()
    x = sm.add_constant(usable[regressors], has_constant="add")
    fit = sm.OLS(usable[return_col], x).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    rows: list[dict[str, Any]] = []
    for term in ["stage_E1", "stage_E2", "stage_E3"]:
        estimate = float(fit.params.get(term, np.nan))
        se = float(fit.bse.get(term, np.nan))
        rows.append(
            {
                "stage_id": term.replace("stage_", ""),
                "model": f"{price_prefix}_stage_dummy",
                "specification": specification,
                "estimate_log_return": estimate,
                "std_error": se,
                "lower_80": estimate - norm.ppf(0.90) * se,
                "upper_80": estimate + norm.ppf(0.90) * se,
                "lower_95": estimate - norm.ppf(0.975) * se,
                "upper_95": estimate + norm.ppf(0.975) * se,
                "pvalue": float(fit.pvalues.get(term, np.nan)),
                "sample_start": str(usable["date"].min().date()),
                "sample_end": str(usable["date"].max().date()),
                "n": int(len(usable)),
            }
        )
    return pd.DataFrame(rows)


def placebo_effect_regression(daily: pd.DataFrame) -> pd.DataFrame:
    frame = daily.copy()
    date = pd.to_datetime(frame["date"])
    frame["stage_E1"] = date.between(pd.Timestamp("2025-02-28"), pd.Timestamp("2025-03-01")).astype(int)
    frame["stage_E2"] = date.between(pd.Timestamp("2025-03-02"), pd.Timestamp("2025-06-16")).astype(int)
    frame["stage_E3"] = date.between(pd.Timestamp("2025-06-17"), pd.Timestamp("2025-06-30")).astype(int)
    return stage_effect_regression(frame, "brent_usd_bbl", "placebo stages shifted to 2025")


def shifted_event_regression(daily: pd.DataFrame, shift_days: int) -> pd.DataFrame:
    frame = daily.copy()
    date = pd.to_datetime(frame["date"])
    e1 = pd.Timestamp("2026-02-28") + pd.Timedelta(days=shift_days)
    e2 = pd.Timestamp("2026-03-02") + pd.Timedelta(days=shift_days)
    e3 = pd.Timestamp("2026-06-17") + pd.Timedelta(days=shift_days)
    frame["stage_E1"] = date.between(e1, e2 - pd.Timedelta(days=1)).astype(int)
    frame["stage_E2"] = date.between(e2, e3 - pd.Timedelta(days=1)).astype(int)
    frame["stage_E3"] = (date >= e3).astype(int)
    result = stage_effect_regression(frame, "brent_usd_bbl", f"event dates shifted by {shift_days} days")
    if not result.empty:
        result["model"] = f"brent_alt_event_shift_{shift_days:+d}d"
    return result


def robustness_summary(forecasts: pd.DataFrame, effects: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
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
    placebo = effects.loc[effects["model"].eq("brent_placebo_2025")].copy()
    if not placebo.empty:
        placebo["robustness_type"] = "placebo_2025"
        pieces.append(placebo)
    for shift in [-5, 5]:
        alt = shifted_event_regression(daily, shift)
        if not alt.empty:
            alt["robustness_type"] = f"event_shift_{shift:+d}d"
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

    event = frame.loc[frame["date"].between(pd.Timestamp("2026-02-28"), CUTOFF)].copy()
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
        premium = float(row["brent_usd_bbl"] - prediction)
        lower_80_log, upper_80_log = forecast_interval(cf_log, sigma, len(rows) + 1, 0.20)
        lower_95_log, upper_95_log = forecast_interval(cf_log, sigma, len(rows) + 1, 0.05)
        rows.append(
            {
                "date": row["date"].strftime("%Y-%m-%d"),
                "period": row["date"].to_period("M").strftime("%Y-%m"),
                "actual": float(row["brent_usd_bbl"]),
                "prediction": prediction,
                "response": premium,
                "lower_80": float(np.exp(lower_80_log)),
                "upper_80": float(np.exp(upper_80_log)),
                "lower_95": float(np.exp(lower_95_log)),
                "upper_95": float(np.exp(upper_95_log)),
                "actual_log": actual_log,
                "counterfactual_log": cf_log,
                "war_premium_usd_bbl": premium,
                "war_stage": row["war_stage"],
                "model": "AR3_plus_USD_counterfactual",
                "horizon": len(rows) + 1,
                "specification": "trained 2024-01-01 to 2026-02-27",
                "sample_start": "2024-01-01",
                "sample_end": "2026-02-27",
            }
        )
    counterfactual = pd.DataFrame(rows)
    save_csv(counterfactual, "q1_daily_counterfactual.csv")
    return counterfactual


def make_q1_shocks(monthly: pd.DataFrame, counterfactual: pd.DataFrame) -> pd.DataFrame:
    shocks = monthly_shock_residuals(monthly)
    if counterfactual.empty:
        war = pd.DataFrame({"period": shocks["period"], "WarPremium": 0.0})
    else:
        war = (
            counterfactual.groupby("period", as_index=False)
            .agg(WarPremium=("war_premium_usd_bbl", "mean"), WarPremium_days=("war_premium_usd_bbl", "count"))
        )
    shocks = shocks.merge(war, on="period", how="left")
    shocks["WarPremium"] = shocks["WarPremium"].fillna(0.0)
    shocks["WarPremium_days"] = shocks["WarPremium_days"].fillna(0).astype(int) if "WarPremium_days" in shocks else 0
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
    plt.figure(figsize=(10, 5))
    plt.plot(actual.index, actual, label="Actual Brent", color="black", linewidth=1.8)
    for model in ["no_change", "ARIMA", "SARIMAX"]:
        if model in pivot.columns:
            plt.plot(pivot.index, pivot[model], label=model, linewidth=1.2)
    plt.title("Q1 Brent one-month-ahead forecasts")
    plt.ylabel("USD per barrel")
    plt.legend()
    plt.tight_layout()
    for suffix in ["png", "pdf"]:
        plt.savefig(FIGURES_DIR / f"q1_forecast_1m.{suffix}", dpi=180)
    plt.close()


def plot_counterfactual(counterfactual: pd.DataFrame) -> None:
    if counterfactual.empty:
        return
    frame = counterfactual.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    plt.figure(figsize=(10, 5))
    plt.plot(frame["date"], frame["actual"], label="Actual Brent", color="black", linewidth=1.8)
    plt.plot(frame["date"], frame["prediction"], label="No-war counterfactual", color="#2a6fbb", linewidth=1.5)
    plt.fill_between(frame["date"], frame["lower_80"], frame["upper_80"], color="#2a6fbb", alpha=0.18, label="80% interval")
    plt.title("Q1 war-premium counterfactual")
    plt.ylabel("USD per barrel")
    plt.legend()
    plt.tight_layout()
    for suffix in ["png", "pdf"]:
        plt.savefig(FIGURES_DIR / f"q1_war_counterfactual.{suffix}", dpi=180)
    plt.close()


def main() -> int:
    np.random.seed(RANDOM_SEED)
    py_warnings.filterwarnings("ignore", category=ValueWarning)
    py_warnings.filterwarnings("ignore", category=FutureWarning, message="No supported index*")
    ensure_dirs()
    warnings_log: list[dict[str, Any]] = []
    monthly = pd.read_csv(PROCESSED_DIR / "model_monthly_q1.csv", parse_dates=["month_end"])
    daily = pd.read_csv(PROCESSED_DIR / "model_daily_q1.csv", parse_dates=["date"])

    forecasts, metrics = monthly_forecasts(monthly, warnings_log)
    effects = pd.concat(
        [
            stage_effect_regression(daily, "brent_usd_bbl", "main Brent event-stage dummy with Newey-West SE"),
            stage_effect_regression(daily, "wti_usd_bbl", "WTI robustness event-stage dummy with Newey-West SE"),
            placebo_effect_regression(daily).assign(model="brent_placebo_2025"),
        ],
        ignore_index=True,
    )
    save_csv(effects, "q1_event_effects.csv")
    counterfactual = daily_counterfactual(daily)
    shocks = make_q1_shocks(monthly, counterfactual)
    robustness = robustness_summary(forecasts, effects, daily)
    plot_forecasts(forecasts)
    plot_counterfactual(counterfactual)

    summary = {
        "status": "WARN" if warnings_log else "PASS",
        "random_seed": RANDOM_SEED,
        "forecast_rows": int(len(forecasts)),
        "metric_rows": int(len(metrics)),
        "event_effect_rows": int(len(effects)),
        "shock_rows": int(len(shocks)),
        "robustness_rows": int(len(robustness)),
        "warnings": warnings_log,
        "main_metric_best_rmse": metrics.sort_values("RMSE").head(1).to_dict("records") if not metrics.empty else [],
    }
    (RESULTS_DIR / "q1_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
