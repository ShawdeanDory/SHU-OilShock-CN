"""Extension Q4: Brent upper-tail risk and China macro-policy stress tests."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize


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
HORIZON_STEPS = {1: 22, 3: 66, 6: 132}
FORECAST_QUANTILES = [0.05, 0.10, 0.50, 0.90, 0.95]
OUTCOME_LABELS = {
    "china_ppi_yoy_pct": "PPI",
    "china_cpi_yoy_pct": "CPI",
    "china_iav_yoy_pct": "工业增加值",
}


def ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)


def save_csv(frame: pd.DataFrame, filename: str) -> Path:
    path = RESULTS_DIR / filename
    frame.to_csv(path, index=False, encoding="utf-8")
    return path


def write_json(payload: dict[str, Any], filename: str) -> Path:
    path = RESULTS_DIR / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return path


def json_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return json.loads(frame.where(pd.notna(frame), None).to_json(orient="records"))


def load_daily() -> pd.DataFrame:
    path = PROCESSED_DIR / "model_daily_q1.csv"
    frame = pd.read_csv(path, parse_dates=["date"])
    required = {"date", "brent_usd_bbl", "brent_usd_bbl_log_return"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Q4 daily input missing columns: {sorted(missing)}")
    frame = frame.loc[frame["date"].le(CUTOFF)].copy()
    frame["brent_usd_bbl"] = pd.to_numeric(frame["brent_usd_bbl"], errors="coerce")
    frame["return_pct"] = pd.to_numeric(frame["brent_usd_bbl_log_return"], errors="coerce") * 100.0
    frame = frame.dropna(subset=["date", "brent_usd_bbl", "return_pct"]).sort_values("date").reset_index(drop=True)
    if len(frame) < 750:
        raise ValueError(f"Q4 needs at least 750 daily returns, got {len(frame)}")
    if frame["date"].max() != CUTOFF:
        raise ValueError(f"Q4 last daily observation must be {CUTOFF.date()}, got {frame['date'].max().date()}")
    return frame


def _variance_path(eps: np.ndarray, params: np.ndarray, sample_var: float) -> np.ndarray:
    omega, alpha, gamma, beta = params
    h = np.empty(len(eps), dtype=float)
    h[0] = sample_var
    for idx in range(1, len(eps)):
        lag = eps[idx - 1]
        h[idx] = omega + alpha * lag**2 + gamma * (lag < 0) * lag**2 + beta * h[idx - 1]
    return h


def fit_gjr_garch(returns_pct: pd.Series) -> dict[str, Any]:
    values = pd.to_numeric(returns_pct, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) < 500:
        raise ValueError(f"GJR-GARCH needs at least 500 observations, got {len(values)}")
    mu = float(np.mean(values))
    eps = values - mu
    sample_var = float(np.var(eps, ddof=1))
    if not np.isfinite(sample_var) or sample_var <= 0:
        raise ValueError("GJR-GARCH sample variance is not positive.")

    def neg_loglike(params: np.ndarray) -> float:
        omega, alpha, gamma, beta = params
        persistence = alpha + 0.5 * gamma + beta
        if omega <= 0 or min(alpha, gamma, beta) < 0 or persistence >= 0.999:
            return 1e15
        h = _variance_path(eps, params, sample_var)
        if np.any(~np.isfinite(h)) or np.any(h <= 0):
            return 1e15
        return float(0.5 * np.sum(np.log(2 * np.pi) + np.log(h) + eps**2 / h))

    starts = [
        np.array([0.02 * sample_var, 0.05, 0.05, 0.88]),
        np.array([0.03 * sample_var, 0.08, 0.02, 0.86]),
        np.array([0.05 * sample_var, 0.10, 0.00, 0.80]),
    ]
    constraints = ({"type": "ineq", "fun": lambda p: 0.999 - p[1] - 0.5 * p[2] - p[3]},)
    fits = []
    for start in starts:
        fit = minimize(
            neg_loglike,
            x0=start,
            bounds=[(1e-10, None), (0.0, 1.0), (0.0, 1.0), (0.0, 0.999)],
            constraints=constraints,
            method="SLSQP",
            options={"maxiter": 600, "ftol": 1e-9},
        )
        if fit.success and np.isfinite(fit.fun):
            fits.append(fit)
    if not fits:
        raise RuntimeError("All GJR-GARCH optimization starts failed.")
    fit = min(fits, key=lambda item: float(item.fun))
    params = np.asarray(fit.x, dtype=float)
    h = _variance_path(eps, params, sample_var)
    z = eps / np.sqrt(h)
    z = z[np.isfinite(z)]
    z_std = float(np.std(z, ddof=1))
    if len(z) < 400 or not np.isfinite(z_std) or z_std <= 0:
        raise RuntimeError("GJR-GARCH standardized residuals are unusable.")
    z = (z - float(np.mean(z))) / z_std
    omega, alpha, gamma, beta = params
    return {
        "mu": mu,
        "omega": float(omega),
        "alpha": float(alpha),
        "gamma": float(gamma),
        "beta": float(beta),
        "persistence": float(alpha + 0.5 * gamma + beta),
        "last_eps": float(eps[-1]),
        "last_h": float(h[-1]),
        "standardized_residuals": z,
        "n": int(len(values)),
        "objective": float(fit.fun),
    }


def simulate_fhs(
    start_price: float,
    fit: dict[str, Any],
    steps: int,
    paths: int,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    prices = np.empty((paths, steps), dtype=float)
    log_price = np.full(paths, math.log(start_price), dtype=float)
    h_prev = np.full(paths, float(fit["last_h"]), dtype=float)
    eps_prev = np.full(paths, float(fit["last_eps"]), dtype=float)
    residuals = np.asarray(fit["standardized_residuals"], dtype=float)
    omega = float(fit["omega"])
    alpha = float(fit["alpha"])
    gamma = float(fit["gamma"])
    beta = float(fit["beta"])
    mu = float(fit["mu"])
    for step in range(steps):
        h = omega + alpha * eps_prev**2 + gamma * (eps_prev < 0) * eps_prev**2 + beta * h_prev
        h = np.maximum(h, 1e-10)
        z = rng.choice(residuals, size=paths, replace=True)
        eps = np.sqrt(h) * z
        log_price += (mu + eps) / 100.0
        prices[:, step] = np.exp(log_price)
        h_prev = h
        eps_prev = eps
    return prices


def simulate_gaussian(
    start_price: float,
    returns_pct: pd.Series,
    steps: int,
    paths: int,
    seed: int,
) -> np.ndarray:
    values = pd.to_numeric(returns_pct, errors="coerce").dropna().to_numpy(dtype=float)
    mu = float(np.mean(values))
    sigma = float(np.std(values, ddof=1))
    if not np.isfinite(sigma) or sigma <= 0:
        raise ValueError("Gaussian baseline volatility is not positive.")
    rng = np.random.default_rng(seed)
    draws = rng.normal(mu, sigma, size=(paths, steps)) / 100.0
    return start_price * np.exp(np.cumsum(draws, axis=1))


def historical_thresholds(daily: pd.DataFrame) -> dict[str, float]:
    prices = daily["brent_usd_bbl"].dropna()
    return {
        "historical_price_p90": float(prices.quantile(0.90)),
        "historical_price_p95": float(prices.quantile(0.95)),
    }


def summarize_paths(
    paths: np.ndarray,
    model: str,
    origin_date: pd.Timestamp,
    origin_price: float,
    thresholds: dict[str, float],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for horizon, steps in HORIZON_STEPS.items():
        terminal = paths[:, steps - 1]
        prefix = paths[:, :steps]
        quantiles = np.quantile(terminal, FORECAST_QUANTILES)
        threshold_90 = thresholds["historical_price_p90"]
        threshold_95 = thresholds["historical_price_p95"]
        upper_tail = terminal[terminal > threshold_95]
        rows.append(
            {
                "origin_date": origin_date.strftime("%Y-%m-%d"),
                "origin_price_usd_bbl": origin_price,
                "horizon_months": horizon,
                "trading_days": steps,
                "model": model,
                "paths": int(len(terminal)),
                "p05_price": float(quantiles[0]),
                "p10_price": float(quantiles[1]),
                "median_price": float(quantiles[2]),
                "p90_price": float(quantiles[3]),
                "p95_price": float(quantiles[4]),
                "historical_price_p90": threshold_90,
                "historical_price_p95": threshold_95,
                "terminal_prob_above_hist_p90": float(np.mean(terminal > threshold_90)),
                "terminal_prob_above_hist_p95": float(np.mean(terminal > threshold_95)),
                "path_prob_cross_hist_p90": float(np.mean(np.max(prefix, axis=1) > threshold_90)),
                "path_prob_cross_hist_p95": float(np.mean(np.max(prefix, axis=1) > threshold_95)),
                "upper_tail_mean_above_hist_p95": float(np.mean(upper_tail)) if len(upper_tail) else np.nan,
                "evidence_status": "PROBABILISTIC_STRESS_FORECAST",
            }
        )
    return pd.DataFrame(rows)


def pinball(actual: float, prediction: float, quantile: float) -> float:
    error = actual - prediction
    return float(max(quantile * error, (quantile - 1.0) * error))


def backtest_origins(daily: pd.DataFrame) -> pd.DataFrame:
    candidates = daily.loc[daily["date"].between(pd.Timestamp("2022-01-01"), pd.Timestamp("2025-12-31"))].copy()
    candidates["quarter"] = candidates["date"].dt.to_period("Q")
    candidates = candidates.groupby("quarter", as_index=False).tail(1)
    max_step = max(HORIZON_STEPS.values())
    candidates = candidates.loc[candidates.index + max_step < len(daily)].copy()
    return candidates


def run_backtest(
    daily: pd.DataFrame,
    paths: int,
    seed: int,
    max_origins: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    origins = backtest_origins(daily)
    if max_origins is not None:
        origins = origins.tail(max_origins)
    origin_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    max_step = max(HORIZON_STEPS.values())
    for origin_number, (idx, origin) in enumerate(origins.iterrows()):
        train = daily.iloc[: idx + 1].copy()
        fit = fit_gjr_garch(train["return_pct"])
        fhs_paths = simulate_fhs(
            float(origin["brent_usd_bbl"]), fit, max_step, paths, seed + origin_number * 101
        )
        gaussian_paths = simulate_gaussian(
            float(origin["brent_usd_bbl"]), train["return_pct"], max_step, paths, seed + origin_number * 101 + 1
        )
        for model, simulated in [("FHS_GJR_GARCH", fhs_paths), ("Gaussian_random_walk", gaussian_paths)]:
            for horizon, steps in HORIZON_STEPS.items():
                target = daily.iloc[idx + steps]
                actual = float(target["brent_usd_bbl"])
                terminal = simulated[:, steps - 1]
                q = np.quantile(terminal, FORECAST_QUANTILES)
                losses = [pinball(actual, float(pred), tau) for pred, tau in zip(q, FORECAST_QUANTILES)]
                origin_rows.append(
                    {
                        "origin_date": origin["date"].strftime("%Y-%m-%d"),
                        "target_date": target["date"].strftime("%Y-%m-%d"),
                        "horizon_months": horizon,
                        "model": model,
                        "actual_price": actual,
                        "p05_price": float(q[0]),
                        "p10_price": float(q[1]),
                        "median_price": float(q[2]),
                        "p90_price": float(q[3]),
                        "p95_price": float(q[4]),
                        "mean_pinball_loss": float(np.mean(losses)),
                        "median_absolute_error": float(abs(actual - q[2])),
                        "covered_80": bool(q[1] <= actual <= q[3]),
                        "covered_90": bool(q[0] <= actual <= q[4]),
                        "interval_width_80": float(q[3] - q[1]),
                        "interval_width_90": float(q[4] - q[0]),
                        "train_end": origin["date"].strftime("%Y-%m-%d"),
                        "no_future_information": bool(target["date"] > origin["date"]),
                    }
                )
    detailed = pd.DataFrame(origin_rows)
    if detailed.empty:
        return detailed, pd.DataFrame(), warnings
    summary = (
        detailed.groupby(["model", "horizon_months"], as_index=False)
        .agg(
            origins=("origin_date", "count"),
            mean_pinball_loss=("mean_pinball_loss", "mean"),
            median_absolute_error=("median_absolute_error", "median"),
            coverage_80=("covered_80", "mean"),
            coverage_90=("covered_90", "mean"),
            mean_width_80=("interval_width_80", "mean"),
            mean_width_90=("interval_width_90", "mean"),
            all_no_future_information=("no_future_information", "all"),
        )
        .sort_values(["horizon_months", "model"])
        .reset_index(drop=True)
    )
    summary["model_role"] = np.where(summary["model"].eq("FHS_GJR_GARCH"), "main", "baseline")
    return detailed, summary, warnings


def build_macro_stress() -> tuple[pd.DataFrame, dict[str, float]]:
    shocks = pd.read_csv(RESULTS_DIR / "q1_structural_shocks.csv")
    values = pd.to_numeric(shocks["oil_specific_risk_shock"], errors="coerce").dropna()
    if len(values) < 120:
        raise ValueError(f"Q4 needs at least 120 oil-specific risk shocks, got {len(values)}")
    scenario_values = {
        "moderate_q75": float(values.quantile(0.75)),
        "severe_q90": float(values.quantile(0.90)),
        "extreme_q95": float(values.quantile(0.95)),
    }
    irf = pd.read_csv(RESULTS_DIR / "q2_irf.csv")
    irf = irf.loc[
        irf["shock"].eq("oil_specific_risk_shock")
        & irf["outcome"].isin(OUTCOME_LABELS)
        & pd.to_numeric(irf["horizon"], errors="coerce").isin([0, 3, 6, 12])
    ].copy()
    required = {"response", "joint_lower_95", "joint_upper_95", "sample_start", "sample_end"}
    missing = required.difference(irf.columns)
    if missing or irf.empty:
        raise ValueError(f"Q4 macro stress missing Q2 IRF fields: {sorted(missing)}")
    rows: list[dict[str, Any]] = []
    for scenario, shock_value in scenario_values.items():
        for row in irf.itertuples(index=False):
            response = float(row.response) * shock_value
            lower = float(row.joint_lower_95) * shock_value
            upper = float(row.joint_upper_95) * shock_value
            rows.append(
                {
                    "scenario": scenario,
                    "shock_quantile_value": shock_value,
                    "shock": "oil_specific_risk_shock",
                    "outcome": row.outcome,
                    "outcome_label": OUTCOME_LABELS[row.outcome],
                    "horizon": int(row.horizon),
                    "conditional_response_pctpt": response,
                    "joint_lower_95": min(lower, upper),
                    "joint_upper_95": max(lower, upper),
                    "joint_ci95_contains_zero": bool(min(lower, upper) <= 0 <= max(lower, upper)),
                    "row_evidence_status": (
                        "INCONCLUSIVE" if min(lower, upper) <= 0 <= max(lower, upper) else "SUPPORTED_JOINT_95"
                    ),
                    "source_q2_evidence_status": "INCONCLUSIVE",
                    "sample_start": row.sample_start,
                    "sample_end": row.sample_end,
                    "specification": "historical positive structural-shock quantile multiplied by Q2 LP response; conditional scenario, not deterministic loss",
                }
            )
    return pd.DataFrame(rows), scenario_values


def build_policy_stress() -> pd.DataFrame:
    source = pd.read_csv(RESULTS_DIR / "q3_policy_macro_counterfactual.csv")
    source = source.loc[source["outcome"].isin(OUTCOME_LABELS)].copy()
    required = {"period", "outcome", "macro_counterfactual_gap_pctpt", "lower_95", "upper_95"}
    missing = required.difference(source.columns)
    if missing or source.empty:
        raise ValueError(f"Q4 policy stress missing Q3 fields: {sorted(missing)}")
    rows: list[dict[str, Any]] = []
    for row in source.itertuples(index=False):
        gap = float(row.macro_counterfactual_gap_pctpt)
        lower = float(row.lower_95)
        upper = float(row.upper_95)
        if row.outcome == "china_iav_yoy_pct":
            benefit = -gap
            benefit_lower = -upper
            benefit_upper = -lower
            interpretation = "actual policy avoided an industrial-activity loss relative to no temporary control"
        else:
            benefit = gap
            benefit_lower = lower
            benefit_upper = upper
            interpretation = "actual policy avoided a price-index increase relative to no temporary control"
        rows.append(
            {
                "period": row.period,
                "outcome": row.outcome,
                "outcome_label": OUTCOME_LABELS[row.outcome],
                "no_policy_minus_actual_gap_pctpt": gap,
                "policy_buffer_benefit_pctpt": benefit,
                "benefit_lower_95": min(benefit_lower, benefit_upper),
                "benefit_upper_95": max(benefit_lower, benefit_upper),
                "evidence_status": (
                    "SUPPORTED_95"
                    if min(benefit_lower, benefit_upper) > 0
                    else "INCONCLUSIVE"
                ),
                "interpretation": interpretation,
                "price_layer_status": row.price_layer_status,
                "source_evidence_status": row.evidence_status,
                "specification": "Q3 realized 2026 no-temporary-control counterfactual restated as policy buffer benefit; not extrapolated to simulated Q4 price paths",
            }
        )
    return pd.DataFrame(rows)


def plot_price_tail_risk(risk: pd.DataFrame) -> None:
    apply_paper_style()
    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    x = np.array([1, 3, 6], dtype=float)
    for model, color, label in [
        ("FHS_GJR_GARCH", PALETTE["blue"], "FHS–GJR-GARCH"),
        ("Gaussian_random_walk", PALETTE["gold"], "高斯随机游走"),
    ]:
        subset = risk.loc[risk["model"].eq(model)].sort_values("horizon_months")
        if subset.empty:
            continue
        xx = subset["horizon_months"].to_numpy(dtype=float)
        median = subset["median_price"].to_numpy(dtype=float)
        ax.plot(xx, median, marker="o", color=color, label=f"{label} 中位数")
        if model == "FHS_GJR_GARCH":
            ax.fill_between(
                xx,
                subset["p05_price"].to_numpy(dtype=float),
                subset["p95_price"].to_numpy(dtype=float),
                color=PALETTE["blue_light"],
                alpha=0.30,
                label="FHS 90%区间",
            )
            ax.fill_between(
                xx,
                subset["p10_price"].to_numpy(dtype=float),
                subset["p90_price"].to_numpy(dtype=float),
                color=PALETTE["blue_light"],
                alpha=0.50,
                label="FHS 80%区间",
            )
    threshold_90 = float(risk["historical_price_p90"].iloc[0])
    threshold_95 = float(risk["historical_price_p95"].iloc[0])
    ax.axhline(threshold_90, color=PALETTE["olive"], linestyle="--", linewidth=1.2, label="历史价格90%分位")
    ax.axhline(threshold_95, color=PALETTE["rose"], linestyle=":", linewidth=1.4, label="历史价格95%分位")
    ax.set_xticks(x, ["1个月", "3个月", "6个月"])
    style_axis(ax, ylabel="Brent价格（美元/桶）", xlabel="预测期限")
    ax.legend(ncol=2, loc="upper left")
    finish_figure(
        fig,
        title="国际油价上行尾部风险",
        subtitle="阴影为FHS条件分布区间，虚线为截止日前历史价格阈值。",
        source="数据：EIA/FRED Brent；计算：FHS–GJR-GARCH 与高斯随机游走，信息截止 2026-06-30。",
    )
    save_figure(fig, FIGURES_DIR / "q4_price_tail_risk")
    plt.close(fig)


def plot_macro_policy_stress(macro: pd.DataFrame, policy: pd.DataFrame) -> None:
    apply_paper_style()
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.8), gridspec_kw={"width_ratios": [1.35, 1.0]})
    left = macro.loc[macro["scenario"].eq("extreme_q95")].copy()
    for outcome, color in [
        ("china_ppi_yoy_pct", PALETTE["gold"]),
        ("china_cpi_yoy_pct", PALETTE["blue"]),
        ("china_iav_yoy_pct", PALETTE["rose"]),
    ]:
        subset = left.loc[left["outcome"].eq(outcome)].sort_values("horizon")
        axes[0].plot(
            subset["horizon"],
            subset["conditional_response_pctpt"],
            marker="o",
            color=color,
            label=OUTCOME_LABELS[outcome],
        )
    axes[0].axhline(0, color=PALETTE["muted"], linewidth=0.8)
    axes[0].set_xticks([0, 3, 6, 12])
    style_axis(axes[0], ylabel="同比增速条件响应（百分点）", xlabel="冲击后月份")
    axes[0].legend(loc="best")

    june = policy.loc[policy["period"].eq("2026-06")].copy()
    order = ["PPI", "CPI", "工业增加值"]
    june["order"] = june["outcome_label"].map({label: idx for idx, label in enumerate(order)})
    june = june.sort_values("order")
    values = june["policy_buffer_benefit_pctpt"].to_numpy(dtype=float)
    lower = june["benefit_lower_95"].to_numpy(dtype=float)
    upper = june["benefit_upper_95"].to_numpy(dtype=float)
    ypos = np.arange(len(june))
    axes[1].barh(ypos, values, color=[PALETTE["gold"], PALETTE["blue"], PALETTE["rose"]])
    axes[1].errorbar(values, ypos, xerr=np.vstack([values - lower, upper - values]), fmt="none", ecolor=PALETTE["ink"], capsize=3)
    axes[1].set_yticks(ypos, june["outcome_label"])
    axes[1].invert_yaxis()
    axes[1].axvline(0, color=PALETTE["muted"], linewidth=0.8)
    style_axis(axes[1], ylabel=None, xlabel="政策缓冲收益（百分点）")
    finish_figure(
        fig,
        title="极端结构冲击的宏观压力与已实现政策缓冲",
        subtitle="左图为95%分位结构冲击条件响应；右图为2026年6月无临时调控相对实际政策路径差额。",
        source="计算：Q1结构冲击分位数、Q2 Local Projection 与 Q3 官方成品油价格层反事实；区间口径见结果表。",
        rect=(0.06, 0.12, 0.99, 0.98),
    )
    save_figure(fig, FIGURES_DIR / "q4_macro_policy_stress")
    plt.close(fig)


def run_probe() -> dict[str, Any]:
    ensure_dirs()
    started = time.perf_counter()
    daily = load_daily()
    fit = fit_gjr_garch(daily["return_pct"])
    thresholds = historical_thresholds(daily)
    max_step = max(HORIZON_STEPS.values())
    start_price = float(daily["brent_usd_bbl"].iloc[-1])
    first = simulate_fhs(start_price, fit, max_step, 500, RANDOM_SEED)
    replay = simulate_fhs(start_price, fit, max_step, 500, RANDOM_SEED)
    alternate = simulate_fhs(start_price, fit, max_step, 500, RANDOM_SEED + 1)
    baseline = simulate_gaussian(start_price, daily["return_pct"], max_step, 500, RANDOM_SEED)
    first_summary = summarize_paths(first, "FHS_GJR_GARCH", CUTOFF, start_price, thresholds)
    alternate_summary = summarize_paths(alternate, "FHS_GJR_GARCH", CUTOFF, start_price, thresholds)
    baseline_summary = summarize_paths(baseline, "Gaussian_random_walk", CUTOFF, start_price, thresholds)
    _, backtest, backtest_warnings = run_backtest(daily, paths=300, seed=RANDOM_SEED, max_origins=3)
    macro, scenario_values = build_macro_stress()
    policy = build_policy_stress()
    prob_columns = ["terminal_prob_above_hist_p90", "terminal_prob_above_hist_p95"]
    seed_sensitivity = float(
        np.max(
            np.abs(
                first_summary[prob_columns].to_numpy(dtype=float)
                - alternate_summary[prob_columns].to_numpy(dtype=float)
            )
        )
    )
    checks = {
        "daily_rows_at_least_750": len(daily) >= 750,
        "cutoff_exact": daily["date"].max() == CUTOFF,
        "gjr_persistence_below_one": 0 <= fit["persistence"] < 0.999,
        "fhs_distribution_non_degenerate": bool((first_summary["p95_price"] > first_summary["p05_price"]).all()),
        "baseline_distribution_non_degenerate": bool((baseline_summary["p95_price"] > baseline_summary["p05_price"]).all()),
        "fixed_seed_exact_replay": bool(np.array_equal(first, replay)),
        "seed_sensitivity_below_0_15": seed_sensitivity <= 0.15,
        "representative_backtest_complete": len(backtest) == 6 and bool(backtest["all_no_future_information"].all()),
        "macro_three_outcomes_present": set(macro["outcome"]) == set(OUTCOME_LABELS),
        "macro_three_scenarios_present": len(scenario_values) == 3,
        "policy_three_outcomes_present": set(policy["outcome"]) == set(OUTCOME_LABELS),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    payload = {
        "status": status,
        "method": "FHS_GJR_GARCH",
        "role": "main",
        "baseline": "Gaussian_random_walk",
        "data_range": [daily["date"].min().strftime("%Y-%m-%d"), daily["date"].max().strftime("%Y-%m-%d")],
        "random_seed": RANDOM_SEED,
        "probe_paths": 500,
        "representative_backtest_origins": 3,
        "checks": checks,
        "metrics": {
            "daily_rows": int(len(daily)),
            "gjr_persistence": float(fit["persistence"]),
            "seed_probability_max_abs_difference": seed_sensitivity,
            "runtime_seconds": float(time.perf_counter() - started),
        },
        "warnings": backtest_warnings,
        "pass_rule": "all input, stationarity, non-degeneracy, replay, seed-perturbation, backtest and cross-module field checks pass",
        "failure_action": "stop the Q4 gate and fix the input/model contract; do not substitute fallback estimates",
    }
    write_json(payload, "q4_risk_probe.json")
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
    return payload


def run_full(paths: int, backtest_paths: int) -> dict[str, Any]:
    ensure_dirs()
    probe_path = RESULTS_DIR / "q4_risk_probe.json"
    if not probe_path.exists():
        raise FileNotFoundError("Run `python code/problem4/run_q4.py --probe` before the full Q4 implementation.")
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    if probe.get("status") != "PASS":
        raise RuntimeError("Q4 risk probe did not pass; full implementation is blocked.")

    daily = load_daily()
    thresholds = historical_thresholds(daily)
    start_price = float(daily["brent_usd_bbl"].iloc[-1])
    fit = fit_gjr_garch(daily["return_pct"])
    max_step = max(HORIZON_STEPS.values())
    fhs_paths = simulate_fhs(start_price, fit, max_step, paths, RANDOM_SEED)
    gaussian_paths = simulate_gaussian(start_price, daily["return_pct"], max_step, paths, RANDOM_SEED + 1)
    risk = pd.concat(
        [
            summarize_paths(fhs_paths, "FHS_GJR_GARCH", CUTOFF, start_price, thresholds),
            summarize_paths(gaussian_paths, "Gaussian_random_walk", CUTOFF, start_price, thresholds),
        ],
        ignore_index=True,
    )
    detailed_backtest, backtest, backtest_warnings = run_backtest(
        daily, paths=backtest_paths, seed=RANDOM_SEED
    )
    macro, scenario_values = build_macro_stress()
    policy = build_policy_stress()

    save_csv(risk, "q4_price_tail_risk.csv")
    save_csv(detailed_backtest, "q4_risk_backtest_origins.csv")
    save_csv(backtest, "q4_risk_backtest.csv")
    save_csv(macro, "q4_macro_stress.csv")
    save_csv(policy, "q4_policy_stress.csv")
    plot_price_tail_risk(risk)
    plot_macro_policy_stress(macro, policy)

    overall_pinball = (
        backtest.groupby("model", as_index=False)["mean_pinball_loss"].mean().sort_values("mean_pinball_loss")
        if not backtest.empty
        else pd.DataFrame()
    )
    preferred = str(overall_pinball.iloc[0]["model"]) if not overall_pinball.empty else None
    fhs_key = risk.loc[risk["model"].eq("FHS_GJR_GARCH")].copy()
    june_policy = policy.loc[policy["period"].eq("2026-06")].copy()
    extreme = macro.loc[macro["scenario"].eq("extreme_q95")].copy()
    summary = {
        "status": "PASS",
        "execution_status": "PASS",
        "evidence_status": "CONDITIONAL_STRESS_TEST",
        "problem_status": "SELF_DEFINED_PROBLEM_4_RISK_LAYER",
        "random_seed": RANDOM_SEED,
        "cutoff": CUTOFF.strftime("%Y-%m-%d"),
        "main_method": "FHS_GJR_GARCH",
        "baseline": "Gaussian_random_walk",
        "backtest_preferred_model_by_mean_pinball": preferred,
        "allowed_claims": [
            "future Brent upper-tail probabilities are conditional stress forecasts under the fixed cutoff",
            "Q2 structural-shock quantiles map to conditional PPI/CPI/IAV response ranges",
            "Q3 realized policy-off gaps quantify the 2026 temporary-control buffer under its maintained specification",
        ],
        "forbidden_claims": [
            "tail probabilities are certain price outcomes",
            "Q4 macro stress values are deterministic GDP losses",
            "Q2 structural responses and Q3 policy counterfactual gaps can be added as one causal estimate",
            "the stress test proves China is generally optimal or costless",
        ],
        "guardrail": "Price risk, structural-shock macro scenarios and realized policy counterfactuals are reported as three linked but non-additive evidence layers.",
        "gjr_parameters": {
            key: float(fit[key]) for key in ["mu", "omega", "alpha", "gamma", "beta", "persistence"]
        },
        "structural_scenarios": scenario_values,
        "rows": {
            "q4_price_tail_risk.csv": int(len(risk)),
            "q4_risk_backtest_origins.csv": int(len(detailed_backtest)),
            "q4_risk_backtest.csv": int(len(backtest)),
            "q4_macro_stress.csv": int(len(macro)),
            "q4_policy_stress.csv": int(len(policy)),
        },
        "key_price_risk": json_records(fhs_key),
        "key_extreme_macro_rows": json_records(
            extreme.loc[extreme["horizon"].isin([6, 12])].sort_values(["outcome", "horizon"])
        ),
        "key_2026_06_policy_buffer": json_records(june_policy.sort_values("outcome")),
        "backtest_summary": json_records(backtest),
        "warnings": backtest_warnings,
    }
    write_json(summary, "q4_summary.json")
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="run only the pre-registered low-cost risk probe")
    parser.add_argument("--paths", type=int, default=20000, help="Monte Carlo paths for the cutoff forecast")
    parser.add_argument("--backtest-paths", type=int, default=1500, help="paths per rolling backtest origin")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.probe:
        payload = run_probe()
        return 0 if payload["status"] == "PASS" else 1
    run_full(paths=args.paths, backtest_paths=args.backtest_paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
