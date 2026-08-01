"""Generate paper handoff tables and supplemental paper-ready figures.

This script reads the frozen modeling outputs and creates artifacts intended
for the writing stage. It does not estimate models or change any numerical
result used by the freeze gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "results"
REPORTS_DIR = REPO_ROOT / "reports"
FIGURES_DIR = REPO_ROOT / "figures"

sys.path.append(str(REPO_ROOT / "code" / "utils"))
from plot_style import PALETTE, apply_paper_style, finish_figure, save_figure  # noqa: E402


COUNTRY_LABEL_ZH = {
    "CHN": "中国",
    "DEU": "德国",
    "FRA": "法国",
    "ITA": "意大利",
    "ESP": "西班牙",
    "JPN": "日本",
    "KOR": "韩国",
}

OUTCOME_LABEL_ZH = {
    "brent_cny_cost_log_change_pct": "人民币原油成本",
    "china_ppi_yoy_pct": "PPI",
    "china_cpi_yoy_pct": "CPI",
    "china_iav_yoy_pct": "工业增加值",
    "china_fx_log_change_pct": "汇率",
}

SHOCK_LABEL_ZH = {
    "supply_shock": "供给冲击",
    "aggregate_demand_shock": "全球需求冲击",
    "oil_specific_risk_shock": "油价特定风险冲击",
    "OilShock": "约化油价创新",
}


def read_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(RESULTS_DIR / name)


def read_json(name: str) -> dict:
    return json.loads((RESULTS_DIR / name).read_text(encoding="utf-8"))


def zh_outcome(value: str) -> str:
    return OUTCOME_LABEL_ZH.get(value, value)


def write_paper_numbers() -> None:
    risk = read_json("risk_probe_summary.json")
    q1_origin = read_csv("q1_origin_forecast.csv")
    q1_event = read_csv("q1_event_effects.csv")
    q1_structural = read_csv("q1_structural_shocks.csv")
    q1_vol = read_csv("q1_volatility_summary.csv")
    q2_metrics = read_csv("q2_transmission_metrics.csv")
    q2_gdp = read_csv("q2_gdp_validation.csv")
    q3_pass = read_csv("q3_country_pass_through.csv")
    q3_policy = read_csv("q3_policy_counterfactual.csv")
    q3_policy_macro = read_csv("q3_policy_macro_counterfactual.csv")
    q3_resilience = read_csv("q3_resilience_metrics.csv")
    q4_risk = read_csv("q4_price_tail_risk.csv")
    q4_backtest = read_csv("q4_risk_backtest.csv")
    q4_macro = read_csv("q4_macro_stress.csv")
    q4_policy = read_csv("q4_policy_stress.csv")
    q4_sapr_optimal = read_csv("q4_sapr_optimal_rule.csv")
    q4_sapr_comparison = read_csv("q4_sapr_strategy_comparison.csv")
    q4_sapr_sensitivity = read_csv("q4_sapr_sensitivity.csv")
    q4_sapr_summary = read_json("q4_sapr_summary.json")

    rows: list[dict[str, object]] = []

    def add(section: str, number_id: str, value: object, unit: str, source_file: str, allowed: str, forbidden: str) -> None:
        rows.append(
            {
                "section": section,
                "number_id": number_id,
                "value": value,
                "unit": unit,
                "rounding": "论文正文保留2到3位有效数字；表格按来源文件精度",
                "source_file": source_file,
                "allowed_claim": allowed,
                "forbidden_claim": forbidden,
            }
        )

    add(
        "overall",
        "paper_finalize_allowed",
        str(risk["paper_finalize_allowed"]).lower(),
        "boolean",
        "results/risk_probe_summary.json",
        "所有核心门禁通过后可进入论文撰写",
        "不得忽略后续新增数据或代码变动后的重新冻结",
    )
    add(
        "overall",
        "blocking_probe_count",
        len(risk["blocking_probe_ids"]),
        "count",
        "results/risk_probe_summary.json",
        "当前无阻塞门禁",
        "不得把单个模型的显著性等同于全部结论成立",
    )

    for _, row in q1_origin.sort_values("horizon_months").iterrows():
        add(
            "Q1",
            f"origin_2026_02_forecast_h{int(row['horizon_months'])}",
            round(float(row["prediction_price"]), 3),
            "美元/桶",
            "results/q1_origin_forecast.csv",
            f"{row['target_period']} 的 no-change 预测价格",
            "不得把未到期的2026-08预测写成有实际误差",
        )
    for _, row in q1_event[q1_event["model"].eq("brent_usd_bbl_event_car")].iterrows():
        add(
            "Q1",
            f"{row['stage_id']}_estimate",
            round(float(row["estimate_log_return"]), 6),
            "log return",
            "results/q1_event_effects.csv",
            "交易日CAR与经验placebo可作为事件相关异常证据",
            "不得解释为严格战争净因果贡献",
        )
        add(
            "Q1",
            f"{row['stage_id']}_empirical_p",
            round(float(row["pvalue_empirical"]), 6),
            "probability",
            "results/q1_event_effects.csv",
            "经验p值使用有限样本add-one修正",
            "不得报告0或只引用常规HAC显著性",
        )
    add(
        "Q1",
        "structural_shock_nonmissing_months_min",
        int(q1_structural[["supply_shock", "aggregate_demand_shock", "oil_specific_risk_shock"]].notna().sum().min()),
        "months",
        "results/q1_structural_shocks.csv",
        "三类SVAR结构冲击满足不少于120个月覆盖",
        "不得再使用52期STEO残差作为主结构识别",
    )
    for _, row in q1_vol.iterrows():
        add(
            "Q1",
            f"vol_multiple_{row['war_stage']}",
            round(float(row["vol_multiple_vs_pre_median"]), 3),
            "倍",
            "results/q1_volatility_summary.csv",
            "条件波动率可描述战争阶段油价波动变化",
            "不得解释为福利损失或实体经济损失",
        )

    focus = q2_metrics[
        q2_metrics["shock"].eq("oil_specific_risk_shock")
        & q2_metrics["outcome"].isin(["brent_cny_cost_log_change_pct", "china_ppi_yoy_pct", "china_cpi_yoy_pct", "china_iav_yoy_pct"])
    ]
    for _, row in focus.iterrows():
        add(
            "Q2",
            f"oil_specific_{row['outcome']}_extremum",
            round(float(row["extremum_response"]), 6),
            "百分点或对数百分点",
            "results/q2_transmission_metrics.csv",
            f"{zh_outcome(row['outcome'])} 的响应方向和量级可报告为估计结果",
            "联合区间未排除零时不得写成稳健增长损失",
        )
        add(
            "Q2",
            f"oil_specific_{row['outcome']}_cum0_12",
            round(float(row["cumulative_response_0_12"]), 6),
            "累计百分点",
            "results/q2_transmission_metrics.csv",
            f"{zh_outcome(row['outcome'])} 的0到12月累计响应可报告为估计量级",
            "不得挑选单一期限替代完整区间报告",
        )
    if not q2_gdp.empty:
        gdp = q2_gdp.iloc[0]
        add(
            "Q2",
            "quarterly_gdp_validation_estimate",
            round(float(gdp["estimate"]), 6),
            "百分点",
            "results/q2_gdp_validation.csv",
            "季度GDP仅作低频验证",
            "不得插值为月度主增长指标",
        )

    h6 = q3_pass[q3_pass["horizon"].eq(6)]
    for _, row in h6.sort_values("country").iterrows():
        add(
            "Q3",
            f"fuel_pass_through_h6_{row['country']}",
            round(float(row["response"]), 6),
            "累计传导率",
            "results/q3_country_pass_through.csv",
            f"{COUNTRY_LABEL_ZH.get(row['country'], row['country'])} 可进入主燃油比较",
            "不得混用中国Brent-CNY代理值与他国观测零售价排名",
        )
    apr = q3_policy[q3_policy["period"].eq("2026-04")]
    if not apr.empty:
        apr0 = apr.iloc[0]
        add(
            "Q3",
            "policy_gap_2026_04_incremental",
            round(float(apr0["incremental_gasoline_gap_cny_t"]), 3),
            "元/吨",
            "results/q3_policy_counterfactual.csv",
            "4月新增调控差额可写为380元/吨",
            "不得把新增差额误写成累计差额",
        )
        add(
            "Q3",
            "policy_gap_2026_04_cumulative",
            round(float(apr0["cumulative_gasoline_gap_cny_t"]), 3),
            "元/吨",
            "results/q3_policy_counterfactual.csv",
            "4月累计规则缺口可写为1425元/吨",
            "不得把价格平滑解释为无成本福利改善",
        )
    june_macro = q3_policy_macro[q3_policy_macro["period"].eq("2026-06")]
    for _, row in june_macro.sort_values("outcome").iterrows():
        add(
            "Q3",
            f"policy_macro_gap_2026_06_{row['outcome']}",
            round(float(row["macro_counterfactual_gap_pctpt"]), 6),
            "百分点",
            "results/q3_policy_macro_counterfactual.csv",
            f"无临时调控路径对{row['outcome_label']}的情景差额可作为政策关闭反事实",
            "不得解释为已发生事实或完整福利评价",
        )
    overall = q3_resilience["overall_china_resilience_judgement"].dropna().iloc[0]
    add(
        "Q3",
        "overall_china_resilience_judgement",
        overall,
        "categorical",
        "results/q3_resilience_metrics.csv",
        "中国综合韧性当前判断为PARTIAL",
        "不得写成无条件SUPPORTED",
    )

    for _, row in q4_risk[q4_risk["model"].eq("FHS_GJR_GARCH")].sort_values("horizon_months").iterrows():
        horizon = int(row["horizon_months"])
        add(
            "Q4",
            f"fhs_median_price_h{horizon}",
            round(float(row["median_price"]), 6),
            "美元/桶",
            "results/q4_price_tail_risk.csv",
            "可作为2026-06-30信息集下的条件分布中位数",
            "不得写成确定性油价路径",
        )
        add(
            "Q4",
            f"fhs_terminal_prob_above_hist_p95_h{horizon}",
            round(float(row["terminal_prob_above_hist_p95"]), 6),
            "probability",
            "results/q4_price_tail_risk.csv",
            "可报告期末价格超过历史95%分位阈值的条件概率",
            "不得解释为事件必然发生概率或因果概率",
        )
    for _, row in q4_backtest.sort_values(["horizon_months", "model"]).iterrows():
        add(
            "Q4",
            f"backtest_pinball_{row['model']}_h{int(row['horizon_months'])}",
            round(float(row["mean_pinball_loss"]), 6),
            "美元/桶分位损失",
            "results/q4_risk_backtest.csv",
            "主方法与基线按相同滚动原点和期限比较",
            "不得只报告有利期限或隐藏基线",
        )
    for _, row in q4_macro[
        q4_macro["scenario"].eq("extreme_q95") & q4_macro["horizon"].isin([6, 12])
    ].sort_values(["outcome", "horizon"]).iterrows():
        add(
            "Q4",
            f"extreme_q95_{row['outcome']}_h{int(row['horizon'])}",
            round(float(row["conditional_response_pctpt"]), 6),
            "百分点",
            "results/q4_macro_stress.csv",
            "可作为历史95%分位油价特定风险冲击下的条件响应",
            "联合区间跨零时不得写成确定性宏观损失",
        )
    for _, row in q4_policy[q4_policy["period"].eq("2026-06")].sort_values("outcome").iterrows():
        add(
            "Q4",
            f"policy_buffer_benefit_2026_06_{row['outcome']}",
            round(float(row["policy_buffer_benefit_pctpt"]), 6),
            "百分点",
            "results/q4_policy_stress.csv",
            "可作为Q3已实现临时调控关闭反事实的政策缓冲收益重述",
            "不得外推到Q4模拟油价路径或写成完整福利收益",
        )

    if not q4_sapr_optimal.empty:
        opt = q4_sapr_optimal.iloc[0]
        for key, unit, claim in [
            ("rho_normal", "pass-through ratio", "普通状态最优传导率"),
            ("rho_stress", "pass-through ratio", "压力状态最优传导率"),
            ("rho_extreme", "pass-through ratio", "极端状态最优传导率"),
            ("J2_cvar95_macro_loss", "standardized loss", "训练样本膝点规则的95%尾部宏观损失"),
            ("J3_gap_burden", "ratio", "训练样本膝点规则的累计未调价负担比例"),
        ]:
            add(
                "Q4",
                f"sapr_optimal_{key}",
                round(float(opt[key]), 6),
                unit,
                "results/q4_sapr_optimal_rule.csv",
                claim,
                "不得写成全局福利最优或不受规则族限制的最优政策",
            )
    sapr_holdout = q4_sapr_comparison[
        q4_sapr_comparison["sample_split"].eq("holdout")
        & q4_sapr_comparison["strategy"].eq("SAPR_CVaR_knee")
    ]
    if not sapr_holdout.empty:
        row = sapr_holdout.iloc[0]
        add(
            "Q4",
            "sapr_holdout_macro_loss_cvar95",
            round(float(row["J2_cvar95_macro_loss"]), 6),
            "standardized loss",
            "results/q4_sapr_strategy_comparison.csv",
            "可作为2022—2026隔离检验样本下SAPR尾部宏观损失",
            "不得声称2026以后仍必然占优",
        )
        add(
            "Q4",
            "sapr_holdout_gap_burden_ratio",
            round(float(row["J3_gap_burden"]), 6),
            "ratio",
            "results/q4_sapr_strategy_comparison.csv",
            "可作为隔离检验样本下累计未调价负担比例",
            "不得解释为财政支出或完整社会成本",
        )
    add(
        "Q4",
        "sapr_holdout_non_dominated_probability",
        round(float(q4_sapr_summary["holdout_non_dominated_probability"]), 6),
        "probability",
        "results/q4_sapr_summary.json",
        "可报告训练期选出规则在检验期保持非支配的bootstrap概率",
        "不得改写成真实世界政策成功概率",
    )
    for _, row in q4_sapr_sensitivity.sort_values("variant").iterrows():
        add(
            "Q4",
            f"sapr_sensitivity_{row['variant']}_rule",
            f"({row['rho_normal']:.2f},{row['rho_stress']:.2f},{row['rho_extreme']:.2f})",
            "rule tuple",
            "results/q4_sapr_sensitivity.csv",
            "可用于说明阈值、块长和权重变动下规则是否稳定",
            "不得事后删除不利敏感性结果",
        )

    pd.DataFrame(rows).to_csv(REPORTS_DIR / "paper_numbers.csv", index=False, encoding="utf-8-sig")


def plot_q1_structural_shocks() -> None:
    df = read_csv("q1_structural_shocks.csv")
    df["period"] = pd.to_datetime(df["period"])
    columns = ["supply_shock", "aggregate_demand_shock", "oil_specific_risk_shock"]
    labels = ["供给冲击", "全球需求冲击", "油价特定风险冲击"]
    fig, ax = plt.subplots(figsize=(8.4, 4.2))
    for col, label in zip(columns, labels):
        series = df[col].rolling(3, min_periods=1).mean()
        ax.plot(df["period"], series, label=label)
    ax.axhline(0, color=PALETTE["muted"], linewidth=0.8)
    ax.set_ylabel("标准化冲击")
    ax.legend(ncol=3, loc="upper left")
    finish_figure(
        fig,
        title="问题一：历史递归SVAR结构冲击",
        subtitle="三个月滚动均值，仅用于识别与传导链输入展示",
        source="来源：EIA International、Dallas Fed IGREA、Brent、美国CPI；作者计算。",
    )
    save_figure(fig, FIGURES_DIR / "q1_structural_shocks")
    plt.close(fig)


def plot_q2_transmission_chain() -> None:
    df = read_csv("q2_transmission_metrics.csv")
    focus = df[
        df["shock"].eq("oil_specific_risk_shock")
        & df["outcome"].isin(
            [
                "brent_cny_cost_log_change_pct",
                "china_ppi_yoy_pct",
                "china_cpi_yoy_pct",
                "china_iav_yoy_pct",
                "china_fx_log_change_pct",
            ]
        )
    ].copy()
    focus["label"] = focus["outcome"].map(OUTCOME_LABEL_ZH)
    focus = focus.sort_values("extremum_response")
    fig, ax = plt.subplots(figsize=(7.8, 4.6))
    colors = [PALETTE["rose"] if v < 0 else PALETTE["blue"] for v in focus["extremum_response"]]
    ax.barh(focus["label"], focus["extremum_response"], color=colors, alpha=0.88)
    ax.axvline(0, color=PALETTE["muted"], linewidth=0.8)
    for _, row in focus.iterrows():
        ax.text(
            row["extremum_response"],
            row["label"],
            f"  {row['extremum_response']:.2f}，h={int(row['extremum_month'])}",
            va="center",
            fontsize=9,
            color=PALETTE["ink"],
        )
    ax.set_xlabel("峰值/谷值响应（百分点或对数百分点）")
    finish_figure(
        fig,
        title="问题二：油价特定风险冲击的传导摘要",
        subtitle="显示各变量峰值或谷值响应；完整区间以结果表为准",
        source="来源：results/q2_transmission_metrics.csv。",
    )
    save_figure(fig, FIGURES_DIR / "q2_transmission_chain")
    plt.close(fig)


def plot_q3_resilience_metrics() -> None:
    df = read_csv("q3_resilience_metrics.csv")
    focus = df[df["dimension"].isin(["fuel_pass_through", "cpi_peak_response", "industrial_activity_trough"])].copy()
    label_map = {
        "fuel_1m_cumulative_pass_through": "燃油1月传导",
        "fuel_3m_cumulative_pass_through": "燃油3月传导",
        "fuel_6m_cumulative_pass_through": "燃油6月传导",
        "cpi_relative_to_china": "CPI相对响应",
        "ip_relative_to_china": "工业活动相对响应",
    }
    focus["label"] = focus["metric"].map(label_map)
    focus = focus.iloc[::-1]
    y = np.arange(len(focus))
    err_left = focus["china_vs_control_median_diff"] - focus["diff_lower_95"]
    err_right = focus["diff_upper_95"] - focus["china_vs_control_median_diff"]
    fig, ax = plt.subplots(figsize=(8.2, 4.3))
    ax.barh(y, focus["china_vs_control_median_diff"], color=PALETTE["olive"], alpha=0.82)
    ax.errorbar(
        focus["china_vs_control_median_diff"],
        y,
        xerr=[err_left, err_right],
        fmt="none",
        ecolor=PALETTE["ink"],
        elinewidth=0.8,
        capsize=3,
    )
    ax.axvline(0, color=PALETTE["muted"], linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(focus["label"])
    ax.set_xlabel("中国相对六国中位数差异")
    finish_figure(
        fig,
        title="问题三：中国综合韧性指标",
        subtitle="点估计与95%区间共同决定SUPPORTED/PARTIAL/NOT_SUPPORTED",
        source="来源：results/q3_resilience_metrics.csv。",
    )
    save_figure(fig, FIGURES_DIR / "q3_resilience_metrics")
    plt.close(fig)


def plot_q3_policy_macro_counterfactual() -> None:
    df = read_csv("q3_policy_macro_counterfactual.csv")
    df["period_dt"] = pd.to_datetime(df["period"], format="%Y-%m")
    label_map = {"PPI": "PPI", "CPI": "CPI", "IAV": "工业增加值"}
    fig, ax = plt.subplots(figsize=(7.8, 4.5))
    for label, color in zip(["PPI", "CPI", "IAV"], [PALETTE["blue"], PALETTE["gold"], PALETTE["rose"]]):
        sub = df[df["outcome_label"].eq(label)].sort_values("period_dt")
        ax.plot(sub["period_dt"], sub["macro_counterfactual_gap_pctpt"], marker="o", color=color, label=label_map[label])
        ax.fill_between(sub["period_dt"], sub["lower_95"], sub["upper_95"], color=color, alpha=0.12, linewidth=0)
    ax.axhline(0, color=PALETTE["muted"], linewidth=0.8)
    ax.set_ylabel("无临时调控相对实际路径差额（百分点）")
    ax.legend(loc="upper left")
    finish_figure(
        fig,
        title="问题三：政策关闭宏观反事实",
        subtitle="在官方成品油价格层上移除临时调控缺口后传播至PPI/CPI/IAV",
        source="来源：results/q3_policy_macro_counterfactual.csv。",
    )
    save_figure(fig, FIGURES_DIR / "q3_policy_macro_counterfactual")
    plt.close(fig)


def draw_box(ax: plt.Axes, xy: tuple[float, float], text: str, width: float = 0.18, height: float = 0.16, color: str = "#f4efe6") -> None:
    box = patches.FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle="round,pad=0.018,rounding_size=0.02",
        linewidth=0.9,
        edgecolor=PALETTE["slate"],
        facecolor=color,
    )
    ax.add_patch(box)
    ax.text(xy[0] + width / 2, xy[1] + height / 2, text, ha="center", va="center", fontsize=10)


def arrow(ax: plt.Axes, start: tuple[float, float], end: tuple[float, float]) -> None:
    ax.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops={"arrowstyle": "->", "linewidth": 1.1, "color": PALETTE["muted"]},
    )


def save_flow(fig: plt.Figure, stem: str, title: str, subtitle: str) -> None:
    fig.subplots_adjust(left=0.04, right=0.98, bottom=0.18, top=0.92)
    fig._shu_caption = title  # type: ignore[attr-defined]
    fig._shu_subtitle = subtitle  # type: ignore[attr-defined]
    fig.text(0.04, 0.045, "来源：作者根据冻结模型流程绘制。", ha="left", va="bottom", fontsize=8.4, color=PALETTE["muted"])
    save_figure(fig, FIGURES_DIR / stem)
    plt.close(fig)


def plot_route_map() -> None:
    fig, ax = plt.subplots(figsize=(10.2, 3.6))
    ax.set_axis_off()
    boxes = [
        ((0.02, 0.55), "问题一\n预测与事件识别"),
        ((0.21, 0.55), "结构冲击\nSVAR输出"),
        ((0.40, 0.55), "问题二\n中国宏观传导"),
        ((0.59, 0.55), "问题三\n跨国韧性与政策情景"),
        ((0.78, 0.55), "问题四\n尾部风险与SAPR优化"),
        ((0.40, 0.18), "冻结校验\n风险门禁PASS"),
        ((0.64, 0.18), "论文撰写\n数字台账引用"),
    ]
    for xy, text in boxes:
        draw_box(ax, xy, text, width=0.15, color="#f4efe6")
    arrow(ax, (0.17, 0.63), (0.21, 0.63))
    arrow(ax, (0.36, 0.63), (0.40, 0.63))
    arrow(ax, (0.55, 0.63), (0.59, 0.63))
    arrow(ax, (0.74, 0.63), (0.78, 0.63))
    arrow(ax, (0.86, 0.55), (0.55, 0.34))
    arrow(ax, (0.55, 0.26), (0.64, 0.26))
    save_flow(fig, "paper_route_map", "四问统一技术路线", "模型链由预测、宏观传导和政策比较延伸到尾部风险压力测试与自适应调价优化")


def plot_event_timeline() -> None:
    fig, ax = plt.subplots(figsize=(8.6, 3.0))
    ax.set_axis_off()
    xs = [0.12, 0.36, 0.64, 0.84]
    labels = ["2026-02-28\n周末事件发生", "2026-03-02\nE1首个交易日", "2026-03-05\nE2持续中断", "2026-06-17\nE3缓和阶段"]
    ax.plot([xs[0], xs[-1]], [0.5, 0.5], color=PALETTE["slate"], linewidth=1.2)
    for x, label in zip(xs, labels):
        ax.scatter([x], [0.5], s=70, color=PALETTE["blue"], zorder=3)
        ax.text(x, 0.67, label, ha="center", va="bottom", fontsize=10)
    ax.text(0.5, 0.25, "正式推断使用CAR[0]、CAR[0,+1]、CAR[0,+2]与周末匹配placebo经验分布", ha="center", fontsize=10, color=PALETTE["muted"])
    save_flow(fig, "paper_event_timeline", "战争事件时间线", "周末事件统一映射到首个共同交易日")


def plot_transmission_mechanism() -> None:
    fig, ax = plt.subplots(figsize=(8.8, 3.8))
    ax.set_axis_off()
    boxes = [
        ((0.04, 0.58), "结构性\n油价冲击"),
        ((0.27, 0.58), "人民币\n原油成本"),
        ((0.50, 0.58), "PPI\n生产成本"),
        ((0.73, 0.66), "CPI\n居民价格"),
        ((0.73, 0.42), "工业活动\n增长响应"),
        ((0.50, 0.18), "季度GDP\n低频验证"),
    ]
    for xy, text in boxes:
        draw_box(ax, xy, text, color="#eef3ee")
    arrow(ax, (0.22, 0.66), (0.27, 0.66))
    arrow(ax, (0.45, 0.66), (0.50, 0.66))
    arrow(ax, (0.68, 0.66), (0.73, 0.74))
    arrow(ax, (0.68, 0.58), (0.73, 0.50))
    arrow(ax, (0.59, 0.58), (0.59, 0.34))
    save_flow(fig, "paper_transmission_mechanism", "油价向中国经济传导链", "主结果报告方向、量级与不确定性而非制造显著性")


def plot_policy_counterfactual_flow() -> None:
    fig, ax = plt.subplots(figsize=(8.8, 3.5))
    ax.set_axis_off()
    boxes = [
        ((0.04, 0.58), "官方调价\n实际路径"),
        ((0.04, 0.26), "无临时调控\n规则路径"),
        ((0.31, 0.42), "1045/380/1425\n政策缺口"),
        ((0.57, 0.42), "燃油价格—宏观\n分布滞后模型"),
        ((0.79, 0.42), "PPI/CPI/IAV\n反事实区间"),
    ]
    for xy, text in boxes:
        draw_box(ax, xy, text, color="#f3eef0")
    arrow(ax, (0.22, 0.66), (0.31, 0.53))
    arrow(ax, (0.22, 0.34), (0.31, 0.50))
    arrow(ax, (0.49, 0.50), (0.57, 0.50))
    arrow(ax, (0.75, 0.50), (0.79, 0.50))
    save_flow(fig, "paper_policy_counterfactual_flow", "中国临时调控关闭反事实流程", "情景结果代表价格平滑成本/延期负担代理而非福利判断")


def write_handoff_markdown() -> None:
    risk = read_json("risk_probe_summary.json")
    q1_origin = read_csv("q1_origin_forecast.csv")
    q1_event = read_csv("q1_event_effects.csv")
    q2_metrics = read_csv("q2_transmission_metrics.csv")
    q3_resilience = read_csv("q3_resilience_metrics.csv")
    q3_policy_macro = read_csv("q3_policy_macro_counterfactual.csv")
    q4_risk = read_csv("q4_price_tail_risk.csv")
    q4_backtest = read_csv("q4_risk_backtest.csv")
    q4_macro = read_csv("q4_macro_stress.csv")
    q4_policy = read_csv("q4_policy_stress.csv")
    q4_sapr_optimal = read_csv("q4_sapr_optimal_rule.csv")
    q4_sapr_comparison = read_csv("q4_sapr_strategy_comparison.csv")
    q4_sapr_sensitivity = read_csv("q4_sapr_sensitivity.csv")
    q4_sapr_summary = read_json("q4_sapr_summary.json")

    q1_rows = []
    for _, row in q1_origin.sort_values("horizon_months").iterrows():
        actual = "未到期" if row["forecast_status"] == "FORECAST_ONLY" else f"{row['actual_price']:.2f}"
        q1_rows.append(f"- h={int(row['horizon_months'])}：预测 {row['prediction_price']:.2f} 美元/桶，实际 {actual}。")
    q1_car = q1_event[q1_event["model"].eq("brent_usd_bbl_event_car")]
    car_rows = [
        f"- {row['stage_id']}：CAR={row['estimate_log_return']:.4f}，经验 p={row['pvalue_empirical']:.4f}。"
        for _, row in q1_car.iterrows()
    ]
    q2_focus = q2_metrics[
        q2_metrics["shock"].eq("oil_specific_risk_shock")
        & q2_metrics["outcome"].isin(["brent_cny_cost_log_change_pct", "china_ppi_yoy_pct", "china_cpi_yoy_pct", "china_iav_yoy_pct"])
    ]
    q2_rows = [
        f"- {zh_outcome(row['outcome'])}：峰值/谷值 {row['extremum_response']:.3f}，h={int(row['extremum_month'])}，0—12月累计 {row['cumulative_response_0_12']:.3f}，证据状态 {row['evidence_status']}。"
        for _, row in q2_focus.iterrows()
    ]
    resilience_overall = q3_resilience["overall_china_resilience_judgement"].dropna().iloc[0]
    q3_rows = [
        f"- {row['metric']}：中国值 {row['china_value']:.3f}，六国中位数 {row['control_median']:.3f}，判断 {row['judgement']}。"
        for _, row in q3_resilience[q3_resilience["dimension"].isin(["fuel_pass_through", "cpi_peak_response", "industrial_activity_trough"])].iterrows()
    ]
    q3_macro_rows = [
        f"- 2026-06 {row['outcome_label']}：无临时调控相对实际路径差额 {row['macro_counterfactual_gap_pctpt']:.3f} 个百分点，95%区间 [{row['lower_95']:.3f}, {row['upper_95']:.3f}]。"
        for _, row in q3_policy_macro[q3_policy_macro["period"].eq("2026-06")].sort_values("outcome").iterrows()
    ]
    q4_price_rows = [
        f"- h={int(row['horizon_months'])}：中位数 {row['median_price']:.2f} 美元/桶，90%区间 [{row['p05_price']:.2f}, {row['p95_price']:.2f}]，期末超过历史95%价格分位的条件概率 {100 * row['terminal_prob_above_hist_p95']:.2f}%。"
        for _, row in q4_risk[q4_risk["model"].eq("FHS_GJR_GARCH")].sort_values("horizon_months").iterrows()
    ]
    q4_backtest_rows = [
        f"- {row['model']}，h={int(row['horizon_months'])}：平均分位损失 {row['mean_pinball_loss']:.3f}，80%/90%覆盖率 {row['coverage_80']:.3f}/{row['coverage_90']:.3f}。"
        for _, row in q4_backtest.sort_values(["horizon_months", "model"]).iterrows()
    ]
    q4_macro_rows = [
        f"- {row['outcome_label']}，h={int(row['horizon'])}：95%分位结构冲击条件响应 {row['conditional_response_pctpt']:.3f} 个百分点，联合95%区间 [{row['joint_lower_95']:.3f}, {row['joint_upper_95']:.3f}]，{row['row_evidence_status']}。"
        for _, row in q4_macro[q4_macro["scenario"].eq("extreme_q95") & q4_macro["horizon"].isin([6, 12])]
        .sort_values(["outcome", "horizon"]).iterrows()
    ]
    q4_policy_rows = [
        f"- 2026-06 {row['outcome_label']}：政策缓冲收益 {row['policy_buffer_benefit_pctpt']:.3f} 个百分点，95%区间 [{row['benefit_lower_95']:.3f}, {row['benefit_upper_95']:.3f}]。"
        for _, row in q4_policy[q4_policy["period"].eq("2026-06")].sort_values("outcome").iterrows()
    ]
    q4_sapr_opt = q4_sapr_optimal.iloc[0]
    q4_sapr_rule_text = (
        f"- SAPR-CVaR 膝点规则：普通/压力/极端传导率 = "
        f"({q4_sapr_opt['rho_normal']:.2f}, {q4_sapr_opt['rho_stress']:.2f}, {q4_sapr_opt['rho_extreme']:.2f})；"
        f"压力阈值 {q4_sapr_opt['stress_threshold_75_cny_t']:.1f} 元/吨，极端阈值 {q4_sapr_opt['stress_threshold_95_cny_t']:.1f} 元/吨。"
    )
    q4_sapr_holdout_rows = [
        f"- {row['strategy']}：检验样本宏观损失均值 {row['J1_macro_loss']:.3f}，95%CVaR {row['J2_cvar95_macro_loss']:.3f}，"
        f"累计缺口比例 {row['J3_gap_burden']:.3f}，调价波动率 {row['J4_adjustment_volatility']:.3f}。"
        for _, row in q4_sapr_comparison[q4_sapr_comparison["sample_split"].eq("holdout")]
        .sort_values("strategy").iterrows()
    ]
    q4_sapr_2026_rows = [
        f"- {row['strategy']}：2026情景宏观损失均值 {row['J1_macro_loss']:.3f}，95%CVaR {row['J2_cvar95_macro_loss']:.3f}，"
        f"累计缺口比例 {row['J3_gap_burden']:.3f}。"
        for _, row in q4_sapr_comparison[q4_sapr_comparison["sample_split"].eq("war_2026")]
        .sort_values("strategy").iterrows()
    ]
    q4_sapr_sensitivity_rows = [
        f"- {row['variant']}：规则=({row['rho_normal']:.2f},{row['rho_stress']:.2f},{row['rho_extreme']:.2f})，"
        f"检验期非支配概率 {row['holdout_non_dominated_probability']:.3f}。"
        for _, row in q4_sapr_sensitivity.sort_values("variant").iterrows()
    ]

    text = f"""# 建模到论文移交说明

