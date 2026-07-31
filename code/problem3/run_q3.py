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


COUNTRY_ORDER = ["CHN", "DEU", "JPN", "KOR"]
COUNTRY_LABEL_ZH = {"CHN": "中国", "DEU": "德国", "JPN": "日本", "KOR": "韩国"}
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


def panel_design(frame: pd.DataFrame, outcome: str, horizon: int) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    data = frame.copy()
    data["month"] = pd.to_datetime(data["period"] + "-01").dt.month
    if outcome == "fuel":
        data["target"] = data.groupby("country")["fuel_log"].shift(-horizon) - data.groupby("country")["fuel_log"].shift(1)
        data["target"] = data["target"] * 100.0
        needed = ["target", "OilShock", "fuel_log"]
    elif outcome == "cpi":
        data["target"] = data.groupby("country")["cpi_yoy_pct"].shift(-horizon)
        needed = ["target", "OilShock", "cpi_yoy_pct"]
    else:
        data["target"] = data.groupby("country")["ip_yoy_log_change_pct"].shift(-horizon)
        needed = ["target", "OilShock", "ip_yoy_log_change_pct"]
    data["trend"] = data.groupby("country").cumcount()
    for country in COUNTRY_ORDER:
        data[f"oil_{country}"] = np.where(data["country"].eq(country), data["OilShock"], 0.0)
        data[f"trend_{country}"] = np.where(data["country"].eq(country), data["trend"], 0.0)
    month_dummies = pd.get_dummies(data["month"], prefix="month", drop_first=True, dtype=float)
    data = pd.concat([data, month_dummies], axis=1)
    needed += [f"oil_{country}" for country in COUNTRY_ORDER]
    x_cols = [f"oil_{country}" for country in COUNTRY_ORDER] + [f"trend_{country}" for country in COUNTRY_ORDER] + list(month_dummies.columns) + ["GPR"]
    usable = data.dropna(subset=needed + ["GPR"]).copy()
    usable["month_index"] = pd.PeriodIndex(usable["period"], freq="M").to_timestamp()
    usable = usable.set_index(["country", "month_index"]).sort_index()
    y = usable["target"].astype(float)
    x = usable[x_cols].astype(float)
    return y, x, usable.reset_index()


