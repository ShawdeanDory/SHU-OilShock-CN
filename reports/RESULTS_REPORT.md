# 国际油价三问及拓展建模封板结果报告

## Material Passport

- Origin Skill: `math-modeling-solver + math-modeling-paper`
- Execution Mode: `paper-ready modeling freeze`
- Verification Status: `PASS`
- Paper Finalize Allowed: `true`
- Cutoff: `2026-06-30`
- Random Seed: `20260730`

## 1. 总体结论

本轮结果已通过风险探针、Schema 校验、哈希冻结与 `--require-final` 验证，可以作为论文定稿数字来源。论文仍需保持证据边界：Q2 的宏观增长损失证据为 `INCONCLUSIVE`，Q3 对“我国应对更好”的综合判断为 `PARTIAL`。

当前可写入论文的主线是：问题一采用 `no_change` 主预测、交易日 CAR/placebo 事件证据、历史递归 SVAR 三类结构冲击和描述性 `ARBaselineGap`；问题二采用结构冲击主规格与 约化形式稳健性，报告人民币原油成本—PPI—CPI/工业活动—GDP 传导链；问题三使用中国官方受管制成品油价格层进入主比较，并输出缓冲交互、综合韧性指标和政策关闭宏观反事实；自拟拓展使用 FHS–GJR-GARCH 报告尾部概率，并将 Q2 结构冲击压力与 Q3 已实现政策反事实分层展示。

当前阻塞定稿的门禁：

- 无。

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

以 2026-02 为原点的竞赛最终预测表如下。2026-08 在数据截止日之后，保留为 `FORECAST_ONLY`。

| origin_period | target_period | horizon_months | model | forecast_status | origin_price | prediction_price | actual_price | forecast_error_price |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-02 | 2026-03 | 1.0000 | no_change | ACTUAL_AVAILABLE | 70.8870 | 70.8870 | 103.1345 | 32.2475 |
| 2026-02 | 2026-05 | 3.0000 | no_change | ACTUAL_AVAILABLE | 70.8870 | 70.8870 | 107.1395 | 36.2525 |
| 2026-02 | 2026-08 | 6.0000 | no_change | FORECAST_ONLY | 70.8870 | 70.8870 |  |  |

历史结构冲击使用递归 VAR/Cholesky 分解，变量排序为“全球供给增长 → 全球真实经济活动 → 实际 Brent 收益”。被选规格如下：

| candidate_lags | is_selected | bic | is_stable | whiteness_pvalue | sample_start | sample_end | nobs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6.0000 | 1.0000 | 12.5123 | 1.0000 | 0.3817 | 2010-02 | 2026-03 | 186.0000 |

GJR-GARCH 条件波动率用于描述战争阶段油价波动变化，不作为战争净因果效应。

| war_stage | trading_days | conditional_vol_pct_median | vol_multiple_vs_pre_median | evidence_status |
| --- | --- | --- | --- | --- |
| prewar | 535.0000 | 1.7433 | 1.0000 | DESCRIPTIVE_VOLATILITY |
| E1_immediate_window | 3.0000 | 2.7667 | 1.5871 | DESCRIPTIVE_VOLATILITY |
| E2_disruption | 67.0000 | 3.8588 | 2.2135 | DESCRIPTIVE_VOLATILITY |
| E3_easing | 10.0000 | 2.7304 | 1.5663 | DESCRIPTIVE_VOLATILITY |

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

国家统计局 IAV/PPI 官方历史已经进入处理层，其中工业增加值有 167 个真实观测，PPI 有 198 个真实观测；官方 1—2 月结构性空值保持为空，不做插值。Q2 当前只能写为“尚未发现稳健的总体增长损失证据”，所有结果仍需带区间与识别 caveat 报告。

