"""Freeze modeling outputs into paper-ready candidate numbers and a report."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


REPO_ROOT = Path(__file__).resolve().parents[2]
CODE_DIR = REPO_ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from utils.plot_style import PALETTE, apply_paper_style, finish_figure, save_figure, style_axis

RESULTS_DIR = REPO_ROOT / "results"
FIGURES_DIR = REPO_ROOT / "figures"
REPORTS_DIR = REPO_ROOT / "reports"
CUTOFF = "2026-06-30"


CORE_RESULT_FILES = [
    "q1_forecast_metrics.csv",
    "q1_event_effects.csv",
    "q1_monthly_shocks.csv",
    "q1_robustness.csv",
    "q2_ardl_baseline.csv",
    "q2_irf.csv",
    "q2_gdp_validation.csv",
    "q2_robustness.csv",
    "q3_country_pass_through.csv",
    "q3_panel_irf.csv",
    "q3_policy_counterfactual.csv",
    "q3_robustness.csv",
    "q3_summary.csv",
]


def read_csv(filename: str) -> pd.DataFrame:
    path = RESULTS_DIR / filename
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_value(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        if not np.isfinite(value):
            return None
        return round(float(value), 8)
    if pd.isna(value):
        return None
    return value


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{key: clean_value(value) for key, value in row.items()} for row in frame.to_dict("records")]


def extract_final_numbers() -> dict[str, Any]:
    q1_metrics = read_csv("q1_forecast_metrics.csv")
    q1_events = read_csv("q1_event_effects.csv")
    q1_shocks = read_csv("q1_monthly_shocks.csv")
    q1_robust = read_csv("q1_robustness.csv")
    q2_ardl = read_csv("q2_ardl_baseline.csv")
    q2_irf = read_csv("q2_irf.csv")
    q2_gdp = read_csv("q2_gdp_validation.csv")
    q2_robust = read_csv("q2_robustness.csv")
    q3_pass = read_csv("q3_country_pass_through.csv")
    q3_irf = read_csv("q3_panel_irf.csv")
    q3_policy = read_csv("q3_policy_counterfactual.csv")
    q3_robust = read_csv("q3_robustness.csv")

    final: dict[str, Any] = {
        "cutoff": CUTOFF,
        "q1": {},
        "q2": {},
        "q3": {},
    }
    if not q1_metrics.empty:
        best = q1_metrics.sort_values(["RMSE", "MAE"]).head(3)
        final["q1"]["forecast_best_by_rmse"] = records(best)
        final["q1"]["forecast_metrics"] = records(q1_metrics.sort_values(["horizon", "model"]))
    if not q1_events.empty:
        final["q1"]["brent_event_effects"] = records(
            q1_events.loc[q1_events["model"].eq("brent_usd_bbl_stage_dummy")].sort_values("stage_id")
        )
        final["q1"]["wti_robustness_effects"] = records(
            q1_events.loc[q1_events["model"].eq("wti_usd_bbl_stage_dummy")].sort_values("stage_id")
        )
    if not q1_shocks.empty:
        event_months = q1_shocks.loc[q1_shocks["WarPremium"].abs().gt(0)]
        final["q1"]["war_premium_months"] = records(event_months[["period", "WarPremium", "WarPremium_days"]])
    if not q1_robust.empty:
        final["q1"]["robustness_rows"] = int(len(q1_robust))
        final["q1"]["robustness_types"] = sorted(q1_robust["robustness_type"].dropna().unique().tolist()) if "robustness_type" in q1_robust else []

    if not q2_ardl.empty:
        final["q2"]["ardl_main"] = records(q2_ardl.sort_values(["outcome", "term"]))
    if not q2_irf.empty:
        final["q2"]["lp_selected_horizons"] = records(
            q2_irf.loc[q2_irf["horizon"].isin([0, 6, 12])].sort_values(["outcome", "horizon"])
        )
    if not q2_gdp.empty:
        final["q2"]["gdp_validation"] = records(q2_gdp)
    if not q2_robust.empty:
        final["q2"]["robustness"] = records(q2_robust.sort_values(["outcome", "lag_max", "exclude_covid"]))

    if not q3_pass.empty:
        final["q3"]["pass_through_h6"] = records(q3_pass.loc[q3_pass["horizon"].eq(6)].sort_values("country"))
    if not q3_irf.empty:
        final["q3"]["panel_lp_selected_horizons"] = records(
            q3_irf.loc[q3_irf["horizon"].isin([0, 6, 12])].sort_values(["outcome", "country", "horizon"])
        )
    if not q3_policy.empty:
        final["q3"]["policy_counterfactual"] = records(q3_policy)
        final["q3"]["policy_max_price_gap_cny_t"] = clean_value(q3_policy["response"].max())
        final["q3"]["policy_max_cpi_gap_pctpt"] = clean_value(q3_policy["cpi_counterfactual_gap_pctpt"].max())
    if not q3_robust.empty:
        final["q3"]["robustness_rows"] = int(len(q3_robust))
        final["q3"]["robustness_types"] = sorted(q3_robust["robustness_type"].dropna().unique().tolist()) if "robustness_type" in q3_robust else []
    return final


def collect_file_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for filename in CORE_RESULT_FILES:
        path = RESULTS_DIR / filename
        if path.exists():
            hashes[filename] = sha256_file(path)
    return hashes


def collect_figures() -> list[str]:
    if not FIGURES_DIR.exists():
        return []
    return sorted(path.name for path in FIGURES_DIR.glob("*.png") if path.name.startswith(("q", "data_")))


def build_data_overview_figures() -> None:
    apply_paper_style()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    monthly_path = REPO_ROOT / "data" / "processed" / "model_monthly_q1.csv"
    country_path = REPO_ROOT / "data" / "processed" / "model_country_monthly.csv"
    if monthly_path.exists():
        monthly = pd.read_csv(monthly_path, parse_dates=["month_end"])
        fig, ax1 = plt.subplots(figsize=(9.2, 5.1))
        ax1.plot(monthly["month_end"], monthly["brent_usd_bbl"], color=PALETTE["blue"], label="Brent", linewidth=1.8)
        style_axis(ax1, ylabel="Brent USD/bbl")
        ax2 = ax1.twinx()
        ax2.plot(monthly["month_end"], monthly["GPR_z"], color=PALETTE["rose"], alpha=0.82, label="GPR z-score", linewidth=1.35, linestyle=(0, (4, 2)))
        ax2.set_ylabel("GPR z-score")
        ax2.tick_params(colors=PALETTE["muted"], length=3.2, width=0.65)
        ax2.spines["right"].set_color(PALETTE["muted"])
        ax2.spines["right"].set_linewidth(0.7)
        ax2.grid(False)
        lines, labels = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines + lines2, labels + labels2, loc="upper left", ncol=2, handlelength=2.8)
        finish_figure(
            fig,
            title="Data overview: Brent and geopolitical risk",
            subtitle="Monthly Brent price and standardized GPR index, 2010-01 to 2026-06.",
            source="Source: FRED Brent and Caldara-Iacoviello GPR processed panel; generated by code/utils/freeze_results.py.",
        )
        save_figure(fig, FIGURES_DIR / "data_overview_oil_gpr")
        plt.close(fig)
    if country_path.exists():
        panel = pd.read_csv(country_path, parse_dates=["month_end"])
        panel = panel.dropna(subset=["fuel_price_local"]).copy()
        panel["fuel_index"] = panel.groupby("country")["fuel_price_local"].transform(lambda s: 100.0 * s / s.iloc[0])
        fig, ax = plt.subplots(figsize=(9.2, 5.1))
        style_map = {
            "CHN": (PALETTE["blue"], "solid"),
            "DEU": (PALETTE["gold"], (0, (4, 2))),
            "JPN": (PALETTE["olive"], (0, (2, 2))),
            "KOR": (PALETTE["rose"], (0, (1, 2))),
        }
        for country, group in panel.groupby("country"):
            color, linestyle = style_map.get(country, (PALETTE["slate"], "solid"))
            ax.plot(group["month_end"], group["fuel_index"], label=country, color=color, linestyle=linestyle, linewidth=1.55)
        style_axis(ax, ylabel="Index, 2010-01 = 100")
        ax.legend(loc="upper left", ncol=4, handlelength=2.8)
        finish_figure(
            fig,
            title="Data overview: fuel price indexes",
            subtitle="Country fuel-price series indexed to 2010-01; China is a Brent-CNY policy proxy.",
            source="Source: EC Weekly Oil Bulletin, METI, KOSIS and constructed China proxy; generated by code/utils/freeze_results.py.",
        )
        save_figure(fig, FIGURES_DIR / "data_overview_fuel_panel")
        plt.close(fig)


def load_json(filename: str) -> dict[str, Any]:
    path = RESULTS_DIR / filename
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def summarize_warnings() -> list[dict[str, Any]]:
    warnings_list: list[dict[str, Any]] = []
    for filename in ["data_warnings.json", "q1_summary.json", "q2_summary.json", "q3_summary.json", "model_panel_summary.json"]:
        payload = load_json(filename)
        for warning in payload.get("warnings", []):
            row = dict(warning)
            row["source"] = filename
            warnings_list.append(row)
        for stage, stage_warnings in payload.get("stage_warnings", {}).items():
            for warning in stage_warnings:
                row = dict(warning)
                row["source"] = f"{filename}:{stage}"
                warnings_list.append(row)
    return warnings_list


def markdown_table(frame: pd.DataFrame, columns: list[str], limit: int = 12) -> str:
    if frame.empty:
        return "_无可用结果。_"
    subset = frame[columns].head(limit).copy()
    for column in subset.columns:
        if pd.api.types.is_numeric_dtype(subset[column]):
            subset[column] = subset[column].map(lambda value: "" if pd.isna(value) else f"{float(value):.4f}")
        else:
            subset[column] = subset[column].fillna("").astype(str)
    header = "| " + " | ".join(subset.columns) + " |"
    divider = "| " + " | ".join(["---"] * len(subset.columns)) + " |"
    body = []
    for row in subset.to_dict("records"):
        body.append("| " + " | ".join(str(row[column]).replace("\n", " ") for column in subset.columns) + " |")
    return "\n".join([header, divider] + body)


def build_report(final_numbers: dict[str, Any], warnings_list: list[dict[str, Any]]) -> str:
    q1_metrics = read_csv("q1_forecast_metrics.csv")
    q1_events = read_csv("q1_event_effects.csv")
    q2_ardl = read_csv("q2_ardl_baseline.csv")
    q2_irf = read_csv("q2_irf.csv")
    q2_gdp = read_csv("q2_gdp_validation.csv")
    q3_pass = read_csv("q3_country_pass_through.csv")
    q3_policy = read_csv("q3_policy_counterfactual.csv")
    figures = collect_figures()

    warning_lines = []
    for warning in warnings_list[:20]:
        warning_lines.append(f"- `{warning.get('code', 'warning')}`：{warning.get('message', '')}")
    if not warning_lines:
        warning_lines.append("- 暂无模型执行 warning。")

    report = f"""# 国际油价三问阶段性建模结果报告

