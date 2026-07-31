# 国际油价三问阶段性建模结果报告

## Material Passport

- Origin Skill: `3coding-visual`
- Execution Mode: `staged modeling audit`
- Verification Status: `PASS`
- Paper Finalize Allowed: `true`
- Cutoff: `2026-06-30`
- Random Seed: `20260730`

## 1. 总体结论

本轮代码、基线、数据覆盖、稳健性和数值冻结门禁均已通过，结果可以进入论文撰写阶段。这里的 `PASS` 表示计算流程具备定稿条件，不改变约化形式模型的识别边界。

当前最重要的边界是：问题一预测主模型改为 `no_change`，ARIMA/SARIMAX 只作解释性补充；事件后价格差额改名为 `ARBaselineGap`，不再称战争溢价；问题二的 `OilShock` 是约化形式油价创新；问题三中国燃油 proxy 不参与主跨国燃油传导排名。

阻塞定稿的门禁：

- 无。

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

E1 已从 2026-02-28 周末映射到 2026-03-02 交易日，同时输出 CAR[0]、CAR[0,+1]、CAR[0,+2] 和匹配周末 placebo 经验 p 值。经验 p 值采用 \((b+1)/(B+1)\) 的有限样本修正，不报告严格的 0。

| model | stage_id | estimate_log_return | std_error | lower_95 | upper_95 | pvalue | pvalue_empirical | event_observations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| brent_usd_bbl_event_car | E1_CAR_0 | 0.0788 | 0.0195 | 0.0406 | 0.1169 | 0.0001 | 0.0119 | 1.0000 |
| brent_usd_bbl_event_car | E1_CAR_0_1 | 0.1540 | 0.0275 | 0.1000 | 0.2080 | 0.0000 | 0.0108 | 2.0000 |
| brent_usd_bbl_event_car | E1_CAR_0_2 | 0.1319 | 0.0337 | 0.0658 | 0.1980 | 0.0001 | 0.0215 | 3.0000 |
| brent_usd_bbl_stage_dummy | E1 | 0.0684 | 0.0037 | 0.0612 | 0.0756 | 0.0000 |  | 1.0000 |
| brent_usd_bbl_stage_dummy | E2 | 0.0049 | 0.0062 | -0.0071 | 0.0170 | 0.4234 |  | 58.0000 |
| brent_usd_bbl_stage_dummy | E3 | -0.0148 | 0.0045 | -0.0235 | -0.0060 | 0.0009 |  | 8.0000 |

## 3. 问题二：中国宏观传导

国家统计局工业增加值与 PPI 完整历史已进入处理层。工业增加值官方 1 月及春节合并发布空值保持为空，不做插值；Q2 使用 167 个工业增加值真实月度观测和 198 个 PPI 月度观测。

Q2 的约化形式结果显示，油价创新对 PPI 存在即期正向响应，但工业增加值在 6 个月附近的负响应区间仍跨越 0，因此不能声称已识别出稳健的总体增长损失。CPI、汇率和 GDP 结果同样需带区间与识别 caveat 报告。

| outcome | horizon | response | lower_95 | upper_95 | ci95_contains_zero | fdr_qvalue | shock_identification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| china_cpi_yoy_pct | 0.0000 | 0.0189 | -0.0555 | 0.0876 | 1.0000 | 0.5315 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_cpi_yoy_pct | 6.0000 | 0.1049 | -0.0992 | 0.3002 | 1.0000 | 0.2970 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_cpi_yoy_pct | 12.0000 | 0.0932 | -0.1184 | 0.2558 | 1.0000 | 0.3052 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_fx_log_change_pct | 0.0000 | 0.0674 | -0.0816 | 0.1605 | 1.0000 | 0.2913 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_fx_log_change_pct | 6.0000 | 0.3567 | -0.3289 | 0.6423 | 1.0000 | 0.1772 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_fx_log_change_pct | 12.0000 | 0.5996 | -0.7634 | 1.1070 | 1.0000 | 0.1866 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_iav_yoy_pct | 0.0000 | 0.0010 | -0.3035 | 0.6046 | 1.0000 | 0.9956 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_iav_yoy_pct | 6.0000 | -0.2570 | -0.7378 | 0.2625 | 1.0000 | 0.7373 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_iav_yoy_pct | 12.0000 | -0.0569 | -0.2899 | 0.5146 | 1.0000 | 0.8425 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_ppi_yoy_pct | 0.0000 | 0.1698 | 0.0262 | 0.3199 | 0.0000 | 0.0250 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_ppi_yoy_pct | 6.0000 | 0.0715 | -0.3183 | 0.6457 | 1.0000 | 0.9406 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |
| china_ppi_yoy_pct | 12.0000 | -0.3065 | -0.7974 | 0.4646 | 1.0000 | 0.4034 | reduced_form_ARX_oil_price_innovation_not_structural_supply_shock |

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
- `results/reproducibility_manifest.json`

其中 `frozen_numbers.json` 遵循 `3coding-visual` 标准冻结格式；风险门禁以及代码、输入、输出文件哈希保存在独立的 reproducibility manifest 中。数值一致性使用标准 skill 脚本检查，项目级文件与环境检查使用 `python code/utils/verify_freeze.py`。

## 6. Warnings

- `nbs_gdp_yoy_manual_supplement`：OECD GY lacks 2026-Q2; GDP yoy=4.3 added from NBS 2026-07-15 release.
- `china_fuel_price_proxy`：China fuel price uses Brent-CNY tonne proxy adjusted by cumulative NDRC policy gaps; it is not an observed retail gasoline series.

## 7. 论文使用建议

论文可以使用当前冻结数值：第一问主线是“no-change 基线预测 + 交易日事件窗口 + 描述性 AR 基准差额”；第二问主线是“约化形式冲击下的 PPI 即期响应与缺乏稳健总体增长损失证据”；第三问主线是“可比国家零售燃油传导 + 中国政策代理情景”。所有结论继续遵守非因果和代理变量边界。