| outcome | shock | horizon | response | lower_95 | upper_95 | joint_lower_95 | joint_upper_95 | fdr_qvalue | inference_band |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| brent_cny_cost_log_change_pct | OilShock | 0.0000 | 10.1875 | 9.4431 | 10.5692 | 9.1636 | 11.2114 | 0.0130 | moving_block_bootstrap_sup_t_95 |
| brent_cny_cost_log_change_pct | OilShock | 6.0000 | 0.4422 | -1.9825 | 1.8125 | -2.9740 | 3.8584 | 0.8021 | moving_block_bootstrap_sup_t_95 |
| brent_cny_cost_log_change_pct | OilShock | 12.0000 | -1.1376 | -3.6194 | 0.7589 | -5.0189 | 2.7437 | 0.5086 | moving_block_bootstrap_sup_t_95 |
| brent_cny_cost_log_change_pct | aggregate_demand_shock | 0.0000 | 0.9348 | -0.4075 | 2.5560 | -1.2450 | 3.1147 | 0.7493 | moving_block_bootstrap_sup_t_95 |
| brent_cny_cost_log_change_pct | aggregate_demand_shock | 6.0000 | 0.3083 | -1.7870 | 2.0041 | -2.5544 | 3.1710 | 0.9435 | moving_block_bootstrap_sup_t_95 |
| brent_cny_cost_log_change_pct | aggregate_demand_shock | 12.0000 | 0.0330 | -2.3034 | 2.3454 | -3.5132 | 3.5791 | 0.9435 | moving_block_bootstrap_sup_t_95 |
| brent_cny_cost_log_change_pct | oil_specific_risk_shock | 0.0000 | 8.8321 | 7.6176 | 9.9453 | 6.8883 | 10.7760 | 0.0130 | moving_block_bootstrap_sup_t_95 |
| brent_cny_cost_log_change_pct | oil_specific_risk_shock | 6.0000 | 1.0394 | -1.2191 | 3.3078 | -2.5407 | 4.6196 | 0.7592 | moving_block_bootstrap_sup_t_95 |
| brent_cny_cost_log_change_pct | oil_specific_risk_shock | 12.0000 | -0.9112 | -3.4112 | 1.1555 | -4.5127 | 2.6904 | 0.7650 | moving_block_bootstrap_sup_t_95 |
| brent_cny_cost_log_change_pct | supply_shock | 0.0000 | 3.9588 | -1.2262 | 7.5291 | -5.0859 | 13.0034 | 0.8784 | moving_block_bootstrap_sup_t_95 |
| brent_cny_cost_log_change_pct | supply_shock | 6.0000 | 0.3981 | -1.1376 | 2.1186 | -2.3582 | 3.1544 | 0.8996 | moving_block_bootstrap_sup_t_95 |
| brent_cny_cost_log_change_pct | supply_shock | 12.0000 | -0.9628 | -3.7152 | 0.2658 | -4.5291 | 2.6034 | 0.6952 | moving_block_bootstrap_sup_t_95 |

传导链摘要按冲击—变量输出峰值/谷值、累计响应和证据状态。当前即使部分点估计方向符合直觉，也不自动升级为“增长损失”结论。

| shock | outcome | extremum_type | extremum_response | extremum_month | cumulative_response_0_6 | cumulative_response_0_12 | evidence_status | allows_growth_loss_language |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aggregate_demand_shock | brent_cny_cost_log_change_pct | peak_abs | 3.1229 | 1.0000 | 5.2937 | 3.4078 | INCONCLUSIVE | 0.0000 |
| aggregate_demand_shock | china_cpi_yoy_pct | peak_abs | 0.1259 | 9.0000 | 0.4912 | 1.0984 | INCONCLUSIVE | 0.0000 |
| aggregate_demand_shock | china_fx_log_change_pct | peak_abs | -0.3488 | 6.0000 | -1.2490 | -2.6522 | INCONCLUSIVE | 0.0000 |
| aggregate_demand_shock | china_iav_yoy_pct | trough | -0.5197 | 6.0000 | -0.7033 | -0.5868 | INCONCLUSIVE | 0.0000 |
| aggregate_demand_shock | china_ppi_yoy_pct | peak_abs | 0.4601 | 10.0000 | 1.6330 | 3.7647 | INCONCLUSIVE | 0.0000 |
| oil_specific_risk_shock | brent_cny_cost_log_change_pct | peak_abs | 8.8321 | 0.0000 | 7.4401 | 4.9385 | INCONCLUSIVE | 0.0000 |
| oil_specific_risk_shock | china_cpi_yoy_pct | peak_abs | 0.2467 | 7.0000 | 0.8767 | 2.1552 | INCONCLUSIVE | 0.0000 |
| oil_specific_risk_shock | china_fx_log_change_pct | peak_abs | 0.7710 | 12.0000 | 1.6122 | 5.8458 | INCONCLUSIVE | 0.0000 |
| oil_specific_risk_shock | china_iav_yoy_pct | trough | -0.4272 | 12.0000 | 0.0870 | -0.3402 | INCONCLUSIVE | 0.0000 |
| oil_specific_risk_shock | china_ppi_yoy_pct | peak_abs | 0.7622 | 10.0000 | 3.6545 | 7.4006 | INCONCLUSIVE | 0.0000 |
| supply_shock | brent_cny_cost_log_change_pct | peak_abs | 3.9588 | 0.0000 | 4.4243 | 4.7471 | INCONCLUSIVE | 0.0000 |
| supply_shock | china_cpi_yoy_pct | peak_abs | 0.0861 | 4.0000 | 0.1290 | 0.1041 | INCONCLUSIVE | 0.0000 |

