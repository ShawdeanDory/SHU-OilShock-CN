# 国际油价三问阶段性建模结果报告

## Material Passport

- Origin Skill: `3coding-visual`
- Execution Mode: `staged modeling audit`
- Verification Status: `CONDITIONAL`
- Paper Finalize Allowed: `false`
- Cutoff: `2026-06-30`
- Random Seed: `20260730`

## 1. 总体结论

本轮结果已经从“可直接定稿”降级为 `CONDITIONAL` 阶段快照。代码、图表和结果可以继续作为建模推进基础，但论文正文不能把当前输出写成严格因果结论。

当前最重要的边界是：问题一预测主模型改为 `no_change`，ARIMA/SARIMAX 只作解释性补充；事件后价格差额改名为 `ARBaselineGap`，不再称战争溢价；问题二以结构冲击为主、`OilShock` 仅作约化形式稳健性；问题三中国燃油 proxy 不参与主跨国燃油传导排名。

阻塞定稿的门禁：

- `q2_nbs_macro_completeness_gate`
- `q3_china_comparability`
- `q3_policy_counterfactual_price_layer`

## 2. 问题一：预测与事件窗口

月度预测表已经加入相对基线指标和逐模型状态。当前主预测模型是 `no_change`。

| model | horizon | RMSE | relative_RMSE_vs_no_change | dm_hln_pvalue_rmse_loss | model_status |
| --- | --- | --- | --- | --- | --- |
| ARIMA | 1.0000 | 0.1437 | 1.0209 | 0.8734 | CONDITIONAL |
| ETS | 1.0000 | 0.1631 | 1.1587 | 0.3177 | FAIL |
| EqualWeight | 1.0000 | 0.1448 | 1.0286 | 0.6994 | CONDITIONAL |
| SARIMAX | 1.0000 | 0.1442 | 1.0247 | 0.8304 | CONDITIONAL |
| Theta | 1.0000 | 0.1409 | 1.0010 | 0.6447 | CONDITIONAL |
| no_change | 1.0000 | 0.1408 | 1.0000 |  | PASS |
| ARIMA | 3.0000 | 0.2977 | 1.1190 | 0.2895 | FAIL |
| ETS | 3.0000 | 0.3232 | 1.2149 | 0.3186 | FAIL |
| EqualWeight | 3.0000 | 0.2865 | 1.0770 | 0.3113 | FAIL |
| SARIMAX | 3.0000 | 0.2938 | 1.1044 | 0.2837 | FAIL |
| Theta | 3.0000 | 0.2668 | 1.0028 | 0.5825 | CONDITIONAL |
| no_change | 3.0000 | 0.2660 | 1.0000 |  | PASS |

E1 已从 2026-02-28 周末映射到 2026-03-02 交易日，同时输出 CAR[0]、CAR[0,+1]、CAR[0,+2] 和匹配周末 placebo 经验 p 值。经验 p 值采用 \((b+1)/(B+1)\) 的有限样本修正，不报告严格的 0。

| model | stage_id | estimate_log_return | std_error | lower_95 | upper_95 | pvalue | pvalue_empirical | event_observations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| brent_usd_bbl_event_car | E1_CAR_0 | 0.0797 | 0.0195 | 0.0415 | 0.1178 | 0.0000 | 0.0112 | 1.0000 |
| brent_usd_bbl_event_car | E1_CAR_0_1 | 0.1561 | 0.0275 | 0.1021 | 0.2101 | 0.0000 | 0.0102 | 2.0000 |
| brent_usd_bbl_event_car | E1_CAR_0_2 | 0.1355 | 0.0337 | 0.0694 | 0.2016 | 0.0001 | 0.0208 | 3.0000 |
| brent_usd_bbl_stage_dummy | E1 | 0.0407 |  |  |  |  |  | 3.0000 |
| brent_usd_bbl_stage_dummy | E2 | 0.0052 | 0.0063 | -0.0072 | 0.0177 | 0.4101 |  | 58.0000 |
| brent_usd_bbl_stage_dummy | E3 | -0.0154 | 0.0045 | -0.0242 | -0.0066 | 0.0006 |  | 8.0000 |

## 3. 问题二：中国宏观传导

Q2 当前只能写为“尚未发现稳健的总体增长损失证据”。IAV/PPI 官方历史序列尚未进入处理层，CPI、汇率和 GDP 结果均需带区间与识别 caveat 报告。

