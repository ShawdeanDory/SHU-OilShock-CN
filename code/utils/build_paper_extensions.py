"""Build paper-only extension tables and figures.

These outputs do not change the frozen Q1-Q4 model estimates.  They reorganize
existing results into the extra evidence modules used in the second paper
version: Q1 event/structure synthesis, Q2 heterogeneous transmission, Q3
partial identification, and Q4 paired holdout/path diagnostics.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.api import VAR


REPO_ROOT = Path(__file__).resolve().parents[2]
CODE_DIR = REPO_ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from utils.plot_style import PALETTE, apply_paper_style, finish_figure, save_figure, style_axis

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RESULTS_DIR = REPO_ROOT / "results"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
FIGURES_DIR = REPO_ROOT / "figures"
RANDOM_SEED = 20260730

SHOCK_LABELS = {
    "supply_shock": "不利供给",
    "aggregate_demand_shock": "全球需求",
    "oil_specific_risk_shock": "石油特定风险",
}
OUTCOME_LABELS = {
    "brent_cny_cost_log_change_pct": "人民币原油成本",
    "china_ppi_yoy_pct": "PPI",
    "china_cpi_yoy_pct": "CPI",
    "china_iav_yoy_pct": "工业增加值",
}
OBJECTIVE_LABELS = {
    "J1_macro_loss": "平均宏观损失",
    "J2_cvar95_macro_loss": "CVaR95宏观损失",
    "J3_avg_gap_month_burden": "平均缺口月负担",
    "J4_adjustment_volatility": "调价波动",
}


def read_result(filename: str) -> pd.DataFrame:
    path = RESULTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing result file: {path}")
    return pd.read_csv(path)


def read_processed(filename: str) -> pd.DataFrame:
    path = PROCESSED_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing processed file: {path}")
    return pd.read_csv(path)


def save_csv(frame: pd.DataFrame, filename: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / filename
    frame.to_csv(path, index=False, encoding="utf-8")
    return path


def clean_value(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else round(float(value), 8)
    if pd.isna(value):
        return None
    return value


def zscore(values: np.ndarray) -> np.ndarray:
    mean = float(np.nanmean(values))
    std = float(np.nanstd(values, ddof=1))
    if std <= 0 or not np.isfinite(std):
        raise ValueError("Cannot standardize a zero-variance vector.")
    return (values - mean) / std


def fit_q1_svar() -> tuple[pd.DataFrame, Any, np.ndarray, np.ndarray]:
    monthly = read_processed("model_monthly_q1.csv")
    global_input = read_processed("global_oil_svar_monthly.csv")
    frame = (
        monthly[["period", "month_end", "brent_usd_bbl_log_return"]]
        .merge(global_input, on="period", how="left")
        .sort_values("period")
        .reset_index(drop=True)
    )
    frame["supply_growth"] = np.log(pd.to_numeric(frame["world_liquids_supply"], errors="coerce")).diff() * 100.0
    frame["real_brent_return"] = np.log(pd.to_numeric(frame["real_brent"], errors="coerce")).diff() * 100.0
    var_cols = ["supply_growth", "global_real_activity", "real_brent_return"]
    var_data = frame.dropna(subset=var_cols).copy().set_index("period")
    selected = read_result("q1_svar_diagnostics.csv")
    selected = selected.loc[selected["is_selected"].astype(str).str.lower().isin(["true", "1"])]
    if len(selected) != 1:
        raise ValueError("Q1 SVAR diagnostics must contain exactly one selected row.")
    lag = int(selected["candidate_lags"].iloc[0])
    fit = VAR(var_data[var_cols]).fit(lag)
    if not fit.is_stable(verbose=False):
        raise ValueError("Selected Q1 VAR is not stable.")
    sigma_u = np.asarray(fit.sigma_u, dtype=float)
    chol = np.linalg.cholesky(sigma_u)
    residuals = fit.resid[var_cols].copy()
    structural = np.linalg.solve(chol, residuals.to_numpy(dtype=float).T).T
    return var_data, fit, chol, structural


def build_q1_historical_decomposition() -> pd.DataFrame:
    var_data, fit, chol, structural = fit_q1_svar()
    periods = list(fit.resid.index.astype(str))
    eps = pd.DataFrame(
        structural,
        index=periods,
        columns=["raw_supply", "raw_aggregate_demand", "raw_oil_specific_risk"],
    )
    ma = fit.ma_rep(maxn=24)
    effects = np.einsum("hij,jk->hik", ma, chol)
    price_idx = 2
    shock_names = ["raw_supply", "raw_aggregate_demand", "raw_oil_specific_risk"]
    contribution_rows: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    for row_idx, period in enumerate(periods):
        contribs: dict[str, float] = {}
        for shock_idx, shock_name in enumerate(shock_names):
            total = 0.0
            max_h = min(24, row_idx)
            for horizon in range(max_h + 1):
                total += float(effects[horizon, price_idx, shock_idx] * eps.iloc[row_idx - horizon, shock_idx])
            contribs[shock_name] = total
        total_model = float(sum(contribs.values()))
        actual = float(var_data.loc[period, "real_brent_return"])
        all_rows.append(
            {
                "period": period,
                "supply_contribution": contribs["raw_supply"],
                "aggregate_demand_contribution": contribs["raw_aggregate_demand"],
                "oil_specific_risk_contribution": contribs["raw_oil_specific_risk"],
                "total_model_contribution": total_model,
                "actual_real_brent_return": actual,
            }
        )
    all_frame = pd.DataFrame(all_rows)
    reference = all_frame["total_model_contribution"].dropna()
    lower_ref = float(reference.quantile(0.025))
    upper_ref = float(reference.quantile(0.975))
    abs_ref = reference.abs().to_numpy()
    target = all_frame.loc[all_frame["period"].between("2026-03", "2026-06")].copy()
    for row in target.to_dict("records"):
        percentile = float((abs_ref <= abs(float(row["total_model_contribution"]))).mean())
        row["lower_95"] = lower_ref
        row["upper_95"] = upper_ref
        row["historical_percentile"] = percentile
        row["interval_type"] = "historical_empirical_reference_interval"
        contribution_rows.append(row)
    result = pd.DataFrame(contribution_rows)
    save_csv(result, "paper_extension_q1_historical_decomposition.csv")
    return result


def plot_q1_event_structural_synthesis(decomposition: pd.DataFrame) -> None:
    placebos = read_result("q1_placebo_distribution.csv")
    effects = read_result("q1_event_effects.csv")
    car_rows = effects.loc[
        effects["model"].eq("brent_usd_bbl_event_car")
        & effects["stage_id"].isin(["E1_CAR_0", "E1_CAR_0_1", "E1_CAR_0_2"])
    ].copy()
    if len(car_rows) != 3:
        raise ValueError("Q1 synthesis figure requires three Brent CAR rows.")
    labels = {"E1_CAR_0": "CAR[0]", "E1_CAR_0_1": "CAR[0,+1]", "E1_CAR_0_2": "CAR[0,+2]"}
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.2), gridspec_kw={"width_ratios": [1.0, 1.2]})

    ax = axes[0]
    positions = np.arange(3)
    for pos, stage_id in zip(positions, ["E1_CAR_0", "E1_CAR_0_1", "E1_CAR_0_2"]):
        pseudo = placebos.loc[placebos["stage_id"].eq(stage_id), "estimate_log_return"].abs().to_numpy(dtype=float)
        actual = float(car_rows.loc[car_rows["stage_id"].eq(stage_id), "estimate_log_return"].abs().iloc[0])
        jitter = np.linspace(-0.14, 0.14, len(pseudo))
        ax.scatter(np.full(len(pseudo), pos) + jitter, pseudo, s=12, color=PALETTE["blue_light"], alpha=0.75)
        ax.scatter([pos], [actual], s=46, color=PALETTE["rose"], marker="D", label="真实CAR" if pos == 0 else None)
    ax.set_xticks(positions, [labels[value] for value in ["E1_CAR_0", "E1_CAR_0_1", "E1_CAR_0_2"]])
    style_axis(ax, ylabel="绝对CAR")
    ax.legend(loc="upper left")

    ax = axes[1]
    row = decomposition.iloc[0]
    values = [
        float(row["supply_contribution"]),
        float(row["aggregate_demand_contribution"]),
        float(row["oil_specific_risk_contribution"]),
        float(row["total_model_contribution"]),
        float(row["actual_real_brent_return"]),
    ]
    names = ["供给项", "全球需求", "石油特定风险", "模型贡献合计", "实际实际油价收益"]
    colors = [PALETTE["rose"], PALETTE["olive"], PALETTE["blue"], PALETTE["slate"], PALETTE["ink"]]
    y_pos = np.arange(len(values))
    ax.barh(y_pos, values, color=colors, alpha=0.88)
    ax.axvline(0.0, color=PALETTE["muted"], linewidth=0.7)
    ax.axvspan(float(row["lower_95"]), float(row["upper_95"]), color=PALETTE["sand"], alpha=0.18)
    for idx, value in enumerate(values):
        ha = "left" if value >= 0 else "right"
        x_offset = 0.6 if value >= 0 else -0.6
        ax.text(value + x_offset, idx, f"{value:.1f}", va="center", ha=ha, fontsize=8.4, color=PALETTE["ink"])
    ax.set_yticks(y_pos, names)
    ax.invert_yaxis()
    style_axis(ax, xlabel="2026-03收益贡献/百分点")
    ax.text(
        0.02,
        0.04,
        "淡色带为历史95%参考区间",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=8.0,
        color=PALETTE["muted"],
    )

    finish_figure(
        fig,
        title="问题一：事件证据与结构贡献合成",
        subtitle="左侧为状态匹配安慰剂绝对CAR分布；右侧为给定SVAR识别下2026年3月可审计结构贡献。",
        source="来源：results/q1_placebo_distribution.csv、paper_extension_q1_historical_decomposition.csv；作者计算。",
        rect=(0.07, 0.10, 0.98, 0.92),
    )
    save_figure(fig, FIGURES_DIR / "paper_extension_q1_event_structural_synthesis")
    plt.close(fig)


def build_q2_shock_matrix() -> pd.DataFrame:
    metrics = read_result("q2_transmission_metrics.csv")
    shocks = ["supply_shock", "aggregate_demand_shock", "oil_specific_risk_shock"]
    outcomes = list(OUTCOME_LABELS)
    frame = metrics.loc[metrics["shock"].isin(shocks) & metrics["outcome"].isin(outcomes)].copy()
    if len(frame) != len(shocks) * len(outcomes):
        raise ValueError("Q2 matrix requires all structural-shock/outcome metric cells.")
    frame["shock_label"] = frame["shock"].map(SHOCK_LABELS)
    frame["outcome_label"] = frame["outcome"].map(OUTCOME_LABELS)
    frame["joint_interval_crosses_zero"] = (
        pd.to_numeric(frame["extremum_joint_lower_95"], errors="coerce").le(0)
        & pd.to_numeric(frame["extremum_joint_upper_95"], errors="coerce").ge(0)
    )
    frame["direction"] = np.where(pd.to_numeric(frame["extremum_response"], errors="coerce") >= 0, "正向", "负向")
    result = frame[
        [
            "shock",
            "shock_label",
            "outcome",
            "outcome_label",
            "extremum_type",
            "extremum_response",
            "extremum_month",
            "extremum_joint_lower_95",
            "extremum_joint_upper_95",
            "joint_interval_crosses_zero",
            "direction",
            "response_curve_area_0_6",
            "response_curve_area_0_12",
            "area_unit",
            "evidence_status",
        ]
    ].sort_values(["outcome", "shock"])
    save_csv(result, "paper_extension_q2_shock_matrix.csv")
    return result


def plot_q2_shock_matrix(matrix: pd.DataFrame) -> None:
    shock_order = ["supply_shock", "aggregate_demand_shock", "oil_specific_risk_shock"]
    outcome_order = list(OUTCOME_LABELS)
    pivot = matrix.pivot(index="outcome", columns="shock", values="extremum_response").loc[outcome_order, shock_order]
    cross = matrix.pivot(index="outcome", columns="shock", values="joint_interval_crosses_zero").loc[outcome_order, shock_order]
    fig, ax = plt.subplots(figsize=(7.3, 4.3))
    vmax = float(np.nanmax(np.abs(pivot.to_numpy(dtype=float))))
    image = ax.imshow(pivot.to_numpy(dtype=float), cmap="RdBu_r", vmin=-vmax, vmax=vmax)
    ax.set_xticks(np.arange(len(shock_order)), [SHOCK_LABELS[value] for value in shock_order])
    ax.set_yticks(np.arange(len(outcome_order)), [OUTCOME_LABELS[value] for value in outcome_order])
    for i, outcome in enumerate(outcome_order):
        for j, shock in enumerate(shock_order):
            value = float(pivot.loc[outcome, shock])
            marker = "跨零" if bool(cross.loc[outcome, shock]) else "不跨零"
            ax.text(j, i, f"{value:.2f}\n{marker}", ha="center", va="center", fontsize=8.4, color=PALETTE["ink"])
    cbar = fig.colorbar(image, ax=ax)
    cbar.set_label("极值响应（百分点或对数百分点）")
    finish_figure(
        fig,
        title="问题二：三类结构冲击的异质传导矩阵",
        subtitle="单元格数值为变量极值响应；跨零表示95%联合区间包含零。",
        source="来源：results/q2_transmission_metrics.csv；作者计算。",
    )
    save_figure(fig, FIGURES_DIR / "paper_extension_q2_shock_matrix")
    plt.close(fig)


def add_country_lags(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.sort_values("period").copy()
    for lag in range(7):
        result[f"brent_lag{lag}"] = result["brent_local_log_return"].shift(lag)
    result["fuel_lag1"] = result["fuel_log_return"].shift(1)
    return result


def fit_pass_through_coefficients(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    data = add_country_lags(frame)
    regressors = [f"brent_lag{lag}" for lag in range(7)] + ["fuel_lag1"]
    usable = data.dropna(subset=["fuel_log_return"] + regressors).copy()
    if len(usable) < 48:
        raise ValueError("Q3 partial identification needs at least 48 fuel observations per country.")
    x = np.column_stack([np.ones(len(usable)), usable[regressors].to_numpy(dtype=float)])
    y = usable["fuel_log_return"].to_numpy(dtype=float)
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    residuals = y - x @ beta
    usable = usable.reset_index(drop=True)
    return beta, residuals, usable


def block_resample_residuals(residuals: np.ndarray, rng: np.random.Generator, block_length: int = 6) -> np.ndarray:
    n = len(residuals)
    starts = rng.integers(0, n, size=int(np.ceil(n / block_length)))
    sampled = []
    for start in starts:
        for offset in range(block_length):
            sampled.append(residuals[(int(start) + offset) % n])
            if len(sampled) == n:
                return np.array(sampled, dtype=float)
    return np.array(sampled[:n], dtype=float)


def build_q3_partial_identification(draws: int = 2000) -> pd.DataFrame:
    panel = read_processed("model_country_monthly.csv")
    pass_through = read_result("q3_country_pass_through.csv")
    h6 = pass_through.loc[pass_through["horizon"].eq(6)].copy()
    china_proxy = float(h6.loc[h6["country"].eq("CHN"), "response"].iloc[0])
    controls = h6.loc[h6["included_in_main_comparison"].astype(str).str.lower().isin(["true", "1"])]
    control_median = float(controls["response"].median())
    base_kappa = control_median / china_proxy

    countries = ["CHN"] + sorted(controls["country"].unique().tolist())
    fits: dict[str, tuple[np.ndarray, np.ndarray, pd.DataFrame]] = {}
    for country in countries:
        fits[country] = fit_pass_through_coefficients(panel.loc[panel["country"].eq(country)].copy())
    shapes = {
        "uniform": np.ones(7),
        "front_loaded_discount": np.array([1.00, 0.95, 0.90, 0.85, 0.80, 0.75, 0.70]),
        "back_loaded_discount": np.array([0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00]),
    }
    rng = np.random.default_rng(RANDOM_SEED)
    records: list[dict[str, Any]] = []
    boot_values = {shape_name: [] for shape_name in shapes}
    for _ in range(draws):
        estimates: dict[str, float] = {}
        shaped_china: dict[str, float] = {}
        for country in countries:
            beta, residuals, usable = fits[country]
            regressors = [f"brent_lag{lag}" for lag in range(7)] + ["fuel_lag1"]
            x = np.column_stack([np.ones(len(usable)), usable[regressors].to_numpy(dtype=float)])
            y_star = x @ beta + block_resample_residuals(residuals, rng)
            beta_star = np.linalg.lstsq(x, y_star, rcond=None)[0]
            estimates[country] = float(beta_star[1:8].sum())
            if country == "CHN":
                for shape_name, shape in shapes.items():
                    shaped_china[shape_name] = float((beta_star[1:8] * shape).sum())
        median_controls = float(np.median([estimates[country] for country in countries if country != "CHN"]))
        for shape_name in shapes:
            denominator = shaped_china[shape_name]
            if denominator > 0:
                boot_values[shape_name].append(median_controls / denominator)
    for shape_name, values in boot_values.items():
        arr = np.array(values, dtype=float)
        records.append(
            {
                "scenario": shape_name,
                "china_proxy_h6": china_proxy,
                "control_median_h6": control_median,
                "critical_kappa_point": base_kappa if shape_name == "uniform" else control_median / float((fits["CHN"][0][1:8] * shapes[shape_name]).sum()),
                "critical_kappa_bootstrap_median": float(np.median(arr)),
                "critical_kappa_lower_95": float(np.quantile(arr, 0.025)),
                "critical_kappa_upper_95": float(np.quantile(arr, 0.975)),
                "bootstrap_draws": int(len(arr)),
                "bootstrap_block_length_months": 6,
                "interpretation": "threshold for a scaled China proxy to equal the six-country official-retail median; not a formal country ranking",
            }
        )
    result = pd.DataFrame(records)
    save_csv(result, "paper_extension_q3_partial_identification.csv")
    return result


def plot_q3_partial_identification(partial: pd.DataFrame) -> None:
    frame = partial.copy()
    labels = {
        "uniform": "比例缩放",
        "front_loaded_discount": "前端折扣",
        "back_loaded_discount": "后端折扣",
    }
    y = np.arange(len(frame))
    point = frame["critical_kappa_bootstrap_median"].to_numpy(dtype=float)
    lower = frame["critical_kappa_lower_95"].to_numpy(dtype=float)
    upper = frame["critical_kappa_upper_95"].to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    ax.errorbar(point, y, xerr=[point - lower, upper - point], fmt="o", color=PALETTE["blue"], ecolor=PALETTE["blue_light"], capsize=3)
    ax.axvline(1.0, color=PALETTE["muted"], linewidth=0.8, linestyle=(0, (3, 2)))
    ax.set_yticks(y, [labels[value] for value in frame["scenario"]])
    ax.invert_yaxis()
    style_axis(ax, xlabel="临界缩放系数 kappa*")
    finish_figure(
        fig,
        title="问题三：中国代理传导率的部分识别临界值",
        subtitle="若真实固定品类零售价传导低于代理值的临界比例，则中国才可能低于六国中位数。",
        source="来源：data/processed/model_country_monthly.csv、results/q3_country_pass_through.csv；作者计算。",
    )
    save_figure(fig, FIGURES_DIR / "paper_extension_q3_partial_identification")
    plt.close(fig)


def build_claim_boundary_table() -> pd.DataFrame:
    rows = [
        {
            "claim": "Q1前两交易日存在状态条件下罕见的异常上涨",
            "evidence": "CAR[0]和CAR[0,+1]的匹配placebo经验p值均为0.0244",
            "status": "支持",
            "allowed_wording": "事件相关异常上涨",
            "forbidden_wording": "严格战争净因果溢价",
        },
        {
            "claim": "Q1结构冲击可供Q2/Q3作事后传导输入",
            "evidence": "三类SVAR结构冲击均有186个月且稳定性探针通过",
            "status": "支持",
            "allowed_wording": "给定SVAR识别下的结构贡献",
            "forbidden_wording": "唯一真实冲击分解",
        },
        {
            "claim": "Q2油价特定风险冲击会提高成本并可能推高PPI/CPI",
            "evidence": "成本入口联合区间不跨零；PPI/CPI/IAV联合区间多跨零",
            "status": "部分支持",
            "allowed_wording": "方向和量级估计",
            "forbidden_wording": "稳健总体增长损失",
        },
        {
            "claim": "Q3中国综合应对显著优于六国",
            "evidence": "中国燃油为代理层；CPI和工业活动缺联合差异区间",
            "status": "结论不充分",
            "allowed_wording": "跨国总体韧性证据不足",
            "forbidden_wording": "中国显著更优",
        },
        {
            "claim": "Q3 2026临时调控降低物价压力",
            "evidence": "无调控减实际路径在2026-06的PPI/CPI区间不跨零",
            "status": "部分支持",
            "allowed_wording": "条件动态反事实下的PPI/CPI缓冲",
            "forbidden_wording": "无成本福利改善",
        },
        {
            "claim": "Q4 SAPR在注册规则族内改善风险-波动权衡",
            "evidence": "检验期J1/J2/J4配对差区间小于零，J3代价为正",
            "status": "支持",
            "allowed_wording": "注册规则族内的Pareto权衡改进",
            "forbidden_wording": "全球最优或完整福利最优",
        },
    ]
    result = pd.DataFrame(rows)
    result.insert(0, "claim_id", ["q1_event", "q1_structural", "q2_macro", "q3_resilience", "q3_policy", "q4_sapr"])
    result["topic"] = result["claim"]
    result["evidence_status"] = result["status"]
    result["allowed_claim"] = result["allowed_wording"]
    result["forbidden_claim"] = result["forbidden_wording"]
    result = result[
        [
            "claim_id",
            "topic",
            "evidence",
            "evidence_status",
            "allowed_claim",
            "forbidden_claim",
            "claim",
            "status",
            "allowed_wording",
            "forbidden_wording",
        ]
    ]
    save_csv(result, "paper_extension_claim_boundary.csv")
    return result


def plot_q4_holdout_forest() -> None:
    paired = read_result("q4_sapr_holdout_paired_summary.csv")
    frame = paired.loc[paired["baseline"].eq("full_mechanism")].copy()
    order = ["J1_macro_loss", "J2_cvar95_macro_loss", "J3_avg_gap_month_burden", "J4_adjustment_volatility"]
    frame["objective_order"] = frame["objective"].map({name: idx for idx, name in enumerate(order)})
    frame = frame.sort_values("objective_order")
    y = np.arange(len(frame))
    point = frame["mean_delta_knee_minus_baseline"].to_numpy(dtype=float)
    lower = frame["lower_95"].to_numpy(dtype=float)
    upper = frame["upper_95"].to_numpy(dtype=float)
    colors = [PALETTE["blue"] if value < 0 else PALETTE["rose"] for value in point]
    fig, ax = plt.subplots(figsize=(7.0, 3.8))
    for idx in range(len(frame)):
        ax.errorbar(
            point[idx],
            y[idx],
            xerr=[[point[idx] - lower[idx]], [upper[idx] - point[idx]]],
            fmt="o",
            color=colors[idx],
            ecolor=PALETTE["slate"],
            capsize=3,
        )
    ax.axvline(0.0, color=PALETTE["muted"], linewidth=0.8, linestyle=(0, (3, 2)))
    ax.set_yticks(y, [OBJECTIVE_LABELS[value] for value in frame["objective"]])
    ax.invert_yaxis()
    style_axis(ax, xlabel="SAPR膝点减完全传导")
    finish_figure(
        fig,
        title="问题四：SAPR相对完全传导的配对检验",
        subtitle="负值表示SAPR在该目标上更低；J3为延期缺口负担，正值表示平滑代价。",
        source="来源：results/q4_sapr_holdout_paired_summary.csv；作者计算。",
    )
    save_figure(fig, FIGURES_DIR / "paper_extension_q4_holdout_forest")
    plt.close(fig)


def plot_q4_2026_paths() -> None:
    paths = read_result("q4_sapr_macro_paths.csv")
    optimal = read_result("q4_sapr_optimal_rule.csv")
    base_price = float(optimal["base_price_2026_06_cny_t"].iloc[0])
    frame = paths.loc[
        paths["sample_split"].eq("war_2026")
        & paths["strategy"].isin(["full_mechanism", "temporary_2026_approx", "SAPR_CVaR_knee", "actual_2026_event_path"])
    ].copy()
    labels = {
        "full_mechanism": "完全传导",
        "temporary_2026_approx": "2026近似",
        "SAPR_CVaR_knee": "SAPR膝点",
        "actual_2026_event_path": "2026实际",
    }
    colors = {
        "full_mechanism": PALETTE["slate"],
        "temporary_2026_approx": PALETTE["gold"],
        "SAPR_CVaR_knee": PALETTE["blue"],
        "actual_2026_event_path": PALETTE["ink"],
    }
    fig, axes = plt.subplots(2, 2, figsize=(9.1, 6.2), sharex=True)
    panels = [
        ("PPI_response_pctpt", "PPI响应/百分点", "PPI_lower_95", "PPI_upper_95"),
        ("CPI_response_pctpt", "CPI响应/百分点", "CPI_lower_95", "CPI_upper_95"),
        ("IAV_response_pctpt", "IAV响应/百分点", "IAV_lower_95", "IAV_upper_95"),
        ("gap_ratio", "累计缺口/基准价格", None, None),
    ]
    frame["gap_ratio"] = frame["cumulative_deferred_gap_cny_t"] / base_price
    for ax, (column, ylabel, lower_col, upper_col) in zip(axes.ravel(), panels):
        for strategy, sub in frame.groupby("strategy"):
            sub = sub.sort_values("month_index")
            ax.plot(sub["month_index"], sub[column], marker="o", label=labels[strategy], color=colors[strategy], linewidth=1.45)
            if strategy == "SAPR_CVaR_knee" and lower_col and upper_col:
                ax.fill_between(
                    sub["month_index"].to_numpy(dtype=float),
                    sub[lower_col].to_numpy(dtype=float),
                    sub[upper_col].to_numpy(dtype=float),
                    color=PALETTE["blue_light"],
                    alpha=0.20,
                    linewidth=0,
                )
        ax.axhline(0.0, color=PALETTE["muted"], linewidth=0.7)
        if column == "gap_ratio":
            ax.axhline(0.20, color=PALETTE["rose"], linewidth=0.8, linestyle=(0, (3, 2)), label="20%硬约束")
            ax.axhline(0.05, color=PALETTE["olive"], linewidth=0.8, linestyle=(0, (2, 2)), label="5%恢复约束")
        style_axis(ax, ylabel=ylabel)
    axes[1, 0].set_xlabel("冲击后月份")
    axes[1, 1].set_xlabel("冲击后月份")
    handles, legend_labels = axes[0, 0].get_legend_handles_labels()
    gap_handles, gap_labels = axes[1, 1].get_legend_handles_labels()
    combined = dict(zip(legend_labels + gap_labels, handles + gap_handles))
    fig.legend(combined.values(), combined.keys(), loc="upper center", ncol=6, frameon=False, fontsize=8.2)
    finish_figure(
        fig,
        title="问题四：2026冲击下策略宏观路径与缺口约束",
        subtitle="SAPR宏观路径阴影为95%区间；缺口面板用基准价格归一化并标出硬约束。",
        source="来源：results/q4_sapr_macro_paths.csv；作者计算。",
        rect=(0.08, 0.08, 0.98, 0.91),
    )
    save_figure(fig, FIGURES_DIR / "paper_extension_q4_2026_paths")
    plt.close(fig)


def write_summary(
    decomposition: pd.DataFrame,
    q2_matrix: pd.DataFrame,
    q3_partial: pd.DataFrame,
    claim_boundary: pd.DataFrame,
) -> dict[str, Any]:
    payload = {
        "status": "PASS",
        "random_seed": RANDOM_SEED,
        "outputs": {
            "q1_historical_decomposition_rows": int(len(decomposition)),
            "q2_shock_matrix_rows": int(len(q2_matrix)),
            "q3_partial_identification_rows": int(len(q3_partial)),
            "claim_boundary_rows": int(len(claim_boundary)),
        },
        "figures": [
            "figures/paper_extension_q1_event_structural_synthesis.png",
            "figures/paper_extension_q2_shock_matrix.png",
            "figures/paper_extension_q3_partial_identification.png",
            "figures/paper_extension_q4_holdout_forest.png",
            "figures/paper_extension_q4_2026_paths.png",
        ],
        "allowed_claims": [
            "Q1 structural contributions are conditional on the recursive SVAR identification.",
            "Q2 heterogeneous transmission is reported by shock source and outcome, not as a single oil-price effect.",
            "Q3 kappa thresholds quantify the China proxy comparability boundary and do not rank China formally.",
            "Q4 paired differences show risk and volatility improvements together with deferred-gap costs.",
        ],
        "forbidden_claims": [
            "Q1 historical decomposition is a war net causal contribution.",
            "China proxy pass-through is a fixed-product retail ranking.",
            "SAPR-CVaR is globally welfare optimal.",
        ],
    }
    path = RESULTS_DIR / "paper_extension_summary.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    apply_paper_style()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    decomposition = build_q1_historical_decomposition()
    plot_q1_event_structural_synthesis(decomposition)
    q2_matrix = build_q2_shock_matrix()
    plot_q2_shock_matrix(q2_matrix)
    q3_partial = build_q3_partial_identification()
    plot_q3_partial_identification(q3_partial)
    claim_boundary = build_claim_boundary_table()
    plot_q4_holdout_forest()
    plot_q4_2026_paths()
    summary = write_summary(decomposition, q2_matrix, q3_partial, claim_boundary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
