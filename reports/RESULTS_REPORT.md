# 国际油价三问阶段性建模结果报告

## Material Passport

- Origin Skill: `academic-research-suite / experiment-agent`
- Execution Mode: `goal`
- Verification Status: `CONDITIONAL`
- Paper Finalize Allowed: `false`
- Cutoff: `2026-06-30`
- Random Seed: `20260730`

## 1. 总体结论

本轮结果已经从“可直接定稿”降级为 `CONDITIONAL` 阶段快照。代码、图表和结果可以继续作为建模推进基础，但论文正文不能把当前输出写成严格因果结论。

当前最重要的边界是：问题一预测主模型改为 `no_change`，ARIMA/SARIMAX 只作解释性补充；事件后价格差额改名为 `ARBaselineGap`，不再称战争溢价；问题二的 `OilShock` 是约化形式油价创新；问题三中国燃油 proxy 不参与主跨国燃油传导排名。

阻塞定稿的门禁：

- `q1_forecast_baseline_gate`
- `q2_nbs_macro_completeness_gate`

## 2. 问题一：预测与事件窗口

月度预测表已经加入相对基线指标和逐模型状态。当前主预测模型是 `no_change`。

| model | horizon | RMSE | relative_RMSE_vs_no_change | dm_hln_pvalue_rmse_loss | model_status |
| --- | --- | --- | --- | --- | --- |
| ARIMA | 1.0000 | 0.1437 | 1.0209 | 0.8734 | CONDITIONAL |
| SARIMAX | 1.0000 | 0.1442 | 1.0247 | 0.8304 | CONDITIONAL |
| no_change | 1.0000 | 0.1408 | 1.0000 |  | PASS |
| ARIMA | 3.0000 | 0.2977 | 1.1190 | 0.2895 | FAIL |
| SARIMAX | 3.0000 | 0.2938 | 1.1044 | 0.2837 | FAIL |
| no_change | 3.0000 | 0.2660 | 1.0000 |  | PASS |
| ARIMA | 6.0000 | 0.3432 | 1.1137 | 0.2789 | FAIL |
| SARIMAX | 6.0000 | 0.3394 | 1.1014 | 0.2651 | FAIL |
| no_change | 6.0000 | 0.3082 | 1.0000 |  | PASS |

E1 已从 2026-02-28 周末映射到 2026-03-02 交易日，同时输出 CAR[0]、CAR[0,+1]、CAR[0,+2] 和匹配周末 placebo 经验 p 值。

| model | stage_id | estimate_log_return | std_error | lower_95 | upper_95 | pvalue | pvalue_empirical | event_observations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| brent_usd_bbl_event_car | E1_CAR_0 | 0.0788 | 0.0195 | 0.0406 | 0.1169 | 0.0001 | 0.0000 | 1.0000 |
| brent_usd_bbl_event_car | E1_CAR_0_1 | 0.1540 | 0.0275 | 0.1000 | 0.2080 | 0.0000 | 0.0000 | 2.0000 |
| brent_usd_bbl_event_car | E1_CAR_0_2 | 0.1319 | 0.0337 | 0.0658 | 0.1980 | 0.0001 | 0.0109 | 3.0000 |
| brent_usd_bbl_stage_dummy | E1 | 0.0684 | 0.0037 | 0.0612 | 0.0756 | 0.0000 |  | 1.0000 |
| brent_usd_bbl_stage_dummy | E2 | 0.0049 | 0.0062 | -0.0071 | 0.0170 | 0.4234 |  | 58.0000 |
| brent_usd_bbl_stage_dummy | E3 | -0.0148 | 0.0045 | -0.0235 | -0.0060 | 0.0009 |  | 8.0000 |

## 3. 问题二：中国宏观传导

Q2 当前只能写为“尚未发现稳健的总体增长损失证据”。IAV/PPI 官方历史序列尚未进入处理层，CPI、汇率和 GDP 结果均需带区间与识别 caveat 报告。

| outcome | horizon | response | lower_95 | upper_95 | ci95_contains_zero | fdr_qvalue | shock_identification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| china_cpi_yoy_pct | 0.0000 | 0.0189 | -0.0555 | 0.0876 | 1.0000 | 0.5315 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_cpi_yoy_pct | 6.0000 | 0.1049 | -0.0992 | 0.3002 | 1.0000 | 0.2970 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_cpi_yoy_pct | 12.0000 | 0.0932 | -0.1184 | 0.2558 | 1.0000 | 0.3052 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_fx_log_change_pct | 0.0000 | 0.0674 | -0.0816 | 0.1605 | 1.0000 | 0.2913 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_fx_log_change_pct | 6.0000 | 0.3567 | -0.3289 | 0.6423 | 1.0000 | 0.1772 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_fx_log_change_pct | 12.0000 | 0.5996 | -0.7634 | 1.1070 | 1.0000 | 0.1866 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |

季度 GDP 只作低频验证，不插值成月度变量。