季度 GDP 只作低频验证，不插值成月度变量。

| outcome | estimate | lower_95 | upper_95 | pvalue | n | sample_start | sample_end |
| --- | --- | --- | --- | --- | --- | --- | --- |
| china_real_gdp_yoy_pct | 0.7482 | 0.0095 | 1.4869 | 0.0471 | 65.0000 | 2010-Q2 | 2026-Q2 |

## 4. 问题三：政策缓冲与跨国比较

跨国燃油主排名只纳入覆盖充分的观测或官方受管制零售汽油价格。中国 Brent-CNY 代理值只保留为附录敏感性材料；正式政策情景已改用官方零售价层。

| country | horizon | response | lower_95 | upper_95 | price_measure_type | included_in_main_comparison |
| --- | --- | --- | --- | --- | --- | --- |
| CHN | 6.0000 | 0.3734 | 0.2433 | 0.5035 | official_regulated_standard_gasoline_cap | 1.0000 |
| DEU | 6.0000 | 0.2367 | 0.1358 | 0.3376 | observed_retail_gasoline | 1.0000 |
| ESP | 6.0000 | 0.2482 | 0.1629 | 0.3334 | observed_retail_gasoline | 1.0000 |
| FRA | 6.0000 | 0.1979 | 0.0689 | 0.3269 | observed_retail_gasoline | 1.0000 |
| ITA | 6.0000 | 0.2169 | 0.1025 | 0.3313 | observed_retail_gasoline | 1.0000 |
| JPN | 6.0000 | 0.1989 | 0.1233 | 0.2745 | observed_retail_gasoline | 1.0000 |
| KOR | 6.0000 | 0.2374 | 0.1513 | 0.3236 | observed_retail_gasoline | 1.0000 |

综合韧性指标把燃油传导、CPI 相对响应、工业活动相对响应和政策关闭情景放在同一口径下判断。当前总体判断为 `PARTIAL`，不是无条件支持“中国显著更好”。

| dimension | metric | horizon | china_value | control_median | china_vs_control_median_diff | diff_lower_95 | diff_upper_95 | judgement | overall_china_resilience_judgement |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fuel_pass_through | fuel_1m_cumulative_pass_through | 1.0000 | 0.3335 | 0.2401 | -0.0933 | -0.2413 | 0.0547 | NOT_SUPPORTED | PARTIAL |
| fuel_pass_through | fuel_3m_cumulative_pass_through | 3.0000 | 0.3700 | 0.2323 | -0.1377 | -0.2596 | -0.0158 | NOT_SUPPORTED | PARTIAL |
| fuel_pass_through | fuel_6m_cumulative_pass_through | 6.0000 | 0.3734 | 0.2268 | -0.1466 | -0.2767 | -0.0164 | NOT_SUPPORTED | PARTIAL |
| cpi_peak_response | cpi_relative_to_china | 5.0000 | 0.0000 | 0.2451 | 0.2451 | -0.0549 | 0.5451 | PARTIAL | PARTIAL |
| industrial_activity_trough | ip_relative_to_china | 12.0000 | 0.0000 | -0.5438 | -0.5438 | -1.6868 | 0.6975 | PARTIAL | PARTIAL |
| policy_counterfactual_macro | china_cpi_yoy_pct | 6.0000 | 0.8185 |  |  | 0.2423 | 1.3948 | POLICY_SCENARIO | PARTIAL |
| policy_counterfactual_macro | china_iav_yoy_pct | 6.0000 | -2.0935 |  |  | -4.1639 | -0.0230 | POLICY_SCENARIO | PARTIAL |
| policy_counterfactual_macro | china_ppi_yoy_pct | 6.0000 | 3.3701 |  |  | 1.5673 | 5.1729 | POLICY_SCENARIO | PARTIAL |

中国政策图与数据表已区分新增差额和累计差额，2026-04 的累计差额为 1425 元/吨，4月新增为 380 元/吨。