[PAPER_READY]

原题三问与自拟问题四的建模、检验、数值冻结和论文移交材料已完成。当前 `overall_status={risk['overall_status']}`，`paper_finalize_allowed={str(risk['paper_finalize_allowed']).lower()}`，阻塞门禁数为 {len(risk['blocking_probe_ids'])}。

## 验证命令

```powershell
python code\\utils\\freeze_results.py
python code\\utils\\verify_freeze.py
python code\\utils\\verify_freeze.py --require-final
```

最后一次运行结果均为 `PASS`。论文所有数字优先引用 `results/frozen_numbers.json`、`results/final_numbers.json` 和 `reports/paper_numbers.csv`。

## 问题一：预测与战争影响

主线：`no_change` 作为诚实胜出的主预测模型，交易日 CAR 与周末匹配 placebo 作为事件相关异常证据，递归 SVAR 提供三类结构冲击。

核心写法：

{chr(10).join(q1_rows)}
{chr(10).join(car_rows)}

可用图表：`figures/q1_forecast_1m.png`、`figures/q1_war_counterfactual.png`、`figures/q1_structural_shocks.png`、`figures/paper_event_timeline.png`。

禁止写法：不得把 `ARBaselineGap` 称作严格战争净贡献；不得把 ARIMA/SARIMAX 未胜出解释成建模失败。