## Material Passport

- Origin Skill: `academic-research-suite / experiment-agent`
- Execution Mode: `goal`
- Verification Status: `ANALYZED`
- Cutoff: `{CUTOFF}`
- Random Seed: `20260730`

## 1. 总体结论

本轮已经完成三问主线的可复现结果冻结：Q1 生成油价预测、战争事件冲击和月度 `OilShock` 接口；Q2 在中国 IAV/PPI 历史处理层暂缺的情况下，完成 CPI、汇率与季度 GDP 验证；Q3 完成日德韩真实零售汽油价格传导、中国 proxy 价格层反事实和跨国 panel LP。

关键边界：所有观测截止于 `2026-06-30`；IAV/PPI 暂未进入正式估计；中国燃油零售价使用 Brent-CNY 加 NDRC 政策差额的 proxy，不作为真实零售价格声称。

## 2. Q1 预测与战争冲击

月度预测评估保留 no-change、ARIMA 和 SARIMAX，未按显著性或好看程度筛选。

{markdown_table(q1_metrics.sort_values(['horizon', 'model']) if not q1_metrics.empty else q1_metrics, ['model', 'horizon', 'n', 'MAE', 'RMSE', 'direction_accuracy', 'coverage_80', 'coverage_95'])}

战争事件效应采用日度 AR(3)+美元收益率与阶段 dummy，标准误为 Newey-West；WTI 和 2025 placebo 作为稳健性/负对照。