| period | policy_adjusted_official_cny_t | no_temporary_control_official_cny_t | incremental_gasoline_gap_cny_t | cumulative_gasoline_gap_cny_t | cpi_counterfactual_gap_pctpt | price_layer_status |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-02 | 7878.0357 | 7878.0357 | 0.0000 | 0.0000 | 0.0000 | official_regulated_finished_fuel_price_layer |
| 2026-03 | 8842.5806 | 9887.5806 | 1045.0000 | 1045.0000 | 0.6545 | official_regulated_finished_fuel_price_layer |
| 2026-04 | 10060.5000 | 11485.5000 | 380.0000 | 1425.0000 | 0.7761 | official_regulated_finished_fuel_price_layer |
| 2026-05 | 10031.6129 | 11456.6129 | 0.0000 | 1425.0000 | 0.7782 | official_regulated_finished_fuel_price_layer |
| 2026-06 | 9504.0000 | 10929.0000 | 0.0000 | 1425.0000 | 0.8185 | official_regulated_finished_fuel_price_layer |

政策关闭宏观反事实已在官方受管制成品油价格层上将临时调控缺口传播到 PPI、CPI 与 IAV，区间来自同一参数不确定性传播。

| period | outcome_label | macro_counterfactual_gap_pctpt | lower_95 | upper_95 | price_layer_status | evidence_status |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-06 | CPI | 0.8185 | 0.2423 | 1.3948 | official_regulated_finished_fuel_price_layer | MACRO_PROPAGATED_WITH_PARAMETER_UNCERTAINTY |
| 2026-06 | IAV | -2.0935 | -4.1639 | -0.0230 | official_regulated_finished_fuel_price_layer | MACRO_PROPAGATED_WITH_PARAMETER_UNCERTAINTY |
| 2026-06 | PPI | 3.3701 | 1.5673 | 5.1729 | official_regulated_finished_fuel_price_layer | MACRO_PROPAGATED_WITH_PARAMETER_UNCERTAINTY |

## 5. 自拟拓展：油价尾部风险与政策压力测试

该模块不是题面正式编号问题。油价概率层以 2026-06-30 最后交易日为原点，比较 FHS–GJR-GARCH 与恒定波动高斯随机游走；历史 90%/95%价格分位只作为上行压力阈值。

| model | horizon_months | median_price | p05_price | p95_price | terminal_prob_above_hist_p90 | terminal_prob_above_hist_p95 | path_prob_cross_hist_p95 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FHS_GJR_GARCH | 1.0000 | 70.9531 | 53.4109 | 89.8229 | 0.0041 | 0.0027 | 0.0037 |
| FHS_GJR_GARCH | 3.0000 | 71.4556 | 44.1523 | 103.4081 | 0.0294 | 0.0227 | 0.0376 |
| FHS_GJR_GARCH | 6.0000 | 71.7560 | 37.1529 | 117.8999 | 0.0683 | 0.0556 | 0.0964 |
| Gaussian_random_walk | 1.0000 | 70.3095 | 56.9037 | 87.1069 | 0.0003 | 0.0001 | 0.0001 |
| Gaussian_random_walk | 3.0000 | 69.9413 | 48.6115 | 101.0162 | 0.0186 | 0.0121 | 0.0199 |
| Gaussian_random_walk | 6.0000 | 69.5814 | 41.5863 | 116.1625 | 0.0670 | 0.0516 | 0.0951 |

滚动回测在同一原点、期限和评价口径下比较主方法与基线；主方法是否胜出由分位损失和覆盖率共同判断，不因预设方法而更换回测区间。

| model | horizon_months | origins | mean_pinball_loss | median_absolute_error | coverage_80 | coverage_90 | mean_width_90 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FHS_GJR_GARCH | 1.0000 | 15.0000 | 1.6386 | 4.7788 | 0.6667 | 0.9333 | 28.6661 |
| Gaussian_random_walk | 1.0000 | 15.0000 | 1.6237 | 4.4784 | 0.9333 | 0.9333 | 35.8286 |
| FHS_GJR_GARCH | 3.0000 | 15.0000 | 2.3006 | 7.5792 | 0.8667 | 1.0000 | 50.8253 |
| Gaussian_random_walk | 3.0000 | 15.0000 | 2.4829 | 6.5916 | 1.0000 | 1.0000 | 62.8624 |
| FHS_GJR_GARCH | 6.0000 | 15.0000 | 3.8860 | 6.8558 | 0.8667 | 0.9333 | 72.8509 |
| Gaussian_random_walk | 6.0000 | 15.0000 | 3.8135 | 6.0388 | 0.9333 | 0.9333 | 90.9725 |

宏观压力层使用 Q1 油价特定风险冲击的历史正向分位数缩放 Q2 IRF。下表只展示 95%分位冲击的 6、12 月条件响应；联合区间跨零时继续标记为 `INCONCLUSIVE`。