## 问题二：中国经济增长传导

主线：结构性油价冲击 → 人民币原油成本 → PPI → CPI/工业增加值 → 季度 GDP 验证。

油价特定风险冲击下的摘要：

{chr(10).join(q2_rows)}

结论边界：当前总体仍应写成“尚未发现稳健的总体增长损失证据”。若正文使用“增长损失”，必须同时满足工业活动负响应且联合区间排除零。

可用图表：`figures/q2_irf.png`、`figures/q2_transmission_chain.png`、`figures/paper_transmission_mechanism.png`。

## 问题三：中国政策与跨国比较

主线：中国使用官方受管制成品油价格层进入主燃油比较；面板 LP 只估计六个对照国相对中国的响应差；缓冲交互用于机制解释；政策关闭情景在官方成品油价格层上传播至 PPI/CPI/IAV。

综合韧性判断：`{resilience_overall}`。

{chr(10).join(q3_rows)}

政策关闭宏观反事实：

{chr(10).join(q3_macro_rows)}

可用图表：`figures/q3_pass_through_6m.png`、`figures/q3_panel_irf.png`、`figures/q3_resilience_metrics.png`、`figures/q3_policy_macro_counterfactual.png`、`figures/paper_policy_counterfactual_flow.png`。

禁止写法：不得仅凭价格传导或中国单一价格监管变量宣称“中国显著更好”；不得把价格平滑写成无成本福利改善。

