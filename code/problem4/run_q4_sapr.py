"""Question 4: SAPR-CVaR adaptive fuel-price smoothing rule.

The model treats the official mechanism-implied adjustment as the primary
pricing signal and optimizes only a transparent temporary smoothing layer.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


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
CUTOFF = "2026-06-30"
SCENARIO_LENGTH = 6
BOOTSTRAP_DRAWS = 2000
DEVELOPMENT_END = "2021-12"
HOLDOUT_START = "2022-01"
TEMPORARY_2026_RHO = (1160.0 + 420.0) / (2205.0 + 800.0)
RECOVERY_MONTHS = 6
MAX_GAP_RATIO = 0.35
MAX_TERMINAL_GAP_RATIO = 0.20
MAX_RECOVERY_TERMINAL_GAP_RATIO = 0.05
MAX_MONTHLY_ADJUSTMENT_RATIO = 0.25

OUTCOMES = ["china_ppi_yoy_pct", "china_cpi_yoy_pct", "china_iav_yoy_pct"]
OUTCOME_LABELS = {
    "china_ppi_yoy_pct": "PPI",
    "china_cpi_yoy_pct": "CPI",
    "china_iav_yoy_pct": "IAV",
}
REGIME_ORDER = ["normal", "stress", "extreme"]


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    sample_split: str
    source_start: str
    periods: tuple[str, ...]
    mechanism_adjustment: np.ndarray
    actual_adjustment: np.ndarray
    cumulative_policy_gap: np.ndarray
    regimes: tuple[str, ...]
    is_2026_anchor: bool


@dataclass(frozen=True)
class MacroKernel:
    means: dict[str, np.ndarray]
    covariances: dict[str, np.ndarray]
    labels: dict[str, str]
    valid_outcomes: tuple[str, ...]


def ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)


def save_csv(frame: pd.DataFrame, filename: str) -> Path:
    path = RESULTS_DIR / filename
    frame.to_csv(path, index=False, encoding="utf-8")
    return path


def read_result(filename: str) -> pd.DataFrame:
    path = RESULTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Required result file is missing: {path}")
    return pd.read_csv(path)


def read_processed(filename: str) -> pd.DataFrame:
    path = PROCESSED_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Required processed file is missing: {path}")
    return pd.read_csv(path)


def clean_value(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else round(float(value), 8)
    if pd.isna(value):
        return None
    return value


def stress_regime(value: float, q75: float, q95: float) -> str:
    if not np.isfinite(value) or value <= q75:
        return "normal"
    if value <= q95:
        return "stress"
    return "extreme"


def build_policy_months(threshold_quantiles: tuple[float, float] = (0.75, 0.95)) -> tuple[pd.DataFrame, dict[str, float]]:
    official = read_processed("china_regulated_gasoline_monthly.csv")
    events = read_processed("cn_fuel_adjustment_events.csv")
    macro = read_processed("model_monthly_cn.csv")
    shocks = read_result("q1_monthly_shocks.csv")

    official = official[
        [
            "period",
            "china_regulated_gasoline_cny_per_ton",
            "source_url",
            "coverage_status",
            "measure_type",
        ]
    ].copy()
    events = events.copy()
    events["period"] = pd.to_datetime(events["effective_date"]).dt.to_period("M").astype(str)
    event_monthly = (
        events.groupby("period", as_index=False)
        .agg(
            gasoline_actual_adjustment_cny_t=("actual_adjustment_cny_per_ton", "sum"),
            gasoline_rule_adjustment_cny_t=("rule_implied_adjustment_cny_per_ton", "sum"),
            event_source_count=("source_url", "count"),
        )
        .sort_values("period")
    )
    event_monthly["gasoline_policy_gap_cny_t"] = (
        event_monthly["gasoline_rule_adjustment_cny_t"] - event_monthly["gasoline_actual_adjustment_cny_t"]
    )
    event_monthly["cum_gasoline_policy_gap_cny_t"] = event_monthly["gasoline_policy_gap_cny_t"].cumsum()

    frame = (
        official.merge(event_monthly, on="period", how="left")
        .merge(
            macro[["period", "brent_usd_bbl", "brent_usd_bbl_log_return", "GPR", "GPR_z"]],
            on="period",
            how="left",
        )
        .merge(
            shocks[
                [
                    "period",
                    "supply_shock",
                    "aggregate_demand_shock",
                    "oil_specific_risk_shock",
                    "reduced_form_shock",
                ]
            ],
            on="period",
            how="left",
        )
        .sort_values("period")
    )
    frame = frame.loc[frame["period"].between("2013-03", "2026-06")].copy()
    frame = frame.dropna(subset=["china_regulated_gasoline_cny_per_ton"]).copy()
    if len(frame) < 48:
        raise ValueError("Q4 requires at least 48 months of the reconstructed regulated-gasoline adjustment proxy.")
    for column in [
        "gasoline_actual_adjustment_cny_t",
        "gasoline_rule_adjustment_cny_t",
        "gasoline_policy_gap_cny_t",
        "cum_gasoline_policy_gap_cny_t",
        "event_source_count",
    ]:
        frame[column] = frame[column].fillna(0.0)

    frame["previous_official_price_cny_t"] = frame["china_regulated_gasoline_cny_per_ton"].shift(1)
    fallback_previous = frame["china_regulated_gasoline_cny_per_ton"] - frame["gasoline_actual_adjustment_cny_t"].fillna(0.0)
    frame["previous_official_price_cny_t"] = frame["previous_official_price_cny_t"].fillna(fallback_previous)
    bad_previous = frame["previous_official_price_cny_t"].le(0) | frame["previous_official_price_cny_t"].isna()
    if bool(bad_previous.any()):
        raise ValueError("Q4 cannot compute mechanism adjustment rates because a previous official fuel price is missing or nonpositive.")

    base_price = float(frame.loc[frame["period"].eq("2026-06"), "china_regulated_gasoline_cny_per_ton"].iloc[0])
    frame["mechanism_adjustment_cny_t_original"] = frame["gasoline_rule_adjustment_cny_t"].fillna(0.0)
    frame["actual_adjustment_cny_t_original"] = frame["gasoline_actual_adjustment_cny_t"].fillna(0.0)
    frame["mechanism_adjustment_rate"] = frame["mechanism_adjustment_cny_t_original"] / frame["previous_official_price_cny_t"]
    frame["actual_adjustment_rate"] = frame["actual_adjustment_cny_t_original"] / frame["previous_official_price_cny_t"]
    frame["mechanism_adjustment_cny_t"] = frame["mechanism_adjustment_rate"] * base_price
    frame["actual_adjustment_cny_t"] = frame["actual_adjustment_rate"] * base_price
    frame["cumulative_policy_gap_cny_t_original"] = frame["cum_gasoline_policy_gap_cny_t"].fillna(0.0)
    frame["source_vintage"] = "downloaded_2026-07-31_ex_post"

    development = frame.loc[frame["period"].le(DEVELOPMENT_END)].copy()
    positive = pd.to_numeric(development["mechanism_adjustment_cny_t"], errors="coerce")
    positive = positive.loc[positive.gt(0)].dropna()
    if len(positive) < 12:
        raise ValueError("Q4 cannot define stress thresholds because development positive adjustments are too sparse.")
    q75 = float(positive.quantile(threshold_quantiles[0]))
    q95 = float(positive.quantile(threshold_quantiles[1]))
    frame["stress_regime"] = frame["mechanism_adjustment_cny_t"].map(lambda value: stress_regime(float(value), q75, q95))

    meta = {
        "base_price_2026_06_cny_t": base_price,
        "stress_threshold_75_cny_t": q75,
        "stress_threshold_95_cny_t": q95,
        "threshold_quantile_low": threshold_quantiles[0],
        "threshold_quantile_high": threshold_quantiles[1],
    }
    return frame, meta


def build_scenarios(threshold_quantiles: tuple[float, float] = (0.75, 0.95)) -> tuple[pd.DataFrame, list[Scenario], dict[str, float]]:
    frame, meta = build_policy_months(threshold_quantiles)
    scenario_rows: list[dict[str, Any]] = []
    scenarios: list[Scenario] = []
    for start in range(0, len(frame) - SCENARIO_LENGTH + 1):
        window = frame.iloc[start : start + SCENARIO_LENGTH].copy()
        source_start = str(window["period"].iloc[0])
        source_end = str(window["period"].iloc[-1])
        if source_end <= DEVELOPMENT_END:
            split = "development"
        elif source_start >= HOLDOUT_START and source_end <= "2026-06":
            split = "holdout"
        else:
            continue
        scenario_id = f"{split.upper()}_{source_start}"
        is_2026_anchor = source_start == "2026-01" and source_end == "2026-06"
        scenario = Scenario(
            scenario_id=scenario_id,
            sample_split=split,
            source_start=source_start,
            periods=tuple(window["period"].astype(str).tolist()),
            mechanism_adjustment=window["mechanism_adjustment_cny_t"].astype(float).to_numpy(),
            actual_adjustment=window["actual_adjustment_cny_t"].astype(float).to_numpy(),
            cumulative_policy_gap=window["cumulative_policy_gap_cny_t_original"].astype(float).to_numpy(),
            regimes=tuple(window["stress_regime"].astype(str).tolist()),
            is_2026_anchor=is_2026_anchor,
        )
        scenarios.append(scenario)
        for month_index, (_, row) in enumerate(window.iterrows()):
            scenario_rows.append(
                {
                    "scenario_id": scenario_id,
                    "sample_split": split,
                    "month_index": month_index,
                    "period": row["period"],
                    "source_start": source_start,
                    "source_end": source_end,
                    "brent_return": row["brent_usd_bbl_log_return"],
                    "brent_level": row["brent_usd_bbl"],
                    "mechanism_adjustment_rate": row["mechanism_adjustment_rate"],
                    "mechanism_adjustment_cny_t": row["mechanism_adjustment_cny_t"],
                    "mechanism_adjustment_cny_t_original": row["mechanism_adjustment_cny_t_original"],
                    "actual_adjustment_cny_t_original": row["actual_adjustment_cny_t_original"],
                    "cumulative_policy_gap_cny_t_original": row["cumulative_policy_gap_cny_t_original"],
                    "stress_regime": row["stress_regime"],
                    "is_2026_anchor": is_2026_anchor,
                    "GPR": row["GPR"],
                    "GPR_z": row["GPR_z"],
                    "supply_shock": row["supply_shock"],
                    "aggregate_demand_shock": row["aggregate_demand_shock"],
                    "oil_specific_risk_shock": row["oil_specific_risk_shock"],
                    "reduced_form_shock": row["reduced_form_shock"],
                    "source_vintage": row["source_vintage"],
                }
            )
    scenario_table = pd.DataFrame(scenario_rows)
    return scenario_table, scenarios, meta


def validated_covariance(matrix: np.ndarray, outcome: str) -> np.ndarray:
    if not np.isfinite(matrix).all():
        raise ValueError(f"Q3 covariance for {outcome} contains non-finite values.")
    if not np.allclose(matrix, matrix.T, atol=1e-10, rtol=1e-10):
        raise ValueError(f"Q3 covariance for {outcome} is not symmetric.")
    eigvals = np.linalg.eigvalsh(matrix)
    if float(eigvals.min()) < -1e-10:
        raise ValueError(f"Q3 covariance for {outcome} is not positive semidefinite.")
    return (matrix + matrix.T) / 2.0


def load_macro_kernel() -> MacroKernel:
    kernel = read_result("q3_policy_macro_kernel.csv")
    covariance = read_result("q3_policy_macro_covariance.csv")
    required_kernel = {"outcome", "outcome_label", "n", "phi_outcome_lag1"} | {f"beta_fuel_lag{lag}" for lag in range(7)}
    required_cov = {"outcome", "row_term", "column_term", "covariance"}
    if not required_kernel.issubset(kernel.columns) or not required_cov.issubset(covariance.columns):
        raise ValueError("Q3 macro kernel or covariance file lacks required columns for Q4.")
    means: dict[str, np.ndarray] = {}
    covariances: dict[str, np.ndarray] = {}
    labels: dict[str, str] = {}
    for outcome in OUTCOMES:
        rows = kernel.loc[kernel["outcome"].eq(outcome)]
        if len(rows) != 1:
            raise ValueError(f"Q4 requires exactly one macro-kernel row for {outcome}.")
        row = rows.iloc[0]
        terms = [f"fuel_log_return_lag{lag}" for lag in range(7)] + [f"{outcome}_lag1"]
        means[outcome] = np.array([float(row[f"beta_fuel_lag{lag}"]) for lag in range(7)] + [float(row["phi_outcome_lag1"])])
        if not np.isfinite(means[outcome]).all():
            raise ValueError(f"Q3 macro kernel for {outcome} contains non-finite coefficients.")
        labels[outcome] = str(row["outcome_label"])
        cov_block = covariance.loc[covariance["outcome"].eq(outcome)].copy()
        required_pairs = {(row_term, col_term) for row_term in terms for col_term in terms}
        observed_pairs = set(zip(cov_block["row_term"].astype(str), cov_block["column_term"].astype(str)))
        missing_pairs = required_pairs - observed_pairs
        if missing_pairs:
            raise ValueError(f"Q3 covariance for {outcome} is missing {len(missing_pairs)} required term pairs.")
        matrix = np.zeros((len(terms), len(terms)), dtype=float)
        for i, row_term in enumerate(terms):
            for j, col_term in enumerate(terms):
                hit = cov_block.loc[cov_block["row_term"].eq(row_term) & cov_block["column_term"].eq(col_term), "covariance"]
                if len(hit) != 1:
                    raise ValueError(f"Q3 covariance for {outcome} has duplicate or missing value for {row_term}, {col_term}.")
                matrix[i, j] = float(hit.iloc[0])
        covariances[outcome] = validated_covariance(matrix, outcome)
    valid = tuple(outcome for outcome in OUTCOMES if outcome in means and outcome in covariances)
    if set(valid) != set(OUTCOMES):
        raise ValueError("Q4 requires PPI, CPI and IAV macro kernels from Q3.")
    return MacroKernel(means=means, covariances=covariances, labels=labels, valid_outcomes=valid)


def draw_parameter_sets(
    kernel: MacroKernel,
    rng: np.random.Generator,
    target_draws: int = BOOTSTRAP_DRAWS,
    minimum_valid_rate: float = 0.95,
) -> tuple[list[dict[str, np.ndarray]], float, int]:
    joint_path = RESULTS_DIR / "q3_policy_macro_bootstrap_draws.csv"
    if joint_path.exists():
        joint = pd.read_csv(joint_path)
        required = {"draw", "outcome", "phi_outcome_lag1"} | {f"beta_fuel_lag{lag}" for lag in range(7)}
        if not required.issubset(joint.columns):
            raise ValueError("Q3 joint macro bootstrap file lacks required Q4 kernel columns.")
        available_draws = sorted(pd.to_numeric(joint["draw"], errors="coerce").dropna().astype(int).unique())
        if len(available_draws) < target_draws:
            raise ValueError(f"Q4 requires {target_draws} joint Q3 draws but found {len(available_draws)}.")
        draws: list[dict[str, np.ndarray]] = []
        for draw_id in available_draws[:target_draws]:
            block = joint.loc[pd.to_numeric(joint["draw"], errors="coerce").eq(draw_id)]
            draw: dict[str, np.ndarray] = {}
            for outcome in kernel.valid_outcomes:
                row = block.loc[block["outcome"].eq(outcome)]
                if len(row) != 1:
                    raise ValueError(f"Q3 joint draw {draw_id} lacks exactly one row for {outcome}.")
                values = np.array(
                    [float(row.iloc[0][f"beta_fuel_lag{lag}"]) for lag in range(7)]
                    + [float(row.iloc[0]["phi_outcome_lag1"])],
                    dtype=float,
                )
                if not np.isfinite(values).all() or abs(float(values[-1])) >= 1.0:
                    raise ValueError(f"Q3 joint draw {draw_id} is invalid for {outcome}.")
                draw[outcome] = values
            draws.append(draw)
        return draws, 1.0, len(draws)
    draws: list[dict[str, np.ndarray]] = []
    max_attempts = int(np.floor(target_draws / minimum_valid_rate))
    attempts_used = 0
    while len(draws) < target_draws and attempts_used < max_attempts:
        attempts_used += 1
        draw: dict[str, np.ndarray] = {}
        valid = True
        for outcome in kernel.valid_outcomes:
            mean = kernel.means[outcome]
            covariance = kernel.covariances[outcome]
            phi = float(mean[-1])
            if abs(phi) >= 1.0:
                raise ValueError(f"Q4 macro kernel for {outcome} has an unstable point-estimate lag coefficient.")
            transformed_mean = mean.copy()
            transformed_mean[-1] = np.arctanh(phi)
            jacobian = np.eye(len(mean), dtype=float)
            jacobian[-1, -1] = 1.0 / (1.0 - phi**2)
            transformed_covariance = validated_covariance(jacobian @ covariance @ jacobian.T, f"{outcome}_stationary_phi")
            transformed_sample = rng.multivariate_normal(transformed_mean, transformed_covariance, method="svd")
            sample = transformed_sample.copy()
            sample[-1] = np.tanh(transformed_sample[-1])
            if not np.isfinite(sample).all() or abs(float(sample[-1])) >= 1.0:
                valid = False
                break
            draw[outcome] = sample
        if valid:
            draws.append(draw)
    valid_rate = len(draws) / float(attempts_used) if attempts_used else 0.0
    return draws, valid_rate, attempts_used


def point_coefficients(kernel: MacroKernel) -> dict[str, np.ndarray]:
    return {outcome: values.copy() for outcome, values in kernel.means.items()}


def historical_macro_stds(weights: dict[str, float]) -> dict[str, float]:
    macro = read_processed("model_monthly_cn.csv")
    frame = macro.loc[macro["period"].between("2013-03", DEVELOPMENT_END)].copy()
    stds: dict[str, float] = {}
    for outcome in OUTCOMES:
        std = float(pd.to_numeric(frame[outcome], errors="coerce").std(skipna=True))
        stds[outcome] = std if np.isfinite(std) and std > 1e-9 else 1.0
    return stds


def enumerate_rules() -> list[dict[str, float]]:
    values = [round(i * 0.05, 2) for i in range(21)]
    rules: list[dict[str, float]] = []
    for rho_normal in values:
        for rho_stress in values:
            for rho_extreme in values:
                if rho_normal >= rho_stress >= rho_extreme:
                    rules.append(
                        {
                            "rho_normal": rho_normal,
                            "rho_stress": rho_stress,
                            "rho_extreme": rho_extreme,
                        }
                    )
    return rules


def rho_for_regime(rule: dict[str, float], regime: str) -> float:
    if regime == "extreme":
        return float(rule["rho_extreme"])
    if regime == "stress":
        return float(rule["rho_stress"])
    return float(rule["rho_normal"])


def simulate_rule_path(scenario: Scenario, rule: dict[str, float], base_price: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    price = np.empty(SCENARIO_LENGTH, dtype=float)
    actual_adjustment = np.empty(SCENARIO_LENGTH, dtype=float)
    deferred_gap = np.empty(SCENARIO_LENGTH, dtype=float)
    fuel_return = np.empty(SCENARIO_LENGTH, dtype=float)
    previous_price = base_price
    gap = 0.0
    for t in range(SCENARIO_LENGTH):
        desired = float(scenario.mechanism_adjustment[t]) + gap
        if desired > 0:
            adjustment = rho_for_regime(rule, scenario.regimes[t]) * desired
            gap = desired - adjustment
            gap_cap = MAX_TERMINAL_GAP_RATIO * base_price
            if gap > gap_cap:
                catch_up = gap - gap_cap
                adjustment += catch_up
                gap = gap_cap
        else:
            adjustment = desired
            gap = 0.0
        current_price = max(previous_price + adjustment, 1.0)
        actual_adjustment[t] = adjustment
        deferred_gap[t] = gap
        price[t] = current_price
        fuel_return[t] = np.log(current_price / previous_price)
        previous_price = current_price
    return price, actual_adjustment, deferred_gap, fuel_return


def simulate_actual_2026_path(scenario: Scenario, base_price: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    price = np.empty(SCENARIO_LENGTH, dtype=float)
    actual_adjustment = np.empty(SCENARIO_LENGTH, dtype=float)
    deferred_gap = np.empty(SCENARIO_LENGTH, dtype=float)
    fuel_return = np.empty(SCENARIO_LENGTH, dtype=float)
    previous_price = base_price
    for t in range(SCENARIO_LENGTH):
        adjustment = float(scenario.actual_adjustment[t])
        current_price = max(previous_price + adjustment, 1.0)
        actual_adjustment[t] = adjustment
        deferred_gap[t] = float(scenario.cumulative_policy_gap[t])
        price[t] = current_price
        fuel_return[t] = np.log(current_price / previous_price)
        previous_price = current_price
    return price, actual_adjustment, deferred_gap, fuel_return


def recovery_terminal_gap(terminal_gap: float, rule: dict[str, float]) -> float:
    gap = max(float(terminal_gap), 0.0)
    rho = float(rule["rho_normal"])
    for _ in range(RECOVERY_MONTHS):
        gap = (1.0 - rho) * gap
    return gap


def macro_path_from_returns(fuel_return: np.ndarray, coefficients: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    paths = {outcome: np.zeros(SCENARIO_LENGTH, dtype=float) for outcome in OUTCOMES}
    lag_buffer = [0.0] * 7
    previous_y = {outcome: 0.0 for outcome in OUTCOMES}
    for t in range(SCENARIO_LENGTH):
        lag_buffer = [float(fuel_return[t])] + lag_buffer[:6]
        for outcome in OUTCOMES:
            params = coefficients[outcome]
            y = float(np.dot(params[:7], np.array(lag_buffer)) + params[7] * previous_y[outcome])
            paths[outcome][t] = y
            previous_y[outcome] = y
    return paths


def objective_from_scenario_outputs(
    scenario_losses: list[float],
    gap_burdens: list[float],
    fuel_returns: list[float],
) -> dict[str, float]:
    losses = np.asarray(scenario_losses, dtype=float)
    gaps = np.asarray(gap_burdens, dtype=float)
    returns = np.asarray(fuel_returns, dtype=float)
    if len(losses) == 0:
        raise ValueError("Q4 objective cannot be computed from an empty scenario set.")
    if not np.isfinite(losses).all() or not np.isfinite(gaps).all() or not np.isfinite(returns).all():
        raise ValueError("Q4 objective inputs contain non-finite values.")
    tail_count = max(1, int(np.ceil(0.05 * len(losses))))
    tail = np.sort(losses)[-tail_count:]
    return {
        "J1_macro_loss": float(np.mean(losses)),
        "J2_cvar95_macro_loss": float(np.mean(tail)),
        "J3_avg_gap_month_burden": float(np.mean(gaps)),
        "J4_adjustment_volatility": float(np.std(returns, ddof=0)) if len(returns) else 0.0,
    }


def evaluate_strategy(
    scenarios: list[Scenario],
    coefficients: dict[str, np.ndarray],
    rule: dict[str, float] | None,
    strategy_name: str,
    split: str,
    base_price: float,
    stds: dict[str, float],
    weights: dict[str, float],
    scenario_indices: np.ndarray | None = None,
) -> dict[str, float]:
    candidates = [scenario for scenario in scenarios if scenario.sample_split == split]
    if split == "war_2026":
        candidates = [scenario for scenario in scenarios if scenario.is_2026_anchor]
    if not candidates:
        raise ValueError(f"Q4 strategy evaluation has no candidate scenarios for split={split}.")
    if scenario_indices is not None and len(candidates):
        candidates = [candidates[int(index) % len(candidates)] for index in scenario_indices]
    losses: list[float] = []
    gap_burdens: list[float] = []
    returns_all: list[float] = []
    max_gap_ratios: list[float] = []
    terminal_gap_ratios: list[float] = []
    recovery_gap_ratios: list[float] = []
    max_adjustment_ratios: list[float] = []
    for scenario in candidates:
        if strategy_name == "actual_2026_event_path":
            price, adjustment, gap, fuel_return = simulate_actual_2026_path(scenario, base_price)
        else:
            if rule is None:
                raise ValueError("A SAPR rule is required for simulated strategies.")
            price, adjustment, gap, fuel_return = simulate_rule_path(scenario, rule, base_price)
        macro_paths = macro_path_from_returns(fuel_return, coefficients)
        month_loss = np.zeros(SCENARIO_LENGTH, dtype=float)
        month_loss += weights["china_ppi_yoy_pct"] * np.maximum(macro_paths["china_ppi_yoy_pct"], 0.0) / stds["china_ppi_yoy_pct"]
        month_loss += weights["china_cpi_yoy_pct"] * np.maximum(macro_paths["china_cpi_yoy_pct"], 0.0) / stds["china_cpi_yoy_pct"]
        month_loss += weights["china_iav_yoy_pct"] * np.maximum(-macro_paths["china_iav_yoy_pct"], 0.0) / stds["china_iav_yoy_pct"]
        losses.append(float(np.mean(month_loss)))
        gap_burdens.append(float(np.mean(np.maximum(gap, 0.0)) / base_price))
        max_gap_ratios.append(float(np.max(np.maximum(gap, 0.0)) / base_price))
        terminal_gap_ratios.append(float(max(float(gap[-1]), 0.0) / base_price))
        recovery_gap_ratios.append(
            float(recovery_terminal_gap(float(gap[-1]), rule) / base_price) if rule is not None else float(max(float(gap[-1]), 0.0) / base_price)
        )
        max_adjustment_ratios.append(float(np.max(np.abs(adjustment)) / base_price))
        returns_all.extend(fuel_return.tolist())
    result = objective_from_scenario_outputs(losses, gap_burdens, returns_all)
    result.update(
        {
            "scenario_count": len(candidates),
            "max_gap_ratio": float(max(max_gap_ratios)),
            "max_terminal_gap_ratio": float(max(terminal_gap_ratios)),
            "max_recovery_terminal_gap_ratio": float(max(recovery_gap_ratios)),
            "max_monthly_adjustment_ratio": float(max(max_adjustment_ratios)),
        }
    )
    return result


def scenario_candidates(scenarios: list[Scenario], split: str) -> list[Scenario]:
    candidates = [scenario for scenario in scenarios if scenario.sample_split == split]
    if split == "war_2026":
        candidates = [scenario for scenario in scenarios if scenario.is_2026_anchor]
    if not candidates:
        raise ValueError(f"Q4 has no scenario candidates for split={split}.")
    return candidates


def strategy_path_arrays(
    scenarios: list[Scenario],
    rule: dict[str, float] | None,
    strategy_name: str,
    split: str,
    base_price: float,
) -> dict[str, np.ndarray]:
    candidates = scenario_candidates(scenarios, split)
    fuel_returns = np.empty((len(candidates), SCENARIO_LENGTH), dtype=float)
    gap_burdens = np.empty(len(candidates), dtype=float)
    max_gap_ratios = np.empty(len(candidates), dtype=float)
    terminal_gap_ratios = np.empty(len(candidates), dtype=float)
    recovery_gap_ratios = np.empty(len(candidates), dtype=float)
    max_adjustment_ratios = np.empty(len(candidates), dtype=float)
    for index, scenario in enumerate(candidates):
        if strategy_name == "actual_2026_event_path":
            _, adjustment, gap, fuel_return = simulate_actual_2026_path(scenario, base_price)
        else:
            if rule is None:
                raise ValueError("A SAPR rule is required for simulated strategies.")
            _, adjustment, gap, fuel_return = simulate_rule_path(scenario, rule, base_price)
        fuel_returns[index, :] = fuel_return
        gap_burdens[index] = float(np.mean(np.maximum(gap, 0.0)) / base_price)
        max_gap_ratios[index] = float(np.max(np.maximum(gap, 0.0)) / base_price)
        terminal_gap_ratios[index] = float(max(float(gap[-1]), 0.0) / base_price)
        recovery_gap_ratios[index] = (
            float(recovery_terminal_gap(float(gap[-1]), rule) / base_price)
            if rule is not None
            else terminal_gap_ratios[index]
        )
        max_adjustment_ratios[index] = float(np.max(np.abs(adjustment)) / base_price)
    return {
        "fuel_returns": fuel_returns,
        "gap_burdens": gap_burdens,
        "max_gap_ratios": max_gap_ratios,
        "terminal_gap_ratios": terminal_gap_ratios,
        "recovery_gap_ratios": recovery_gap_ratios,
        "max_adjustment_ratios": max_adjustment_ratios,
    }


def macro_losses_from_returns(
    fuel_returns: np.ndarray,
    coefficients: dict[str, np.ndarray],
    stds: dict[str, float],
    weights: dict[str, float],
) -> np.ndarray:
    if fuel_returns.ndim != 2 or fuel_returns.shape[1] != SCENARIO_LENGTH:
        raise ValueError("Q4 macro loss calculation requires a scenario-by-month fuel-return matrix.")
    month_loss = np.zeros_like(fuel_returns, dtype=float)
    for outcome in OUTCOMES:
        params = coefficients[outcome]
        y = np.zeros_like(fuel_returns, dtype=float)
        for t in range(SCENARIO_LENGTH):
            signal = np.zeros(fuel_returns.shape[0], dtype=float)
            for lag in range(7):
                if t - lag >= 0:
                    signal += float(params[lag]) * fuel_returns[:, t - lag]
            if t > 0:
                signal += float(params[7]) * y[:, t - 1]
            y[:, t] = signal
        if outcome == "china_iav_yoy_pct":
            contribution = np.maximum(-y, 0.0)
        else:
            contribution = np.maximum(y, 0.0)
        month_loss += weights[outcome] * contribution / stds[outcome]
    return month_loss.mean(axis=1)


def objectives_from_arrays(
    scenario_losses: np.ndarray,
    gap_burdens: np.ndarray,
    fuel_returns: np.ndarray,
    scenario_indices: np.ndarray | None = None,
) -> dict[str, float]:
    if scenario_indices is not None:
        indices = np.asarray(scenario_indices, dtype=int) % len(scenario_losses)
        losses = scenario_losses[indices]
        gaps = gap_burdens[indices]
        returns = fuel_returns[indices, :].reshape(-1)
    else:
        losses = scenario_losses
        gaps = gap_burdens
        returns = fuel_returns.reshape(-1)
    return objective_from_scenario_outputs(losses.tolist(), gaps.tolist(), returns.tolist())


def dominates(a: np.ndarray, b: np.ndarray) -> bool:
    return bool(np.all(a <= b + 1e-12) and np.any(a < b - 1e-12))


def pareto_mask(objectives: np.ndarray) -> np.ndarray:
    n = objectives.shape[0]
    mask = np.ones(n, dtype=bool)
    for i in range(n):
        if not mask[i]:
            continue
        dominated_by_i = np.all(objectives[i] <= objectives + 1e-12, axis=1) & np.any(objectives[i] < objectives - 1e-12, axis=1)
        dominated_by_i[i] = False
        mask[dominated_by_i] = False
        if np.any(np.all(objectives[mask] <= objectives[i] + 1e-12, axis=1) & np.any(objectives[mask] < objectives[i] - 1e-12, axis=1)):
            mask[i] = False
    return mask


def epsilon_pareto_mask(objectives: np.ndarray, epsilon_fraction: float = 0.01) -> np.ndarray:
    """Treat sub-material objective differences as ties to avoid a mechanically wide front."""
    spans = np.ptp(objectives, axis=0)
    epsilon = np.maximum(spans * epsilon_fraction, 1e-12)
    n = objectives.shape[0]
    mask = np.ones(n, dtype=bool)
    for i in range(n):
        candidate = objectives[i]
        for j in range(n):
            if i == j:
                continue
            challenger = objectives[j]
            if np.all(challenger <= candidate + epsilon) and np.any(challenger < candidate - epsilon):
                mask[i] = False
                break
    return mask


def choose_knee(grid: pd.DataFrame) -> pd.DataFrame:
    objective_cols = ["J1_macro_loss", "J2_cvar95_macro_loss", "J3_avg_gap_month_burden", "J4_adjustment_volatility"]
    grid = grid.copy()
    grid["is_feasible"] = (
        grid["max_gap_ratio"].le(MAX_GAP_RATIO)
        & grid["max_terminal_gap_ratio"].le(MAX_TERMINAL_GAP_RATIO)
        & grid["max_recovery_terminal_gap_ratio"].le(MAX_RECOVERY_TERMINAL_GAP_RATIO)
        & grid["max_monthly_adjustment_ratio"].le(MAX_MONTHLY_ADJUSTMENT_RATIO)
    )
    grid["is_pareto"] = False
    grid["is_knee"] = False
    feasible = grid.loc[grid["is_feasible"]].copy()
    if feasible.empty:
        raise ValueError("Q4 has no feasible rule under the preregistered gap, recovery and adjustment constraints.")
    feasible_values = feasible[objective_cols].astype(float).to_numpy()
    exact_mask = pareto_mask(feasible_values)
    grid["is_pareto_exact"] = False
    grid.loc[feasible.index, "is_pareto_exact"] = exact_mask
    mask = epsilon_pareto_mask(feasible_values, epsilon_fraction=0.01)
    grid.loc[feasible.index, "is_pareto"] = mask
    pareto = grid.loc[grid["is_pareto"]].copy()
    if pareto.empty:
        raise ValueError("Q4 Pareto set is empty.")
    mins = pareto[objective_cols].min()
    maxs = pareto[objective_cols].max()
    denom = (maxs - mins).replace(0.0, 1.0)
    normalized = (pareto[objective_cols] - mins) / denom
    pareto["knee_score"] = np.sqrt((normalized**2).sum(axis=1))
    pareto = pareto.sort_values(["knee_score", "J3_avg_gap_month_burden", "rho_normal"], ascending=[True, True, False])
    knee_rule_id = pareto.iloc[0]["rule_id"]
    grid.loc[grid["rule_id"].eq(knee_rule_id), "is_knee"] = True
    grid["knee_score"] = np.nan
    grid.loc[pareto.index, "knee_score"] = pareto["knee_score"]
    return grid


def run_grid_search(
    scenarios: list[Scenario],
    coefficients: dict[str, np.ndarray],
    base_price: float,
    stds: dict[str, float],
    weights: dict[str, float],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for idx, rule in enumerate(enumerate_rules(), start=1):
        objectives = evaluate_strategy(scenarios, coefficients, rule, "SAPR_candidate", "development", base_price, stds, weights)
        rows.append(
            {
                "rule_id": f"R{idx:04d}",
                **rule,
                **objectives,
                "sample_split": "development",
            }
        )
    grid = choose_knee(pd.DataFrame(rows))
    if int(grid["is_knee"].sum()) != 1:
        raise ValueError("Q4 knee selection is not unique.")
    return grid


def strategy_catalog(knee_rule: dict[str, float]) -> dict[str, dict[str, Any]]:
    return {
        "full_mechanism": {"rule": {"rho_normal": 1.0, "rho_stress": 1.0, "rho_extreme": 1.0}, "type": "rule"},
        "uniform_75_smoothing": {"rule": {"rho_normal": 0.75, "rho_stress": 0.75, "rho_extreme": 0.75}, "type": "rule"},
        "temporary_2026_approx": {"rule": {"rho_normal": 1.0, "rho_stress": 1.0, "rho_extreme": round(TEMPORARY_2026_RHO, 6)}, "type": "rule"},
        "SAPR_CVaR_knee": {"rule": knee_rule, "type": "rule"},
        "actual_2026_event_path": {"rule": None, "type": "actual_2026"},
    }


def block_bootstrap_indices(n: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    if n <= 0:
        raise ValueError("Q4 block bootstrap requires a positive scenario count.")
    indices: list[int] = []
    while len(indices) < n:
        start = int(rng.integers(0, n))
        for offset in range(block_length):
            indices.append((start + offset) % n)
            if len(indices) >= n:
                break
    return np.array(indices[:n], dtype=int)


def compare_strategies(
    scenarios: list[Scenario],
    kernel: MacroKernel,
    parameter_draws: list[dict[str, np.ndarray]],
    knee_rule: dict[str, float],
    base_price: float,
    stds: dict[str, float],
    weights: dict[str, float],
    rng: np.random.Generator,
    block_length: int = 6,
) -> tuple[pd.DataFrame, float, bool]:
    point = point_coefficients(kernel)
    strategies = strategy_catalog(knee_rule)
    rows: list[dict[str, Any]] = []
    interval_store: dict[tuple[str, str], list[dict[str, float]]] = {}
    splits = ["development", "holdout", "war_2026"]
    for split in splits:
        for strategy_name, meta in strategies.items():
            if strategy_name == "actual_2026_event_path" and split != "war_2026":
                continue
            arrays = strategy_path_arrays(scenarios, meta["rule"], strategy_name, split, base_price)
            point_losses = macro_losses_from_returns(arrays["fuel_returns"], point, stds, weights)
            objectives = objectives_from_arrays(point_losses, arrays["gap_burdens"], arrays["fuel_returns"])
            objectives["scenario_count"] = int(len(point_losses))
            objectives.update(
                {
                    "max_gap_ratio": float(np.max(arrays["max_gap_ratios"])),
                    "max_terminal_gap_ratio": float(np.max(arrays["terminal_gap_ratios"])),
                    "max_recovery_terminal_gap_ratio": float(np.max(arrays["recovery_gap_ratios"])),
                    "max_monthly_adjustment_ratio": float(np.max(arrays["max_adjustment_ratios"])),
                }
            )
            row = {
                "sample_split": split,
                "strategy": strategy_name,
                "rho_normal": clean_value(meta["rule"]["rho_normal"]) if meta["rule"] else None,
                "rho_stress": clean_value(meta["rule"]["rho_stress"]) if meta["rule"] else None,
                "rho_extreme": clean_value(meta["rule"]["rho_extreme"]) if meta["rule"] else None,
                **objectives,
            }
            rows.append(row)
            interval_store[(split, strategy_name)] = []
            n = int(len(point_losses))
            for draw in parameter_draws:
                sampled = block_bootstrap_indices(n, block_length, rng)
                draw_losses = macro_losses_from_returns(arrays["fuel_returns"], draw, stds, weights)
                interval_store[(split, strategy_name)].append(
                    objectives_from_arrays(draw_losses, arrays["gap_burdens"], arrays["fuel_returns"], sampled)
                )
    comparison = pd.DataFrame(rows)
    full_by_split = comparison.loc[comparison["strategy"].eq("full_mechanism")].set_index("sample_split")
    for idx, row in comparison.iterrows():
        split = row["sample_split"]
        if split in full_by_split.index:
            full = full_by_split.loc[split]
            for col in ["J1_macro_loss", "J2_cvar95_macro_loss"]:
                denom = abs(float(full[col])) if abs(float(full[col])) > 1e-12 else np.nan
                comparison.loc[idx, f"{col}_improvement_vs_full_pct"] = (
                    100.0 * (float(full[col]) - float(row[col])) / denom if np.isfinite(denom) else np.nan
                )
    for idx, row in comparison.iterrows():
        draws = interval_store.get((row["sample_split"], row["strategy"]), [])
        if not draws:
            continue
        for col in ["J1_macro_loss", "J2_cvar95_macro_loss"]:
            values = np.array([float(draw[col]) for draw in draws], dtype=float)
            comparison.loc[idx, f"{col}_lower_95"] = float(np.quantile(values, 0.025))
            comparison.loc[idx, f"{col}_upper_95"] = float(np.quantile(values, 0.975))

    probability, point_non_dominated = holdout_validation_probability(
        scenarios,
        parameter_draws,
        knee_rule,
        base_price,
        stds,
        weights,
        rng,
        block_length=block_length,
        point_comparison=comparison,
    )
    return comparison, probability, point_non_dominated


def holdout_validation_probability(
    scenarios: list[Scenario],
    parameter_draws: list[dict[str, np.ndarray]],
    knee_rule: dict[str, float],
    base_price: float,
    stds: dict[str, float],
    weights: dict[str, float],
    rng: np.random.Generator,
    block_length: int,
    point_comparison: pd.DataFrame | None = None,
    point_values: dict[str, np.ndarray] | None = None,
    save_outputs: bool = True,
) -> tuple[float, bool]:
    objective_cols = ["J1_macro_loss", "J2_cvar95_macro_loss", "J3_avg_gap_month_burden", "J4_adjustment_volatility"]
    strategies = strategy_catalog(knee_rule)
    holdout_strategies = [name for name in strategies if name != "actual_2026_event_path"]
    if point_comparison is None:
        if point_values is None:
            raise ValueError("Q4 holdout validation requires either point comparison rows or explicit point coefficients.")
        point_rows: list[dict[str, Any]] = []
        for strategy_name in holdout_strategies:
            meta = strategies[strategy_name]
            arrays = strategy_path_arrays(scenarios, meta["rule"], strategy_name, "holdout", base_price)
            point_losses = macro_losses_from_returns(arrays["fuel_returns"], point_values, stds, weights)
            objectives = objectives_from_arrays(point_losses, arrays["gap_burdens"], arrays["fuel_returns"])
            objectives["scenario_count"] = int(len(point_losses))
            point_rows.append({"sample_split": "holdout", "strategy": strategy_name, **objectives})
        point_holdout = pd.DataFrame(point_rows)
    else:
        point_holdout = point_comparison.loc[
            point_comparison["sample_split"].eq("holdout") & point_comparison["strategy"].isin(holdout_strategies)
        ].copy()
    if set(point_holdout["strategy"]) != set(holdout_strategies):
        raise ValueError("Q4 holdout validation is missing one or more preregistered strategies.")
    point_knee = point_holdout.loc[point_holdout["strategy"].eq("SAPR_CVaR_knee")]
    if len(point_knee) != 1:
        raise ValueError("Q4 holdout validation requires exactly one SAPR knee row.")
    knee_vec = point_knee[objective_cols].iloc[0].astype(float).to_numpy()
    point_non_dominated = True
    for _, row in point_holdout.loc[point_holdout["strategy"].ne("SAPR_CVaR_knee")].iterrows():
        other_vec = row[objective_cols].astype(float).to_numpy()
        if dominates(other_vec, knee_vec):
            point_non_dominated = False
            break
    holdout_n = len([scenario for scenario in scenarios if scenario.sample_split == "holdout"])
    arrays_by_strategy = {
        strategy_name: strategy_path_arrays(scenarios, strategies[strategy_name]["rule"], strategy_name, "holdout", base_price)
        for strategy_name in holdout_strategies
    }
    point_matrix = point_holdout.set_index("strategy").loc[holdout_strategies, objective_cols].astype(float).to_numpy()
    point_mins = point_matrix.min(axis=0)
    point_denom = np.maximum(point_matrix.max(axis=0) - point_mins, 1e-12)
    point_distances = np.sqrt((((point_matrix - point_mins) / point_denom) ** 2).sum(axis=1))
    point_knee_distance = float(point_distances[holdout_strategies.index("SAPR_CVaR_knee")])
    point_oracle_distance = float(point_distances.min())
    draw_rows: list[dict[str, Any]] = []
    valid_flags: list[bool] = []
    for draw_id, draw in enumerate(parameter_draws):
        sampled = block_bootstrap_indices(holdout_n, block_length, rng)
        vectors: dict[str, np.ndarray] = {}
        for strategy_name in holdout_strategies:
            arrays = arrays_by_strategy[strategy_name]
            draw_losses = macro_losses_from_returns(arrays["fuel_returns"], draw, stds, weights)
            obj = objectives_from_arrays(draw_losses, arrays["gap_burdens"], arrays["fuel_returns"], sampled)
            vectors[strategy_name] = np.array(
                [obj["J1_macro_loss"], obj["J2_cvar95_macro_loss"], obj["J3_avg_gap_month_burden"], obj["J4_adjustment_volatility"]],
                dtype=float,
            )
        sampled_knee_vec = vectors["SAPR_CVaR_knee"]
        non_dominated = not any(dominates(vec, sampled_knee_vec) for name, vec in vectors.items() if name != "SAPR_CVaR_knee")
        valid_flags.append(non_dominated)
        matrix = np.vstack([vectors[name] for name in holdout_strategies])
        mins = matrix.min(axis=0)
        denom = np.maximum(matrix.max(axis=0) - mins, 1e-12)
        distances = np.sqrt((((matrix - mins) / denom) ** 2).sum(axis=1))
        knee_distance = float(distances[holdout_strategies.index("SAPR_CVaR_knee")])
        oracle_distance = float(distances.min())
        for baseline in [name for name in holdout_strategies if name != "SAPR_CVaR_knee"]:
            delta = sampled_knee_vec - vectors[baseline]
            draw_rows.append(
                {
                    "draw": draw_id,
                    "block_length": block_length,
                    "baseline": baseline,
                    **{f"delta_{column}": float(delta[idx]) for idx, column in enumerate(objective_cols)},
                    "knee_distance_to_ideal": knee_distance,
                    "oracle_distance_to_ideal": oracle_distance,
                    "knee_regret_vs_oracle": knee_distance - oracle_distance,
                    "knee_non_dominated": non_dominated,
                }
            )
    if len(valid_flags) != len(parameter_draws):
        raise ValueError("Q4 holdout validation did not evaluate every valid parameter draw.")
    validation = pd.DataFrame(draw_rows)
    if save_outputs:
        save_csv(validation, "q4_sapr_holdout_validation.csv")
    paired_summary: list[dict[str, Any]] = []
    for baseline, group in validation.groupby("baseline"):
        for column in objective_cols:
            values = group[f"delta_{column}"].to_numpy(dtype=float)
            lower, upper = np.quantile(values, [0.025, 0.975])
            paired_summary.append(
                {
                    "baseline": baseline,
                    "objective": column,
                    "mean_delta_knee_minus_baseline": float(np.mean(values)),
                    "lower_95": float(lower),
                    "upper_95": float(upper),
                    "supported_improvement": bool(upper < 0.0),
                }
            )
    paired_frame = pd.DataFrame(paired_summary)
    if save_outputs:
        save_csv(paired_frame, "q4_sapr_holdout_paired_summary.csv")
    unique_draws = validation.drop_duplicates("draw")
    summary_payload = {
        "block_length": block_length,
        "draws": int(len(unique_draws)),
        "point_non_dominated": point_non_dominated,
        "non_dominated_probability": float(np.mean(valid_flags)),
        "point_knee_distance_to_ideal": point_knee_distance,
        "point_oracle_distance_to_ideal": point_oracle_distance,
        "point_regret_vs_oracle": point_knee_distance - point_oracle_distance,
        "median_regret_vs_oracle": float(unique_draws["knee_regret_vs_oracle"].median()),
        "regret_upper_95": float(unique_draws["knee_regret_vs_oracle"].quantile(0.975)),
        "probability_within_0_10_of_oracle": float(unique_draws["knee_regret_vs_oracle"].le(0.10).mean()),
        "supported_improvement_count": int(paired_frame["supported_improvement"].sum()),
    }
    if save_outputs:
        (RESULTS_DIR / "q4_sapr_holdout_validation_summary.json").write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return float(np.mean(valid_flags)), point_non_dominated


def aggregate_macro_paths(
    scenarios: list[Scenario],
    kernel: MacroKernel,
    parameter_draws: list[dict[str, np.ndarray]],
    knee_rule: dict[str, float],
    base_price: float,
    split: str = "war_2026",
) -> pd.DataFrame:
    strategies = strategy_catalog(knee_rule)
    point = point_coefficients(kernel)
    rows: list[dict[str, Any]] = []
    target_scenarios = [scenario for scenario in scenarios if scenario.is_2026_anchor] if split == "war_2026" else [scenario for scenario in scenarios if scenario.sample_split == split]
    if not target_scenarios:
        raise ValueError(f"Q4 macro-path aggregation has no target scenarios for split={split}.")
    for strategy_name, meta in strategies.items():
        if strategy_name == "actual_2026_event_path" and split != "war_2026":
            continue
        month_records: list[dict[str, Any]] = []
        for scenario in target_scenarios:
            if strategy_name == "actual_2026_event_path":
                price, adjustment, gap, fuel_return = simulate_actual_2026_path(scenario, base_price)
            else:
                price, adjustment, gap, fuel_return = simulate_rule_path(scenario, meta["rule"], base_price)
            macro_paths = macro_path_from_returns(fuel_return, point)
            draw_paths = {outcome: [] for outcome in OUTCOMES}
            for draw in parameter_draws:
                simulated = macro_path_from_returns(fuel_return, draw)
                for outcome in OUTCOMES:
                    draw_paths[outcome].append(simulated[outcome])
            for t, period in enumerate(scenario.periods):
                record = {
                    "sample_split": split,
                    "scenario_id": scenario.scenario_id,
                    "strategy": strategy_name,
                    "month_index": t,
                    "period": period,
                    "fuel_price_cny_t": price[t],
                    "actual_adjustment_cny_t": adjustment[t],
                    "fuel_log_return": fuel_return[t],
                    "cumulative_deferred_gap_cny_t": gap[t],
                    "PPI_response_pctpt": macro_paths["china_ppi_yoy_pct"][t],
                    "CPI_response_pctpt": macro_paths["china_cpi_yoy_pct"][t],
                    "IAV_response_pctpt": macro_paths["china_iav_yoy_pct"][t],
                }
                for outcome, label in OUTCOME_LABELS.items():
                    values = np.array([path[t] for path in draw_paths[outcome]], dtype=float)
                    record[f"{label}_lower_95"] = float(np.quantile(values, 0.025))
                    record[f"{label}_upper_95"] = float(np.quantile(values, 0.975))
                month_records.append(record)
        if not month_records:
            raise ValueError(f"Q4 macro-path aggregation produced no rows for strategy={strategy_name}, split={split}.")
        rows.extend(month_records)
    return pd.DataFrame(rows)


def policy_identity_checks(scenarios: list[Scenario], base_price: float, kernel: MacroKernel) -> dict[str, Any]:
    scenario = next(item for item in scenarios if item.sample_split == "development")
    _, full_adjustment, full_gap, _ = simulate_rule_path(
        scenario,
        {"rho_normal": 1.0, "rho_stress": 1.0, "rho_extreme": 1.0},
        base_price,
    )
    synthetic = Scenario(
        scenario_id="IDENTITY_ZERO",
        sample_split="development",
        source_start="2099-01",
        periods=tuple(f"2099-0{i + 1}" for i in range(SCENARIO_LENGTH)),
        mechanism_adjustment=np.zeros(SCENARIO_LENGTH),
        actual_adjustment=np.zeros(SCENARIO_LENGTH),
        cumulative_policy_gap=np.zeros(SCENARIO_LENGTH),
        regimes=tuple(["normal"] * SCENARIO_LENGTH),
        is_2026_anchor=False,
    )
    _, _, _, zero_return = simulate_rule_path(
        synthetic,
        {"rho_normal": 0.35, "rho_stress": 0.2, "rho_extreme": 0.1},
        base_price,
    )
    zero_macro = macro_path_from_returns(zero_return, point_coefficients(kernel))
    accumulation = Scenario(
        scenario_id="IDENTITY_ACCUMULATION",
        sample_split="development",
        source_start="2099-01",
        periods=tuple(f"2099-0{i + 1}" for i in range(SCENARIO_LENGTH)),
        mechanism_adjustment=np.array([100.0, 100.0, 0.0, 0.0, 0.0, 0.0]),
        actual_adjustment=np.zeros(SCENARIO_LENGTH),
        cumulative_policy_gap=np.zeros(SCENARIO_LENGTH),
        regimes=tuple(["normal"] * SCENARIO_LENGTH),
        is_2026_anchor=False,
    )
    _, _, gap_accum, _ = simulate_rule_path(
        accumulation,
        {"rho_normal": 0.0, "rho_stress": 0.0, "rho_extreme": 0.0},
        base_price,
    )
    offset = Scenario(
        scenario_id="IDENTITY_OFFSET",
        sample_split="development",
        source_start="2099-01",
        periods=tuple(f"2099-0{i + 1}" for i in range(SCENARIO_LENGTH)),
        mechanism_adjustment=np.array([100.0, -40.0, -100.0, 0.0, 0.0, 0.0]),
        actual_adjustment=np.zeros(SCENARIO_LENGTH),
        cumulative_policy_gap=np.zeros(SCENARIO_LENGTH),
        regimes=tuple(["normal"] * SCENARIO_LENGTH),
        is_2026_anchor=False,
    )
    _, _, gap_offset, _ = simulate_rule_path(
        offset,
        {"rho_normal": 0.0, "rho_stress": 0.0, "rho_extreme": 0.0},
        base_price,
    )
    policy = read_processed("china_fuel_policy_monthly.csv")
    march = policy.loc[policy["period"].eq("2026-03")].iloc[0]
    april = policy.loc[policy["period"].eq("2026-04")].iloc[0]
    q3_repro = reproduce_q3_policy_counterfactual(kernel)
    return {
        "full_rule_max_abs_gap": float(np.max(np.abs(full_gap))),
        "full_rule_adjustment_identity_max_abs_error": float(np.max(np.abs(full_adjustment - scenario.mechanism_adjustment))),
        "zero_policy_macro_max_abs_response": float(max(np.max(np.abs(values)) for values in zero_macro.values())),
        "zero_upward_pass_through_terminal_gap": float(gap_accum[2]),
        "negative_adjustment_offsets_gap": bool(abs(float(gap_offset[2])) < 1e-9),
        "official_2026_03_gap": float(march["gasoline_policy_gap_cny_t"]),
        "official_2026_04_gap": float(april["gasoline_policy_gap_cny_t"]),
        "official_2026_04_cumulative_gap": float(april["cum_gasoline_policy_gap_cny_t"]),
        "q3_policy_counterfactual_reproduction_max_abs_error": q3_repro,
    }


def reproduce_q3_policy_counterfactual(kernel: MacroKernel) -> float:
    q3 = read_result("q3_policy_macro_counterfactual.csv")
    max_error = 0.0
    for outcome, group in q3.groupby("outcome"):
        group = group.sort_values("horizon")
        fuel = group["fuel_return_gap"].to_numpy(dtype=float)
        params = kernel.means[str(outcome)]
        expected = np.zeros(len(group), dtype=float)
        for t in range(len(group)):
            for lag in range(7):
                if t - lag >= 0:
                    expected[t] += float(params[lag]) * float(fuel[t - lag])
            if t > 0:
                expected[t] += float(params[7]) * expected[t - 1]
        observed = group["macro_counterfactual_gap_pctpt"].to_numpy(dtype=float)
        max_error = max(max_error, float(np.max(np.abs(expected - observed))))
    return float(max_error)


def run_sensitivity(
    default_grid: pd.DataFrame,
    scenarios: list[Scenario],
    kernel: MacroKernel,
    parameter_draws: list[dict[str, np.ndarray]],
    meta: dict[str, float],
    stds: dict[str, float],
    rng: np.random.Generator,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    variants = [
        ("threshold_70_90", (0.70, 0.90), {"china_ppi_yoy_pct": 1.0, "china_cpi_yoy_pct": 1.0, "china_iav_yoy_pct": 1.0}, 3),
        ("threshold_80_975", (0.80, 0.975), {"china_ppi_yoy_pct": 1.0, "china_cpi_yoy_pct": 1.0, "china_iav_yoy_pct": 1.0}, 3),
        ("cpi_weight_plus20", (0.75, 0.95), {"china_ppi_yoy_pct": 1.0, "china_cpi_yoy_pct": 1.2, "china_iav_yoy_pct": 1.0}, 3),
        ("iav_weight_plus20", (0.75, 0.95), {"china_ppi_yoy_pct": 1.0, "china_cpi_yoy_pct": 1.0, "china_iav_yoy_pct": 1.2}, 3),
        ("bootstrap_block_3", (0.75, 0.95), {"china_ppi_yoy_pct": 1.0, "china_cpi_yoy_pct": 1.0, "china_iav_yoy_pct": 1.0}, 3),
        ("bootstrap_block_6", (0.75, 0.95), {"china_ppi_yoy_pct": 1.0, "china_cpi_yoy_pct": 1.0, "china_iav_yoy_pct": 1.0}, 6),
        ("bootstrap_block_12", (0.75, 0.95), {"china_ppi_yoy_pct": 1.0, "china_cpi_yoy_pct": 1.0, "china_iav_yoy_pct": 1.0}, 12),
    ]
    point = point_coefficients(kernel)
    for variant_name, quantiles, weights, block_length in variants:
        if variant_name.startswith("threshold"):
            _, variant_scenarios, variant_meta = build_scenarios(quantiles)
        else:
            variant_scenarios = scenarios
            variant_meta = meta
        if variant_name.startswith("bootstrap_block"):
            grid = default_grid.copy()
        else:
            grid = run_grid_search(variant_scenarios, point, float(variant_meta["base_price_2026_06_cny_t"]), stds, weights)
        knee = grid.loc[grid["is_knee"]].iloc[0]
        knee_rule = {
            "rho_normal": float(knee["rho_normal"]),
            "rho_stress": float(knee["rho_stress"]),
            "rho_extreme": float(knee["rho_extreme"]),
        }
        prob, point_nd = holdout_validation_probability(
            variant_scenarios,
            parameter_draws,
            knee_rule,
            float(variant_meta["base_price_2026_06_cny_t"]),
            stds,
            weights,
            rng,
            block_length=block_length,
            point_values=point,
            save_outputs=False,
        )
        rows.append(
            {
                "variant": variant_name,
                "threshold_low_quantile": quantiles[0],
                "threshold_high_quantile": quantiles[1],
                "bootstrap_block_length": block_length,
                "ppi_weight": weights["china_ppi_yoy_pct"],
                "cpi_weight": weights["china_cpi_yoy_pct"],
                "iav_weight": weights["china_iav_yoy_pct"],
                "rho_normal": knee_rule["rho_normal"],
                "rho_stress": knee_rule["rho_stress"],
                "rho_extreme": knee_rule["rho_extreme"],
                "pareto_rule_count": int(grid["is_pareto"].sum()),
                "holdout_non_dominated_probability": prob,
                "holdout_point_non_dominated": point_nd,
                "changed_from_default": bool(
                    knee_rule["rho_normal"] != float(default_grid.loc[default_grid["is_knee"], "rho_normal"].iloc[0])
                    or knee_rule["rho_stress"] != float(default_grid.loc[default_grid["is_knee"], "rho_stress"].iloc[0])
                    or knee_rule["rho_extreme"] != float(default_grid.loc[default_grid["is_knee"], "rho_extreme"].iloc[0])
                ),
            }
        )
    return pd.DataFrame(rows)


def plot_pareto(grid: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    pareto = grid.loc[grid["is_pareto"]].copy()
    if pareto.empty:
        raise ValueError("Q4 Pareto plot requires a non-empty Pareto set.")
    volatility = pareto["J4_adjustment_volatility"].astype(float)
    size = 24.0 + 72.0 * (volatility - volatility.min()) / max(float(volatility.max() - volatility.min()), 1e-12)
    sc = ax.scatter(
        pareto["J1_macro_loss"],
        pareto["J3_avg_gap_month_burden"],
        c=pareto["J2_cvar95_macro_loss"],
        cmap="cividis",
        s=size,
        alpha=0.82,
    )
    knee = pareto.loc[pareto["is_knee"]]
    if len(knee) != 1:
        raise ValueError("Q4 Pareto plot requires exactly one knee rule.")
    ax.scatter(knee["J1_macro_loss"], knee["J3_avg_gap_month_burden"], marker="*", s=180, color=PALETTE["rose"], edgecolor="white", linewidth=0.8, label="膝点规则")
    style_axis(ax, xlabel="期望宏观损失", ylabel="平均缺口月负担")
    ax.legend(loc="upper right")
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("CVaR95宏观损失")
    finish_figure(
        fig,
        title="问题四：SAPR-CVaR 四目标Pareto前沿",
        subtitle="横纵轴为J1/J3，颜色为J2，点大小为J4；仅绘制通过硬约束的1%epsilon-非支配规则，星形为膝点。",
        source="来源：results/q4_sapr_policy_grid.csv；作者计算。",
    )
    save_figure(fig, FIGURES_DIR / "q4_sapr_pareto_front")
    plt.close(fig)


def plot_policy_heatmap(knee_rule: dict[str, float]) -> None:
    regimes = ["normal", "stress", "extreme"]
    gap_bins = ["低缺口", "中缺口", "高缺口"]
    values = np.array([[rho_for_regime(knee_rule, regime) for regime in regimes] for _ in gap_bins])
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    image = ax.imshow(values, cmap="YlGnBu", vmin=0, vmax=1)
    ax.set_xticks(np.arange(len(regimes)), labels=["普通", "压力", "极端"])
    ax.set_yticks(np.arange(len(gap_bins)), labels=gap_bins)
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            ax.text(j, i, f"{values[i, j]:.2f}", ha="center", va="center", color=PALETTE["ink"], fontsize=10)
    ax.set_xlabel("机制应调额状态")
    ax.set_ylabel("累计未调价缺口")
    cbar = fig.colorbar(image, ax=ax)
    cbar.set_label("最优传导率")
    finish_figure(
        fig,
        title="问题四：冲击强度与最优传导率",
        subtitle="SAPR规则按冲击状态调整传导率，累计缺口通过状态转移进入下一期应调额。",
        source="来源：results/q4_sapr_optimal_rule.csv；作者计算。",
    )
    save_figure(fig, FIGURES_DIR / "q4_sapr_policy_heatmap")
    plt.close(fig)


def plot_strategy_comparison(comparison: pd.DataFrame) -> None:
    frame = comparison.loc[comparison["sample_split"].eq("holdout") & comparison["strategy"].ne("actual_2026_event_path")].copy()
    if frame.empty:
        raise ValueError("Q4 strategy comparison plot requires holdout strategy rows.")
    labels = {
        "full_mechanism": "完全传导",
        "uniform_75_smoothing": "固定75%平滑",
        "temporary_2026_approx": "2026近似",
        "SAPR_CVaR_knee": "SAPR膝点",
    }
    frame["label"] = frame["strategy"].map(labels).fillna(frame["strategy"])
    metrics = ["J1_macro_loss", "J2_cvar95_macro_loss", "J3_avg_gap_month_burden", "J4_adjustment_volatility"]
    metric_labels = ["平均宏观损失", "CVaR95宏观损失", "平均缺口月负担", "月度调价波动"]
    fig, axes = plt.subplots(2, 2, figsize=(9.0, 6.4))
    colors = [PALETTE["slate"], PALETTE["gold"], PALETTE["olive"], PALETTE["blue"]]
    for ax, metric, label in zip(axes.ravel(), metrics, metric_labels):
        ax.bar(frame["label"], frame[metric].astype(float), color=colors, width=0.62)
        ax.tick_params(axis="x", labelrotation=18)
        style_axis(ax, ylabel=label)
    finish_figure(
        fig,
        title="问题四：检验期四种策略原始目标对比",
        subtitle="四个子图保留各自原始量纲；数值越低表示该目标表现越好，不能跨子图直接比较高度。",
        source="来源：results/q4_sapr_strategy_comparison.csv；作者计算。",
        rect=(0.08, 0.08, 0.98, 0.90),
    )
    save_figure(fig, FIGURES_DIR / "q4_sapr_strategy_comparison")
    plt.close(fig)


def plot_2026_paths(paths: pd.DataFrame) -> None:
    frame = paths.loc[paths["sample_split"].eq("war_2026")].copy()
    if frame.empty:
        raise ValueError("Q4 2026 path plot requires war_2026 rows.")
    labels = {
        "full_mechanism": "完全传导",
        "uniform_75_smoothing": "固定75%平滑",
        "temporary_2026_approx": "2026近似",
        "SAPR_CVaR_knee": "SAPR膝点",
        "actual_2026_event_path": "2026实际",
    }
    fig, axes = plt.subplots(2, 2, figsize=(9.0, 6.2), sharex=True)
    panels = [
        ("PPI_response_pctpt", "PPI响应"),
        ("CPI_response_pctpt", "CPI响应"),
        ("IAV_response_pctpt", "IAV响应"),
        ("cumulative_deferred_gap_cny_t", "累计缺口"),
    ]
    for ax, (column, ylabel) in zip(axes.ravel(), panels):
        for strategy, sub in frame.groupby("strategy"):
            sub = sub.sort_values("month_index")
            ax.plot(sub["month_index"], sub[column], marker="o", label=labels.get(strategy, strategy))
        ax.axhline(0, color=PALETTE["muted"], linewidth=0.7)
        style_axis(ax, ylabel=ylabel)
    axes[-1, 0].set_xlabel("冲击后月份")
    axes[-1, 1].set_xlabel("冲击后月份")
    handles, legend_labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="upper center", ncol=5, frameon=False)
    finish_figure(
        fig,
        title="问题四：2026冲击下策略路径对比",
        subtitle="宏观路径由Q3燃油价格响应核传播，累计缺口为价格平滑延期负担代理。",
        source="来源：results/q4_sapr_macro_paths.csv；作者计算。",
        rect=(0.08, 0.08, 0.98, 0.92),
    )
    save_figure(fig, FIGURES_DIR / "q4_sapr_2026_macro_paths")
    plt.close(fig)


def write_summary(
    scenario_table: pd.DataFrame,
    grid: pd.DataFrame,
    optimal: pd.DataFrame,
    comparison: pd.DataFrame,
    sensitivity: pd.DataFrame,
    identity: dict[str, Any],
    valid_draw_rate: float,
    total_draw_attempts: int,
    valid_draw_count: int,
    holdout_probability: float,
    holdout_point_non_dominated: bool,
) -> dict[str, Any]:
    validation_path = RESULTS_DIR / "q4_sapr_holdout_validation_summary.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8")) if validation_path.exists() else {}
    knee_rows = comparison.loc[comparison["strategy"].eq("SAPR_CVaR_knee")]
    knee_feasible_all_splits = bool(
        not knee_rows.empty
        and knee_rows["max_gap_ratio"].le(MAX_GAP_RATIO).all()
        and knee_rows["max_terminal_gap_ratio"].le(MAX_TERMINAL_GAP_RATIO).all()
        and knee_rows["max_recovery_terminal_gap_ratio"].le(MAX_RECOVERY_TERMINAL_GAP_RATIO).all()
        and knee_rows["max_monthly_adjustment_ratio"].le(MAX_MONTHLY_ADJUSTMENT_RATIO).all()
    )
    supported_improvements = int(validation.get("supported_improvement_count", 0))
    near_oracle_probability = float(validation.get("probability_within_0_10_of_oracle", 0.0))
    if knee_feasible_all_splits and supported_improvements >= 1 and near_oracle_probability >= 0.80:
        evidence_status = "SUPPORTED"
    elif knee_feasible_all_splits and holdout_point_non_dominated:
        evidence_status = "PARTIAL"
    else:
        evidence_status = "NOT_SUPPORTED"
    required_interval_cols = [
        "J1_macro_loss_lower_95",
        "J1_macro_loss_upper_95",
        "J2_cvar95_macro_loss_lower_95",
        "J2_cvar95_macro_loss_upper_95",
    ]
    has_complete_intervals = bool(
        set(required_interval_cols).issubset(comparison.columns)
        and np.isfinite(comparison[required_interval_cols].astype(float).to_numpy()).all()
    )
    execution_gates = {
        "q4_sapr_scenario_no_leakage_gate": bool(
            not scenario_table.empty
            and scenario_table.loc[scenario_table["sample_split"].eq("development"), "source_end"].max() <= DEVELOPMENT_END
            and scenario_table.loc[scenario_table["sample_split"].eq("holdout"), "source_start"].min() >= HOLDOUT_START
        ),
        "q4_sapr_macro_kernel_gate": bool(valid_draw_count == BOOTSTRAP_DRAWS and valid_draw_rate >= 0.95),
        "q4_sapr_policy_identity_gate": bool(
            identity["full_rule_max_abs_gap"] < 1e-8
            and identity["full_rule_adjustment_identity_max_abs_error"] < 1e-8
            and identity["zero_policy_macro_max_abs_response"] < 1e-10
            and abs(identity["official_2026_03_gap"] - 1045.0) < 1e-8
            and abs(identity["official_2026_04_gap"] - 380.0) < 1e-8
            and abs(identity["official_2026_04_cumulative_gap"] - 1425.0) < 1e-8
            and identity["q3_policy_counterfactual_reproduction_max_abs_error"] < 1e-8
            and identity["negative_adjustment_offsets_gap"]
        ),
        "q4_sapr_pareto_selection_gate": bool(len(grid) == 1771 and int(grid["is_pareto"].sum()) > 0 and int(grid["is_knee"].sum()) == 1),
        "q4_sapr_policy_feasibility_gate": knee_feasible_all_splits,
        "q4_sapr_holdout_validation_gate": bool(
            comparison["sample_split"].astype(str).eq("holdout").any()
            and "SAPR_CVaR_knee" in set(comparison["strategy"])
            and evidence_status in {"SUPPORTED", "PARTIAL", "NOT_SUPPORTED"}
        ),
        "q4_sapr_uncertainty_gate": bool(valid_draw_count == BOOTSTRAP_DRAWS and valid_draw_rate >= 0.95 and has_complete_intervals),
        "q4_sapr_claim_strength_gate": True,
    }
    execution_status = "PASS" if all(execution_gates.values()) else "FAIL"
    knee = optimal.iloc[0].to_dict()
    payload = {
        "status": execution_status,
        "execution_status": execution_status,
        "evidence_status": evidence_status,
        "model_name": "SAPR-CVaR",
        "cutoff": CUTOFF,
        "random_seed": RANDOM_SEED,
        "bootstrap_attempts": BOOTSTRAP_DRAWS,
        "bootstrap_total_draw_attempts": total_draw_attempts,
        "valid_parameter_draw_count": valid_draw_count,
        "valid_parameter_draw_rate": valid_draw_rate,
        "parameter_sampling": "joint three-equation circular moving-block bootstrap inherited from Q3; identical time blocks for PPI, CPI and IAV",
        "holdout_non_dominated_probability": holdout_probability,
        "holdout_point_non_dominated": holdout_point_non_dominated,
        "holdout_validation": validation,
        "scenario_counts": scenario_table.groupby("sample_split")["scenario_id"].nunique().to_dict(),
        "rule_count": int(len(grid)),
        "pareto_rule_count": int(grid["is_pareto"].sum()),
        "optimal_rule": {key: clean_value(value) for key, value in knee.items()},
        "identity_checks": identity,
        "execution_gates": execution_gates,
        "allowed_claims": [
            "SAPR-CVaR is optimal only within the registered three-regime smoothing family, six-month scenario library and four-objective criterion.",
            "The selected rule can be compared with full pass-through, fixed smoothing and a 2026 temporary-control approximation under the frozen Q3 macro kernel.",
            "J3 is the average monthly outstanding adjustment gap divided by the base price; terminal and recovery gaps are separate hard constraints.",
        ],
        "forbidden_claims": [
            "global optimum across all possible Chinese fuel pricing policies",
            "complete welfare gain or fiscal cost estimate",
            "the deferred gap equals government subsidy spending or a complete welfare loss",
            "Q4 uses post-2021 data to select stress thresholds or the optimal rule",
        ],
        "sensitivity_rows": int(len(sensitivity)),
        "figure_files": [
            "figures/q4_sapr_pareto_front.png",
            "figures/q4_sapr_policy_heatmap.png",
            "figures/q4_sapr_strategy_comparison.png",
            "figures/q4_sapr_2026_macro_paths.png",
        ],
    }
    (RESULTS_DIR / "q4_sapr_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plots-only", action="store_true", help="Regenerate Q4 figures from saved result tables.")
    args = parser.parse_args(argv)
    apply_paper_style()
    ensure_dirs()

    if args.plots_only:
        grid = read_result("q4_sapr_policy_grid.csv")
        optimal = read_result("q4_sapr_optimal_rule.csv")
        comparison = read_result("q4_sapr_strategy_comparison.csv")
        paths = read_result("q4_sapr_macro_paths.csv")
        knee_rule = {
            "rho_normal": float(optimal["rho_normal"].iloc[0]),
            "rho_stress": float(optimal["rho_stress"].iloc[0]),
            "rho_extreme": float(optimal["rho_extreme"].iloc[0]),
        }
        plot_pareto(grid)
        plot_policy_heatmap(knee_rule)
        plot_strategy_comparison(comparison)
        plot_2026_paths(paths)
        print(json.dumps({"status": "PASS", "mode": "plots-only", "figures": 4}, ensure_ascii=False, indent=2))
        return 0

    rng = np.random.default_rng(RANDOM_SEED)
    scenario_table, scenarios, meta = build_scenarios()
    save_csv(scenario_table, "q4_sapr_scenarios.csv")
    kernel = load_macro_kernel()
    parameter_draws, valid_draw_rate, total_draw_attempts = draw_parameter_sets(kernel, rng)
    if len(parameter_draws) != BOOTSTRAP_DRAWS:
        raise ValueError(
            f"Q4 generated {len(parameter_draws)} valid macro-parameter draws from {total_draw_attempts} attempts; "
            f"{BOOTSTRAP_DRAWS} valid draws are required."
        )
    point = point_coefficients(kernel)
    weights = {"china_ppi_yoy_pct": 1.0, "china_cpi_yoy_pct": 1.0, "china_iav_yoy_pct": 1.0}
    stds = historical_macro_stds(weights)
    base_price = float(meta["base_price_2026_06_cny_t"])
    grid = run_grid_search(scenarios, point, base_price, stds, weights)
    for key, value in meta.items():
        grid[key] = value
    save_csv(grid, "q4_sapr_policy_grid.csv")
    knee = grid.loc[grid["is_knee"]].iloc[0]
    knee_rule = {
        "rho_normal": float(knee["rho_normal"]),
        "rho_stress": float(knee["rho_stress"]),
        "rho_extreme": float(knee["rho_extreme"]),
    }
    optimal = pd.DataFrame(
        [
            {
                "model": "SAPR-CVaR",
                "rule_id": knee["rule_id"],
                "rho_normal": knee_rule["rho_normal"],
                "rho_stress": knee_rule["rho_stress"],
                "rho_extreme": knee_rule["rho_extreme"],
                "stress_threshold_75_cny_t": meta["stress_threshold_75_cny_t"],
                "stress_threshold_95_cny_t": meta["stress_threshold_95_cny_t"],
                "base_price_2026_06_cny_t": base_price,
                "J1_macro_loss": knee["J1_macro_loss"],
                "J2_cvar95_macro_loss": knee["J2_cvar95_macro_loss"],
                "J3_avg_gap_month_burden": knee["J3_avg_gap_month_burden"],
                "J4_adjustment_volatility": knee["J4_adjustment_volatility"],
                "max_gap_ratio": knee["max_gap_ratio"],
                "max_terminal_gap_ratio": knee["max_terminal_gap_ratio"],
                "max_recovery_terminal_gap_ratio": knee["max_recovery_terminal_gap_ratio"],
                "max_monthly_adjustment_ratio": knee["max_monthly_adjustment_ratio"],
                "constraint_max_gap_ratio": MAX_GAP_RATIO,
                "constraint_max_terminal_gap_ratio": MAX_TERMINAL_GAP_RATIO,
                "constraint_max_recovery_terminal_gap_ratio": MAX_RECOVERY_TERMINAL_GAP_RATIO,
                "constraint_max_monthly_adjustment_ratio": MAX_MONTHLY_ADJUSTMENT_RATIO,
                "recovery_months": RECOVERY_MONTHS,
                "pareto_rule_count": int(grid["is_pareto"].sum()),
                "feasible_rule_count": int(grid["is_feasible"].sum()),
                "candidate_rule_count": int(len(grid)),
                "selection_rule": "minimum normalized Euclidean distance to the feasible Pareto ideal; ties by smaller average gap-month burden and higher normal pass-through",
            }
        ]
    )
    save_csv(optimal, "q4_sapr_optimal_rule.csv")
    comparison, holdout_probability, holdout_point_non_dominated = compare_strategies(
        scenarios,
        kernel,
        parameter_draws,
        knee_rule,
        base_price,
        stds,
        weights,
        rng,
        block_length=6,
    )
    save_csv(comparison, "q4_sapr_strategy_comparison.csv")
    paths = aggregate_macro_paths(scenarios, kernel, parameter_draws, knee_rule, base_price, split="war_2026")
    save_csv(paths, "q4_sapr_macro_paths.csv")
    sensitivity = run_sensitivity(grid, scenarios, kernel, parameter_draws[:500], meta, stds, rng)
    save_csv(sensitivity, "q4_sapr_sensitivity.csv")
    identity = policy_identity_checks(scenarios, base_price, kernel)
    summary = write_summary(
        scenario_table,
        grid,
        optimal,
        comparison,
        sensitivity,
        identity,
        valid_draw_rate,
        total_draw_attempts,
        len(parameter_draws),
        holdout_probability,
        holdout_point_non_dominated,
    )
    plot_pareto(grid)
    plot_policy_heatmap(knee_rule)
    plot_strategy_comparison(comparison)
    plot_2026_paths(paths)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["execution_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