| scenario | outcome_label | horizon | conditional_response_pctpt | joint_lower_95 | joint_upper_95 | row_evidence_status |
| --- | --- | --- | --- | --- | --- | --- |
| extreme_q95 | CPI | 6.0000 | 0.2672 | -0.1917 | 0.7260 | INCONCLUSIVE |
| extreme_q95 | CPI | 12.0000 | 0.2400 | -0.2235 | 0.7034 | INCONCLUSIVE |
| extreme_q95 | 工业增加值 | 6.0000 | -0.4354 | -1.2394 | 0.3687 | INCONCLUSIVE |
| extreme_q95 | 工业增加值 | 12.0000 | -0.6284 | -1.4204 | 0.1636 | INCONCLUSIVE |
| extreme_q95 | PPI | 6.0000 | 0.8754 | -0.2898 | 2.0406 | INCONCLUSIVE |
| extreme_q95 | PPI | 12.0000 | 0.4930 | -0.8593 | 1.8454 | INCONCLUSIVE |

政策压力层只重述 Q3 已实现的 2026 年临时调控关闭反事实，不外推到模拟油价路径。正的“政策缓冲收益”分别表示避免的 PPI/CPI 增幅或避免的工业活动损失。

| period | outcome_label | policy_buffer_benefit_pctpt | benefit_lower_95 | benefit_upper_95 | evidence_status |
| --- | --- | --- | --- | --- | --- |
| 2026-06 | CPI | 0.8185 | 0.2423 | 1.3948 | SUPPORTED_95 |
| 2026-06 | 工业增加值 | 2.0935 | 0.0230 | 4.1639 | SUPPORTED_95 |
| 2026-06 | PPI | 3.3701 | 1.5673 | 5.1729 | SUPPORTED_95 |

## 6. 图表与冻结文件

核心 PNG 图表：data_overview_fuel_panel.png, data_overview_oil_gpr.png, q1_forecast_1m.png, q1_structural_shocks.png, q1_war_counterfactual.png, q2_irf.png, q2_transmission_chain.png, q3_panel_irf.png, q3_pass_through_6m.png, q3_policy_counterfactual.png, q3_policy_macro_counterfactual.png, q3_resilience_metrics.png, q4_macro_policy_stress.png, q4_price_tail_risk.png。

冻结文件：

- `results/final_numbers.json`
- `results/frozen_numbers.json`
- `results/risk_probe_summary.json`
- `results/reproducibility_manifest.json`

其中 `frozen_numbers.json` 遵循 `3coding-visual` 标准冻结格式；风险门禁以及代码、输入、输出文件哈希保存在独立的 reproducibility manifest 中。数值一致性使用标准 skill 脚本检查，项目级文件与环境检查使用 `python code/utils/verify_freeze.py`。

## 7. Warnings

- `manifest_status`：nbs_cpi_202606_release status=REMOTE_ONLY
- `missing_raw_snapshot`：nbs_cpi_202606_release raw snapshot is absent
- `manifest_status`：nbs_gdp_2026q2_release status=REMOTE_ONLY
- `missing_raw_snapshot`：nbs_gdp_2026q2_release raw snapshot is absent
- `manifest_status`：nbs_iav_202606_release status=REMOTE_ONLY
- `missing_raw_snapshot`：nbs_iav_202606_release raw snapshot is absent
- `manifest_status`：nbs_ppi_202606_release status=REMOTE_ONLY
- `missing_raw_snapshot`：nbs_ppi_202606_release raw snapshot is absent
- `manifest_status`：ndrc_fuel_control_20260323 status=REMOTE_ONLY
- `missing_raw_snapshot`：ndrc_fuel_control_20260323 raw snapshot is absent
- `manifest_status`：ndrc_fuel_control_20260407 status=REMOTE_ONLY
- `missing_raw_snapshot`：ndrc_fuel_control_20260407 raw snapshot is absent
- `nbs_gdp_yoy_manual_supplement`：OECD GY lacks 2026-Q2; GDP yoy=4.3 added from NBS 2026-07-15 release.

## 8. 论文使用建议

论文正文可把当前结果作为封板数值使用，但必须区分预测表现、事件相关异常、结构冲击传导和政策情景模拟。第一问不得把 `ARBaselineGap` 写成严格战争净贡献；第二问不得在联合区间未排除零时写“显著增长损失”；第三问不得仅凭价格传导或单一价格监管变量断言中国政策具有一般因果优势；拓展问题不得把尾部概率写成确定结果，也不得把 Q2 与 Q3 的不同证据层直接相加。