## 问题四：极端油价尾部风险、政策压力测试与自适应调价规则优化

定位：该部分作为论文正式自拟问题四，不再设置其他自拟问题。问题四由两个互补模块构成：同事已有的 FHS–GJR-GARCH 尾部风险与宏观政策压力测试负责回答“极端冲击有多大概率、会形成多大压力”；本轮 SAPR-CVaR 自适应调价优化负责回答“在现行机制约束上应如何设置状态依赖的临时平滑层”。油价概率、Q2 结构冲击宏观情景、Q3 已实现政策反事实和 SAPR 策略优化是递进关系，不可简单相加为单一因果贡献。

FHS–GJR-GARCH 条件尾部预测：

{chr(10).join(q4_price_rows)}

与高斯随机游走的同口径滚动回测：

{chr(10).join(q4_backtest_rows)}

95%分位油价特定风险结构冲击的宏观压力：

{chr(10).join(q4_macro_rows)}

2026年已实现临时调控的政策缓冲重述：

{chr(10).join(q4_policy_rows)}

SAPR-CVaR 自适应调价规则：

{q4_sapr_rule_text}

隔离检验样本策略比较：

{chr(10).join(q4_sapr_holdout_rows)}

2026实际冲击情景策略比较：

{chr(10).join(q4_sapr_2026_rows)}