def fit_panel_lp(panel: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    from linearmodels.panel import PanelOLS

    rows: list[dict[str, Any]] = []
    for outcome in ["fuel", "cpi", "ip"]:
        outcome_panel = panel.loc[bool_series(panel["included_in_main_comparison"])].copy() if outcome == "fuel" and "included_in_main_comparison" in panel else panel.copy()
        for horizon in range(13):
            try:
                y, x, usable = panel_design(outcome_panel, outcome, horizon)
                if len(y) < x.shape[1] + 20 or y.index.get_level_values(0).nunique() < 3:
                    warnings_log.append({"code": "q3_panel_lp_skipped", "message": f"{outcome} h={horizon}: insufficient panel support."})
                    continue
                fit = PanelOLS(y, x, entity_effects=True, drop_absorbed=True, check_rank=False).fit(
                    cov_type="kernel",
                    kernel="bartlett",
                    bandwidth=max(1, horizon + 1),
                )
                for country in COUNTRY_ORDER:
                    term = f"oil_{country}"
                    if term not in fit.params.index:
                        continue
                    estimate = float(fit.params[term])
                    se = float(fit.std_errors[term])
                    rows.append(
                        {
                            "outcome": outcome,
                            "country": country,
                            "horizon": horizon,
                            "response": estimate,
                            "std_error": se,
                            "lower_80": estimate - norm.ppf(0.90) * se,
                            "upper_80": estimate + norm.ppf(0.90) * se,
                            "lower_95": estimate - norm.ppf(0.975) * se,
                            "upper_95": estimate + norm.ppf(0.975) * se,
                            "pvalue": float(fit.pvalues[term]),
                            "model": "stacked_panel_LP",
                            "specification": "country FE, month seasonality, country trends, OilShock x country, Driscoll-Kraay covariance",
                            "sample_start": usable["period"].min(),
                            "sample_end": usable["period"].max(),
                            "n": int(len(usable)),
                        }
                    )
            except Exception as exc:
                warnings_log.append({"code": "q3_panel_lp_failed", "message": f"{outcome} h={horizon}: {exc}"})
    result = pd.DataFrame(rows)
    save_csv(result, "q3_panel_irf.csv")
    return result


def china_fuel_to_cpi_elasticity(country_panel: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> dict[str, float]:
    chn = country_panel.loc[country_panel["country"].eq("CHN")].sort_values("period").copy()
    chn = add_lags(chn, "fuel_log_return", 6)
    chn["cpi_lag1"] = chn["cpi_yoy_pct"].shift(1)
    regressors = [f"fuel_log_return_lag{lag}" for lag in range(7)] + ["cpi_lag1", "GPR"]
    usable = chn.dropna(subset=["cpi_yoy_pct"] + regressors)
    if len(usable) < 48:
        warnings_log.append({"code": "q3_policy_macro_elasticity_missing", "message": "Too few China proxy fuel observations for CPI propagation."})
        return {"cpi_cumulative_elasticity": np.nan, "cpi_elasticity_se": np.nan}
    fit = sm.OLS(usable["cpi_yoy_pct"], sm.add_constant(usable[regressors].astype(float), has_constant="add")).fit(
        cov_type="HAC",
        cov_kwds={"maxlags": 6},
    )
    lag_terms = [f"fuel_log_return_lag{lag}" for lag in range(7)]
    estimate = float(fit.params[lag_terms].sum())
    cov = fit.cov_params().loc[lag_terms, lag_terms]
    se = float(np.sqrt(np.ones(len(lag_terms)) @ cov.to_numpy() @ np.ones(len(lag_terms))))
    return {"cpi_cumulative_elasticity": estimate, "cpi_elasticity_se": se}


def policy_counterfactual(country_panel: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    china_proxy = pd.read_csv(PROCESSED_DIR / "china_fuel_proxy_monthly.csv")
    policy = pd.read_csv(PROCESSED_DIR / "china_fuel_policy_monthly.csv")
    frame = china_proxy.merge(
        policy[["period", "gasoline_policy_gap_cny_t", "diesel_policy_gap_cny_t", "cum_gasoline_policy_gap_cny_t", "cum_diesel_policy_gap_cny_t"]],
        on="period",
        how="left",
        suffixes=("", "_policy"),
    )
    frame = frame.loc[frame["period"].between("2026-02", "2026-06")].copy()
    elasticity = china_fuel_to_cpi_elasticity(country_panel, warnings_log)
    frame["policy_adjusted_proxy_cny_t"] = frame["china_gasoline_proxy_cny_t"]
    frame["no_temporary_control_proxy_cny_t"] = frame["china_gasoline_rule_proxy_cny_t"]
    frame["incremental_gasoline_gap_cny_t"] = frame["gasoline_policy_gap_cny_t"]
    frame["cumulative_gasoline_gap_cny_t"] = frame["cum_gasoline_policy_gap_cny_t"]
    frame["actual"] = frame["policy_adjusted_proxy_cny_t"]
    frame["prediction"] = frame["no_temporary_control_proxy_cny_t"]
    frame["response"] = frame["cumulative_gasoline_gap_cny_t"]
    frame["fuel_log_gap"] = np.log(frame["prediction"] / frame["actual"])
    frame["cpi_counterfactual_gap_pctpt"] = frame["fuel_log_gap"] * elasticity["cpi_cumulative_elasticity"]
    se = elasticity["cpi_elasticity_se"]
    frame["lower_95"] = frame["cpi_counterfactual_gap_pctpt"] - norm.ppf(0.975) * np.abs(frame["fuel_log_gap"]) * se
    frame["upper_95"] = frame["cpi_counterfactual_gap_pctpt"] + norm.ppf(0.975) * np.abs(frame["fuel_log_gap"]) * se
    frame["model"] = "China_policy_counterfactual"
    frame["horizon"] = 6
    frame["specification"] = "add cumulative NDRC gasoline policy gap back to Brent-CNY proxy; CPI propagation via China proxy fuel ARDL; descriptive proxy scenario only"
    frame["sample_start"] = "2010-01"
    frame["sample_end"] = "2026-06"
    result = frame[
        [
            "period",
            "actual",
            "prediction",
            "response",
            "policy_adjusted_proxy_cny_t",
            "no_temporary_control_proxy_cny_t",
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
            "sample_start",
            "sample_end",
        ]
    ]
    save_csv(result, "q3_policy_counterfactual.csv")
    return result


def robustness_checks(panel: pd.DataFrame, warnings_log: list[dict[str, Any]]) -> pd.DataFrame:
    from linearmodels.panel import PanelOLS

    rows: list[dict[str, Any]] = []
    main_panel = panel.loc[bool_series(panel["included_in_main_comparison"])].copy() if "included_in_main_comparison" in panel else panel.copy()
    main_countries = [country for country in COUNTRY_ORDER if country in set(main_panel["country"])]
    for omitted in main_countries:
        subset = main_panel.loc[main_panel["country"].ne(omitted)].copy()
        try:
            y, x, usable = panel_design(subset, "fuel", 6)
            if len(y) >= x.shape[1] + 20:
                fit = PanelOLS(y, x, entity_effects=True, drop_absorbed=True, check_rank=False).fit(
                    cov_type="kernel",
                    kernel="bartlett",
                    bandwidth=7,
                )
                for country in COUNTRY_ORDER:
                    term = f"oil_{country}"
                    if term in fit.params.index:
                        rows.append(
                            {
                                "robustness_type": "leave_one_country_panel_fuel_h6",
                                "omitted_country": omitted,
                                "country": country,
                                "horizon": 6,
                                "estimate": float(fit.params[term]),
                                "std_error": float(fit.std_errors[term]),
                                "model": "stacked_panel_LP",
                                "specification": "fuel h=6 panel LP after omitting one country",
                                "n": int(len(usable)),
                            }
                        )
        except Exception as exc:
            warnings_log.append({"code": "q3_leave_one_failed", "message": f"omit {omitted}: {exc}"})

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
    colors = [PALETTE["gold"], PALETTE["olive"], PALETTE["rose"]]
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    ax.bar(
        frame["country_label"],
        frame["response"],
        color=colors[: len(frame)],
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
        subtitle="仅纳入可观测官方零售汽油价格；中国 Brent-CNY 代理值不参与主排名。",
        source="来源：欧盟周度油价公报、日本METI、韩国KOSIS/KNOC 与 FRED；由 code/problem3/run_q3.py 生成。",
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
        "JPN": (PALETTE["olive"], (0, (2, 2)), "^"),
        "KOR": (PALETTE["rose"], (0, (1, 2)), "D"),
    }
    for country in COUNTRY_ORDER:
        sub = frame.loc[frame["country"].eq(country)].sort_values("horizon")
        if sub.empty:
            continue
        color, linestyle, marker = style_map[country]
        ax.plot(sub["horizon"], sub["response"], color=color, linestyle=linestyle, marker=marker, label=COUNTRY_LABEL_ZH.get(country, country))
    ax.axhline(0, color=PALETTE["muted"], linewidth=0.8)
    style_axis(ax, xlabel="油价冲击后月份", ylabel="响应")
    ax.legend(loc="upper left", ncol=4, handlelength=2.6)
    finish_figure(
        fig,
        title="问题三：跨国面板 LP 响应",
        subtitle="燃油价格对问题一约化形式 OilShock 的响应；燃油主图剔除中国代理值，标准误为 Driscoll-Kraay。",
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
    ax.plot(x, frame["actual"], marker="o", color=PALETTE["blue"], label="政策调整后代理路径")
    ax.plot(x, frame["prediction"], marker="s", color=PALETTE["gold"], linestyle=(0, (4, 2)), label="无临时调控规则代理路径")
    ax.fill_between(x, frame["actual"], frame["prediction"], color=PALETTE["gold_light"], alpha=0.26, linewidth=0)
    ax.set_xticks(x)
    ax.set_xticklabels(frame["period"])
    for tick, row in enumerate(frame.itertuples(index=False)):
        if getattr(row, "cumulative_gasoline_gap_cny_t") > 0:
            label = f"累计差额 {row.cumulative_gasoline_gap_cny_t:.0f}"
            if getattr(row, "incremental_gasoline_gap_cny_t") > 0 and row.period == "2026-04":
                label = f"累计差额 {row.cumulative_gasoline_gap_cny_t:.0f}\n4月新增 {row.incremental_gasoline_gap_cny_t:.0f}"
            ax.text(tick, max(row.actual, row.prediction), label, ha="center", va="bottom", fontsize=8.4, color=PALETTE["muted"])
    style_axis(ax, ylabel="元/吨代理值")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=2, handlelength=2.6)
    finish_figure(
        fig,
        title="问题三：中国成品油调控代理情景",
        subtitle="阴影代表累计政策差额；代理值只用于政策情景，不用于跨国主排名。",
        source="来源：Brent-CNY 代理值与国家发展改革委调价事件；由 code/problem3/run_q3.py 生成。",
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
    counterfactual = policy_counterfactual(panel, warnings_log)
    robustness = robustness_checks(panel, warnings_log)
    plot_pass_through(pass_through)
    plot_panel_irf(panel_irf)
    plot_policy(counterfactual)

    summary = pd.DataFrame(
        [
            {
                "component": "CountryPassThrough",
                "rows": len(pass_through),
                "status": "CONDITIONAL" if len(pass_through) else "WARN",
                "note": "main ranking excludes China proxy; distributed lag, 1/3/6 month cumulative response",
            },
            {
                "component": "PanelLP",
                "rows": len(panel_irf),
                "status": "CONDITIONAL" if len(panel_irf) else "WARN",
                "note": "fuel LP excludes China proxy from main comparison; country FE, month seasonality, country trend",
            },
            {
                "component": "ChinaPolicyCounterfactual",
                "rows": len(counterfactual),
                "status": "PASS" if len(counterfactual) else "WARN",
                "note": "price layer always reported; CPI propagation uses proxy fuel ARDL",
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
        "status": "CONDITIONAL",
        "random_seed": RANDOM_SEED,
        "comparability_guardrail": "China fuel proxy is excluded from the main cross-country fuel pass-through ranking; it remains a policy-scenario sensitivity input.",
        "warnings": warnings_log,
        "rows": {
            "q3_country_pass_through.csv": int(len(pass_through)),
            "q3_panel_irf.csv": int(len(panel_irf)),
            "q3_policy_counterfactual.csv": int(len(counterfactual)),
            "q3_robustness.csv": int(len(robustness)),
        },
    }
    (RESULTS_DIR / "q3_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