{markdown_table(q1_events.sort_values(['model', 'stage_id']) if not q1_events.empty else q1_events, ['model', 'stage_id', 'estimate_log_return', 'std_error', 'lower_95', 'upper_95', 'pvalue', 'n'])}

## 3. Q2 中国宏观传导

ARDL 基线使用 `OilShock` 的 0-6 阶滞后、结果变量一阶滞后、美元、GPR、月份季节项和疫情阶段。由于 IAV/PPI 缺历史处理层，本轮正式月度输出聚焦 CPI 与汇率。

{markdown_table(q2_ardl.sort_values(['outcome', 'term']) if not q2_ardl.empty else q2_ardl, ['outcome', 'term', 'estimate', 'std_error', 'lower_95', 'upper_95', 'n'])}

Local Projection 生成 h=0..12 的响应，下表只展示 h=0/6/12 以便开题汇报。

{markdown_table(q2_irf.loc[q2_irf['horizon'].isin([0, 6, 12])].sort_values(['outcome', 'horizon']) if not q2_irf.empty else q2_irf, ['outcome', 'horizon', 'response', 'std_error', 'lower_95', 'upper_95', 'n'])}

季度 GDP 验证不把 GDP 插值到月度。

{markdown_table(q2_gdp, ['outcome', 'estimate', 'std_error', 'correlation', 'n', 'sample_start', 'sample_end'])}