| outcome | estimate | lower_95 | upper_95 | pvalue | n | sample_start | sample_end |
| --- | --- | --- | --- | --- | --- | --- | --- |
| china_real_gdp_yoy_pct | 0.6643 | -0.0817 | 1.4104 | 0.0809 | 65.0000 | 2010-Q2 | 2026-Q2 |

## 4. 问题三：政策缓冲与跨国比较

跨国燃油主排名现在只纳入德国、日本、韩国的观测官方零售汽油价格。中国 Brent-CNY 代理值保留为政策情景和附录敏感性材料。

| country | horizon | response | lower_95 | upper_95 | price_measure_type | included_in_main_comparison |
| --- | --- | --- | --- | --- | --- | --- |
| DEU | 6.0000 | 0.2367 | 0.1358 | 0.3376 | observed_retail_gasoline | 1.0000 |
| JPN | 6.0000 | 0.1989 | 0.1233 | 0.2745 | observed_retail_gasoline | 1.0000 |
| KOR | 6.0000 | 0.2374 | 0.1513 | 0.3236 | observed_retail_gasoline | 1.0000 |

中国政策图与数据表已区分新增差额和累计差额，2026-04 的累计差额为 1425 元/吨，4月新增为 380 元/吨。

| period | policy_adjusted_proxy_cny_t | no_temporary_control_proxy_cny_t | incremental_gasoline_gap_cny_t | cumulative_gasoline_gap_cny_t | cpi_counterfactual_gap_pctpt |
| --- | --- | --- | --- | --- | --- |
| 2026-02 | 3589.2274 | 3589.2274 | 0.0000 | 0.0000 | 0.0000 |
| 2026-03 | 4166.2262 | 5211.2262 | 1045.0000 | 1045.0000 | 0.4874 |
| 2026-04 | 4454.0946 | 5879.0946 | 380.0000 | 1425.0000 | 0.6045 |
| 2026-05 | 3915.9735 | 5340.9735 | 0.0000 | 1425.0000 | 0.6758 |
| 2026-06 | 2817.2991 | 4242.2991 | 0.0000 | 1425.0000 | 0.8914 |

## 5. 图表与冻结文件

核心 PNG 图表：data_overview_fuel_panel.png, data_overview_oil_gpr.png, q1_forecast_1m.png, q1_war_counterfactual.png, q2_irf.png, q3_panel_irf.png, q3_pass_through_6m.png, q3_policy_counterfactual.png。

冻结文件：

- `results/final_numbers.json`
- `results/frozen_numbers.json`
- `results/risk_probe_summary.json`

## 6. Warnings

- `missing_raw_snapshot`：nbs_cpi_202606_release raw snapshot is absent
- `missing_raw_snapshot`：nbs_gdp_2026q2_release raw snapshot is absent
- `missing_raw_snapshot`：nbs_iav_202606_release raw snapshot is absent
- `missing_raw_snapshot`：nbs_ppi_202606_release raw snapshot is absent
- `missing_raw_snapshot`：ndrc_fuel_control_20260323 raw snapshot is absent
- `missing_raw_snapshot`：ndrc_fuel_control_20260407 raw snapshot is absent
- `missing_raw_snapshot`：oecd_g20_cpi_monthly raw snapshot is absent
- `missing_raw_snapshot`：oecd_kei_ip_monthly raw snapshot is absent
- `nbs_gdp_yoy_manual_supplement`：OECD GY lacks 2026-Q2; GDP yoy=4.3 added from NBS 2026-07-15 release.
- `optional_china_macro_missing`：nbs_iav_monthly.csv absent; Q2 will run available CPI/FX/GDP modules.
- `optional_china_macro_missing`：nbs_ppi_monthly.csv absent; Q2 will run available CPI/FX/GDP modules.
- `china_fuel_price_proxy`：China fuel price uses Brent-CNY tonne proxy adjusted by cumulative NDRC policy gaps; it is not an observed retail gasoline series.
- `q2_outcome_skipped`：中国规模以上工业增加值同比，百分点 skipped: insufficient usable monthly history.
- `q2_outcome_skipped`：中国PPI同比，百分点 skipped: insufficient usable monthly history.
- `nbs_gdp_yoy_manual_supplement`：OECD GY lacks 2026-Q2; GDP yoy=4.3 added from NBS 2026-07-15 release.
- `optional_china_macro_missing`：nbs_iav_monthly.csv absent; Q2 will run available CPI/FX/GDP modules.
- `optional_china_macro_missing`：nbs_ppi_monthly.csv absent; Q2 will run available CPI/FX/GDP modules.
- `china_fuel_price_proxy`：China fuel price uses Brent-CNY tonne proxy adjusted by cumulative NDRC policy gaps; it is not an observed retail gasoline series.

## 7. 论文使用建议

论文正文应把当前状态写成阶段性结果：第一问主线是“基线预测 + 交易日事件窗口 + 描述性 AR 基准差额”；第二问主线是“约化形式冲击下未发现稳健增长损失证据”；第三问主线是“可比国家零售燃油传导 + 中国政策代理情景”。只有在风险门禁全部 `PASS` 后，才可把冻结文件作为定稿数值来源。