| outcome | horizon | response | lower_95 | upper_95 | ci95_contains_zero | fdr_qvalue | shock_identification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| china_cpi_yoy_pct | 0.0000 | -0.3406 | -1.4793 | 0.2346 | 1.0000 | 0.6796 | adverse_supply_shock_from_EIA_recursive_decomposition |
| china_cpi_yoy_pct | 0.0000 | 0.0932 | -0.4846 | 0.9390 | 1.0000 | 0.8896 | aggregate_demand_shock_from_EIA_recursive_decomposition |
| china_cpi_yoy_pct | 0.0000 | -0.0167 | -0.6429 | 0.4660 | 1.0000 | 0.9655 | oil_specific_risk_shock_from_EIA_recursive_decomposition |
| china_cpi_yoy_pct | 0.0000 | 0.0247 | -0.0694 | 0.0913 | 1.0000 | 0.6147 | reduced_form_ARX_oil_price_innovation_robustness |
| china_cpi_yoy_pct | 6.0000 | -0.3090 | -1.0174 | 0.4484 | 1.0000 | 0.6796 | adverse_supply_shock_from_EIA_recursive_decomposition |
| china_cpi_yoy_pct | 6.0000 | 0.0947 | -0.4727 | 0.9808 | 1.0000 | 0.8896 | aggregate_demand_shock_from_EIA_recursive_decomposition |
| china_cpi_yoy_pct | 6.0000 | 0.0891 | -0.4872 | 0.5365 | 1.0000 | 0.8153 | oil_specific_risk_shock_from_EIA_recursive_decomposition |
| china_cpi_yoy_pct | 6.0000 | 0.1068 | -0.0944 | 0.2799 | 1.0000 | 0.5544 | reduced_form_ARX_oil_price_innovation_robustness |
| china_cpi_yoy_pct | 12.0000 | 0.1246 | -0.2287 | 1.1756 | 1.0000 | 0.6796 | adverse_supply_shock_from_EIA_recursive_decomposition |
| china_cpi_yoy_pct | 12.0000 | -0.0869 | -1.3744 | 0.5350 | 1.0000 | 0.8896 | aggregate_demand_shock_from_EIA_recursive_decomposition |
| china_cpi_yoy_pct | 12.0000 | 0.0691 | -0.6260 | 0.4484 | 1.0000 | 0.9655 | oil_specific_risk_shock_from_EIA_recursive_decomposition |
| china_cpi_yoy_pct | 12.0000 | 0.0932 | -0.1554 | 0.2510 | 1.0000 | 0.5544 | reduced_form_ARX_oil_price_innovation_robustness |

季度 GDP 只作低频验证，不插值成月度变量。

| outcome | estimate | lower_95 | upper_95 | pvalue | n | sample_start | sample_end |
| --- | --- | --- | --- | --- | --- | --- | --- |
| china_real_gdp_yoy_pct | 0.0037 | -0.2631 | 0.2704 | 0.9785 | 65.0000 | 2010-Q2 | 2026-Q2 |

## 4. 问题三：政策缓冲与跨国比较

跨国燃油主排名现在只纳入德国、法国、意大利、西班牙、日本、韩国的观测官方零售汽油价格。中国 Brent-CNY 代理值保留为政策情景和附录敏感性材料。

| country | horizon | response | lower_95 | upper_95 | price_measure_type | included_in_main_comparison |
| --- | --- | --- | --- | --- | --- | --- |
| DEU | 6.0000 | 0.2367 | 0.1358 | 0.3376 | observed_retail_gasoline | 1.0000 |
| ESP | 6.0000 | 0.2482 | 0.1629 | 0.3334 | observed_retail_gasoline | 1.0000 |
| FRA | 6.0000 | 0.1979 | 0.0689 | 0.3269 | observed_retail_gasoline | 1.0000 |
| ITA | 6.0000 | 0.2169 | 0.1025 | 0.3313 | observed_retail_gasoline | 1.0000 |
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
- `results/reproducibility_manifest.json`

其中 `frozen_numbers.json` 遵循 `3coding-visual` 标准冻结格式；风险门禁以及代码、输入、输出文件哈希保存在独立的 reproducibility manifest 中。数值一致性使用标准 skill 脚本检查，项目级文件与环境检查使用 `python code/utils/verify_freeze.py`。

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
- `q2_robustness_skipped`：china_cpi_yoy_pct lag=12 exclude_covid=True: too few observations.
- `q2_robustness_skipped`：china_fx_log_change_pct lag=12 exclude_covid=True: too few observations.
- `q3_buffer_lp_skipped`：fuel h=0: buffer interaction is not identifiable with current comparable data.
- `q3_buffer_lp_skipped`：fuel h=1: buffer interaction is not identifiable with current comparable data.
- `q3_buffer_lp_skipped`：fuel h=2: buffer interaction is not identifiable with current comparable data.
- `q3_buffer_lp_skipped`：fuel h=3: buffer interaction is not identifiable with current comparable data.

## 7. 论文使用建议

论文正文应把当前状态写成阶段性结果：第一问主线是“基线预测 + 交易日事件窗口 + 描述性 AR 基准差额”；第二问主线是“结构冲击/约化形式稳健性下尚未发现稳健增长损失证据”；第三问主线是“六个可比国家零售燃油传导 + 政策缓冲交互 + 中国政策代理情景”。只有在风险门禁全部 `PASS` 后，才可把冻结文件作为定稿数值来源。