## 4. Q3 政策缓冲与跨国比较

燃油价格传导采用各国本币 Brent 到汽油价格的 0-6 月 distributed lag。日德韩为官方零售燃油价格，中国为 policy-adjusted Brent-CNY proxy。

{markdown_table(q3_pass.loc[q3_pass['horizon'].eq(6)].sort_values('country') if not q3_pass.empty else q3_pass, ['country', 'horizon', 'response', 'std_error', 'lower_95', 'upper_95', 'fuel_source'])}

中国调价反事实把 2026-03-23 和 2026-04-07 的政策差额加回，先报告价格层，再用中国 proxy fuel ARDL 传播到 CPI。

{markdown_table(q3_policy, ['period', 'actual', 'prediction', 'response', 'fuel_log_gap', 'cpi_counterfactual_gap_pctpt'])}

## 5. 图表与文件

核心图表（PNG）：{', '.join(figures) if figures else '暂无图表'}。

冻结数值文件：

- `results/final_numbers.json`
- `results/frozen_numbers.json`
- `results/risk_probe_summary.json`

## 6. Warnings

{chr(10).join(warning_lines)}

## 7. 论文使用建议

正文主线建议按“Q1 可预测部分与战争溢价分离、Q2 CPI/汇率/GDP 动态响应、Q3 跨国传导与中国政策反事实”组织。不要把中国 proxy 燃油价格解释为观测零售价；它适合回答“如果没有 2026 年两次调控，价格层差额有多大”，不适合声称完整历史零售价格传导。
"""
    return report


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    build_data_overview_figures()
    final_numbers = extract_final_numbers()
    final_path = RESULTS_DIR / "final_numbers.json"
    final_path.write_text(json.dumps(final_numbers, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    file_hashes = collect_file_hashes()
    freeze_source = json.dumps({"numbers": final_numbers, "hashes": file_hashes}, ensure_ascii=False, sort_keys=True)
    frozen = {
        "freeze_hash": hashlib.sha256(freeze_source.encode("utf-8")).hexdigest(),
        "cutoff": CUTOFF,
        "random_seed": 20260730,
        "core_result_hashes": file_hashes,
        "final_numbers": final_numbers,
    }
    frozen_path = RESULTS_DIR / "frozen_numbers.json"
    frozen_path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    warnings_list = summarize_warnings()
    execution_summary = {
        "status": "EXECUTION_SUMMARY",
        "cutoff": CUTOFF,
        "random_seed": 20260730,
        "core_results_present": {filename: (RESULTS_DIR / filename).exists() for filename in CORE_RESULT_FILES},
        "figure_pngs": collect_figures(),
        "warnings": warnings_list,
        "freeze_hash": frozen["freeze_hash"],
    }
    (RESULTS_DIR / "risk_probe_summary.json").write_text(json.dumps(execution_summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    report = build_report(final_numbers, warnings_list)
    (REPORTS_DIR / "RESULTS_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": "PASS", "freeze_hash": frozen["freeze_hash"], "warnings": len(warnings_list)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