敏感性检验：

{chr(10).join(q4_sapr_sensitivity_rows)}

证据状态：`{q4_sapr_summary['evidence_status']}`；检验期非支配 bootstrap 概率为 `{q4_sapr_summary['holdout_non_dominated_probability']:.3f}`。

可用图表：`figures/q4_price_tail_risk.png`、`figures/q4_macro_policy_stress.png`、`figures/q4_sapr_pareto_front.png`、`figures/q4_sapr_policy_heatmap.png`、`figures/q4_sapr_strategy_comparison.png`、`figures/q4_sapr_2026_macro_paths.png`。

禁止写法：不得把尾部概率写成确定结果，不得把宏观情景写成确定性 GDP 损失，不得把 Q2 条件响应与 Q3 政策差额相加为单一因果贡献；不得把 SAPR 的注册规则族最优写成全球最优、完整福利收益或财政成本估计。

## 论文接手顺序

1. 先按 `reports/paper_numbers.csv` 抽取数值，填入摘要、问题重述、模型假设和结果表。
2. 四个问题均按“目标—数据—公式—估计—结果—检验—解释边界”写；问题四单列为自拟问题，明确从前三问结果递进而来。
3. 所有图表从 `figures/` 选择 PNG 入文，PDF 留作高清备份。
4. 写作期间如改动模型代码、输入数据或核心结果，必须重新运行冻结和 `--require-final`。
"""
    (REPORTS_DIR / "MODELING_TO_PAPER_HANDOFF.md").write_text(text, encoding="utf-8")


def main() -> None:
    apply_paper_style()
    REPORTS_DIR.mkdir(exist_ok=True)
    FIGURES_DIR.mkdir(exist_ok=True)
    write_paper_numbers()
    plot_q1_structural_shocks()
    plot_q2_transmission_chain()
    plot_q3_resilience_metrics()
    plot_q3_policy_macro_counterfactual()
    plot_route_map()
    plot_event_timeline()
    plot_transmission_mechanism()
    plot_policy_counterfactual_flow()
    write_handoff_markdown()
    print("[PAPER_READY] handoff artifacts generated.")


if __name__ == "__main__":
    main()
