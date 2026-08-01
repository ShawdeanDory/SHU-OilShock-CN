# 国际油价四问建模封板结果报告

## Material Passport

- Origin Skill: `math-modeling-solver + math-modeling-paper`
- Execution Mode: `paper-ready modeling freeze`
- Verification Status: `PASS`
- Paper Finalize Allowed: `true`
- Cutoff: `2026-06-30`
- Random Seed: `20260730`

## 1. 总体结论

本轮结果已通过风险探针、Schema 校验、哈希冻结与 `--require-final` 验证，可以作为论文定稿数字来源。论文仍需保持证据边界：Q2 的宏观增长损失证据为 `INCONCLUSIVE`，Q3 对“我国应对更好”的综合判断为 `PARTIAL`。

当前可写入论文的主线是：问题一采用 `no_change` 主预测、交易日 CAR/placebo 事件证据、历史递归 SVAR 三类结构冲击和描述性 `ARBaselineGap`；问题二采用结构冲击主规格与 约化形式稳健性，报告人民币原油成本—PPI—CPI/工业活动—GDP 传导链；问题三使用中国中国调价指数代理退出正式价格水平排名，待审计缓冲交互不发布，并输出条件动态政策情景；问题四使用 FHS–GJR-GARCH 报告尾部概率，将 Q2 结构冲击压力与 Q3 已实现政策反事实分层展示，并进一步用 SAPR-CVaR 在现行调价机制约束上优化临时平滑规则。

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
| brent_usd_bbl_event_car | E1_CAR_0 | 0.0797 | 0.0195 | 0.0415 | 0.1178 | 0.0000 | 0.0244 | 1.0000 |
| brent_usd_bbl_event_car | E1_CAR_0_1 | 0.1561 | 0.0275 | 0.1021 | 0.2101 | 0.0000 | 0.0244 | 2.0000 |
| brent_usd_bbl_event_car | E1_CAR_0_2 | 0.1355 | 0.0337 | 0.0694 | 0.2016 | 0.0001 | 0.0513 | 3.0000 |
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

| shock | outcome | extremum_type | extremum_response | extremum_month | response_curve_area_0_6 | response_curve_area_0_12 | area_unit | evidence_status | allows_growth_loss_language |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aggregate_demand_shock | brent_cny_cost_log_change_pct | peak_abs | 3.1229 | 1.0000 | 5.2937 | 3.4078 | percentage_point_month | INCONCLUSIVE | 0.0000 |
| aggregate_demand_shock | china_cpi_yoy_pct | peak_abs | 0.1259 | 9.0000 | 0.4912 | 1.0984 | percentage_point_month | INCONCLUSIVE | 0.0000 |
| aggregate_demand_shock | china_fx_log_change_pct | peak_abs | -0.3488 | 6.0000 | -1.2490 | -2.6522 | percentage_point_month | INCONCLUSIVE | 0.0000 |
| aggregate_demand_shock | china_iav_yoy_pct | trough | -0.5197 | 6.0000 |  |  | not_applicable_sparse_horizons | INCONCLUSIVE | 0.0000 |
| aggregate_demand_shock | china_ppi_yoy_pct | peak_abs | 0.4601 | 10.0000 | 1.6330 | 3.7647 | percentage_point_month | INCONCLUSIVE | 0.0000 |
| oil_specific_risk_shock | brent_cny_cost_log_change_pct | peak_abs | 8.8321 | 0.0000 | 7.4401 | 4.9385 | percentage_point_month | INCONCLUSIVE | 0.0000 |
| oil_specific_risk_shock | china_cpi_yoy_pct | peak_abs | 0.2467 | 7.0000 | 0.8767 | 2.1552 | percentage_point_month | INCONCLUSIVE | 0.0000 |
| oil_specific_risk_shock | china_fx_log_change_pct | peak_abs | 0.7710 | 12.0000 | 1.6122 | 5.8458 | percentage_point_month | INCONCLUSIVE | 0.0000 |
| oil_specific_risk_shock | china_iav_yoy_pct | trough | -0.4272 | 12.0000 |  |  | not_applicable_sparse_horizons | INCONCLUSIVE | 0.0000 |
| oil_specific_risk_shock | china_ppi_yoy_pct | peak_abs | 0.7622 | 10.0000 | 3.6545 | 7.4006 | percentage_point_month | INCONCLUSIVE | 0.0000 |
| supply_shock | brent_cny_cost_log_change_pct | peak_abs | 3.9588 | 0.0000 | 4.4243 | 4.7471 | percentage_point_month | INCONCLUSIVE | 0.0000 |
| supply_shock | china_cpi_yoy_pct | peak_abs | 0.0861 | 4.0000 | 0.1290 | 0.1041 | percentage_point_month | INCONCLUSIVE | 0.0000 |

季度 GDP 只作低频验证，不插值成月度变量。

| outcome | estimate | lower_95 | upper_95 | pvalue | n | sample_start | sample_end |
| --- | --- | --- | --- | --- | --- | --- | --- |
| china_real_gdp_yoy_pct |  |  |  |  | 0.0000 |  |  |

## 4. 问题三：政策缓冲与跨国比较

跨国燃油主排名只纳入覆盖充分且价格层可解释的观测零售汽油价格。中国历史路径是受管制汽油调价指数代理，只保留为敏感性材料；2026政策公告差额单独核验。

| country | horizon | response | lower_95 | upper_95 | price_measure_type | included_in_main_comparison |
| --- | --- | --- | --- | --- | --- | --- |
| DEU | 6.0000 | 0.2367 | 0.1358 | 0.3376 | observed_retail_gasoline | 1.0000 |
| ESP | 6.0000 | 0.2482 | 0.1629 | 0.3334 | observed_retail_gasoline | 1.0000 |
| FRA | 6.0000 | 0.1979 | 0.0689 | 0.3269 | observed_retail_gasoline | 1.0000 |
| ITA | 6.0000 | 0.2169 | 0.1025 | 0.3313 | observed_retail_gasoline | 1.0000 |
| JPN | 6.0000 | 0.1989 | 0.1233 | 0.2745 | observed_retail_gasoline | 1.0000 |
| KOR | 6.0000 | 0.2374 | 0.1513 | 0.3236 | observed_retail_gasoline | 1.0000 |

综合韧性指标把燃油传导、CPI 相对响应、工业活动相对响应和政策关闭情景放在同一口径下判断。当前总体判断为 `PARTIAL`，不是无条件支持“中国显著更好”。

| dimension | metric | horizon | china_value | control_median | china_vs_control_median_diff | diff_lower_95 | diff_upper_95 | judgement | overall_china_resilience_judgement |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fuel_price | six_month_pass_through_proxy_sensitivity | 6.0000 | 0.3734 | 0.2268 |  |  |  | CONDITIONAL_PROXY | INCONCLUSIVE |
| consumer_prices | control_minus_china_cpi_relative_response | 5.0000 |  | 0.2451 | 0.2451 |  |  | INCONCLUSIVE | INCONCLUSIVE |
| industrial_activity | control_minus_china_ip_relative_response | 1.0000 |  | 2.4328 | 2.4328 |  |  | INCONCLUSIVE | INCONCLUSIVE |
| policy_counterfactual_macro | china_cpi_yoy_pct | 3.0000 | 0.5242 |  |  | 0.1538 | 0.9929 | POLICY_SCENARIO | INCONCLUSIVE |
| policy_counterfactual_macro | china_iav_yoy_pct | 3.0000 | -1.1109 |  |  | -1.9996 | -0.0661 | POLICY_SCENARIO | INCONCLUSIVE |
| policy_counterfactual_macro | china_ppi_yoy_pct | 4.0000 | 2.5956 |  |  | 1.4527 | 3.6329 | POLICY_SCENARIO | INCONCLUSIVE |

中国政策图与数据表已区分新增差额和累计差额，2026-04 的累计差额为 1425 元/吨，4月新增为 380 元/吨。

| period | policy_adjusted_official_cny_t | no_temporary_control_official_cny_t | incremental_gasoline_gap_cny_t | cumulative_gasoline_gap_cny_t | cpi_counterfactual_gap_pctpt | price_layer_status |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-02 | 7878.0357 | 7878.0357 | 0.0000 | 0.0000 | 0.0000 | regulated_gasoline_adjustment_index_proxy_with_2026_notice_gaps |
| 2026-03 | 8842.5806 | 9887.5806 | 1045.0000 | 1045.0000 | 0.3738 | regulated_gasoline_adjustment_index_proxy_with_2026_notice_gaps |
| 2026-04 | 10060.5000 | 11485.5000 | 380.0000 | 1425.0000 | 0.4038 | regulated_gasoline_adjustment_index_proxy_with_2026_notice_gaps |
| 2026-05 | 10031.6129 | 11456.6129 | 0.0000 | 1425.0000 | 0.5242 | regulated_gasoline_adjustment_index_proxy_with_2026_notice_gaps |
| 2026-06 | 9504.0000 | 10929.0000 | 0.0000 | 1425.0000 | 0.4139 | regulated_gasoline_adjustment_index_proxy_with_2026_notice_gaps |

政策关闭宏观情景在明确标注的调价指数代理层上，将2026临时调控收益差通过0—6阶核和结果变量递归传播到PPI、CPI与IAV；区间来自三方程共同时间块重采样。

| period | outcome_label | macro_counterfactual_gap_pctpt | lower_95 | upper_95 | price_layer_status | evidence_status |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-06 | CPI | 0.4139 | 0.1993 | 1.0878 | regulated_gasoline_adjustment_index_proxy_with_2026_notice_gaps | CONDITIONAL_DYNAMIC_PROXY_SCENARIO |
| 2026-06 | IAV | -0.4691 | -1.6898 | 0.6724 | regulated_gasoline_adjustment_index_proxy_with_2026_notice_gaps | CONDITIONAL_DYNAMIC_PROXY_SCENARIO |
| 2026-06 | PPI | 2.5956 | 1.4527 | 3.6329 | regulated_gasoline_adjustment_index_proxy_with_2026_notice_gaps | CONDITIONAL_DYNAMIC_PROXY_SCENARIO |

## 5. 问题四：极端油价尾部风险、政策压力测试与自适应调价规则优化

问题四把同事已完成的“尾部风险与压力测试”作为风险输入层，并把本轮 SAPR-CVaR 自适应调价规则作为政策优化层：先判断极端油价路径概率与宏观压力，再回答我国成品油调价机制在极端冲击下应如何状态依赖地平滑传导。油价概率层以 2026-06-30 最后交易日为原点，比较 FHS–GJR-GARCH 与恒定波动高斯随机游走；历史 90%/95%价格分位只作为上行压力阈值。

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
| FHS_GJR_GARCH | 1.0000 | 47.0000 | 1.5647 | 4.8945 | 0.8085 | 0.9362 | 26.4542 |
| Gaussian_random_walk | 1.0000 | 47.0000 | 1.6288 | 4.3907 | 0.9362 | 0.9574 | 35.5231 |
| FHS_GJR_GARCH | 3.0000 | 47.0000 | 2.3667 | 7.9488 | 0.8723 | 0.9574 | 47.4366 |
| Gaussian_random_walk | 3.0000 | 47.0000 | 2.5615 | 6.9626 | 0.9574 | 0.9787 | 62.5604 |
| FHS_GJR_GARCH | 6.0000 | 47.0000 | 3.5192 | 8.6212 | 0.8936 | 0.9362 | 69.0469 |
| Gaussian_random_walk | 6.0000 | 47.0000 | 3.6894 | 7.1355 | 0.9362 | 0.9574 | 90.6974 |

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
| 2026-06 | CPI | 0.4139 | 0.1993 | 1.0878 | SUPPORTED_95 |
| 2026-06 | 工业增加值 | 0.4691 | -0.6724 | 1.6898 | INCONCLUSIVE |
| 2026-06 | PPI | 2.5956 | 1.4527 | 3.6329 | SUPPORTED_95 |

SAPR-CVaR 优化层只在 2013-03—2021-12 开发样本上确定阈值和规则，2022-01—2026-06 完全作为隔离检验样本；2026 年战争冲击只用于检验和展示，不参与规则选择。三档传导率满足 `普通 ≥ 压力 ≥ 极端`，目标函数同时考虑宏观损失、95% CVaR、累计未调价负担和国内调价波动。

| rule_id | rho_normal | rho_stress | rho_extreme | stress_threshold_75_cny_t | stress_threshold_95_cny_t | J1_macro_loss | J2_cvar95_macro_loss | J3_avg_gap_month_burden | J4_adjustment_volatility | max_gap_ratio | max_recovery_terminal_gap_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R0062 | 0.3000 | 0.1000 | 0.1000 | 435.9727 | 702.4907 | 0.1315 | 0.5225 | 0.0245 | 0.0332 | 0.1567 | 0.0184 |

隔离检验样本与 2026 实际冲击情景的策略比较如下。若 SAPR 在检验样本被预注册基线支配，论文必须报告负结果；当前证据状态以 `q4_sapr_summary.json` 为准。

| sample_split | strategy | rho_normal | rho_stress | rho_extreme | J1_macro_loss | J2_cvar95_macro_loss | J3_avg_gap_month_burden | J4_adjustment_volatility | max_gap_ratio | max_recovery_terminal_gap_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| holdout | SAPR_CVaR_knee | 0.3000 | 0.1000 | 0.1000 | 0.1650 | 1.1979 | 0.0222 | 0.0351 | 0.2000 | 0.0235 |
| holdout | full_mechanism | 1.0000 | 1.0000 | 1.0000 | 0.3155 | 1.9571 | 0.0000 | 0.0503 | 0.0000 | 0.0000 |
| holdout | temporary_2026_approx | 1.0000 | 1.0000 | 0.5258 | 0.2941 | 1.7681 | 0.0031 | 0.0426 | 0.1746 | 0.0000 |
| holdout | uniform_75_smoothing | 0.7500 | 0.7500 | 0.7500 | 0.2812 | 1.7916 | 0.0052 | 0.0438 | 0.0953 | 0.0000 |
| war_2026 | SAPR_CVaR_knee | 0.3000 | 0.1000 | 0.1000 | 1.7116 | 1.7116 | 0.0971 | 0.0678 | 0.2000 | 0.0029 |
| war_2026 | actual_2026_event_path |  |  |  | 1.6477 | 1.6477 | 0.0933 | 0.0856 | 0.1499 | 0.1499 |
| war_2026 | full_mechanism | 1.0000 | 1.0000 | 1.0000 | 2.4129 | 2.4129 | 0.0000 | 0.1148 | 0.0000 | 0.0000 |
| war_2026 | temporary_2026_approx | 1.0000 | 1.0000 | 0.5258 | 2.2346 | 2.2346 | 0.0291 | 0.0821 | 0.1746 | 0.0000 |
| war_2026 | uniform_75_smoothing | 0.7500 | 0.7500 | 0.7500 | 2.2364 | 2.2364 | 0.0266 | 0.0921 | 0.0953 | 0.0000 |

敏感性检验固定改变阈值、bootstrap 块长和 CPI/IAV 权重，不为追求结论改动样本或目标函数。

| variant | rho_normal | rho_stress | rho_extreme | pareto_rule_count | holdout_non_dominated_probability | changed_from_default |
| --- | --- | --- | --- | --- | --- | --- |
| threshold_70_90 | 0.3000 | 0.1500 | 0.1000 | 82.0000 | 1.0000 | 1.0000 |
| threshold_80_975 | 0.3000 | 0.1000 | 0.1000 | 209.0000 | 1.0000 | 0.0000 |
| cpi_weight_plus20 | 0.3000 | 0.1000 | 0.1000 | 121.0000 | 1.0000 | 0.0000 |
| iav_weight_plus20 | 0.3000 | 0.1000 | 0.1000 | 116.0000 | 1.0000 | 0.0000 |
| bootstrap_block_3 | 0.3000 | 0.1000 | 0.1000 | 119.0000 | 1.0000 | 0.0000 |
| bootstrap_block_6 | 0.3000 | 0.1000 | 0.1000 | 119.0000 | 1.0000 | 0.0000 |
| bootstrap_block_12 | 0.3000 | 0.1000 | 0.1000 | 119.0000 | 1.0000 | 0.0000 |

## 6. 图表与冻结文件

核心 PNG 图表：data_overview_fuel_panel.png, data_overview_oil_gpr.png, q1_forecast_1m.png, q1_structural_shocks.png, q1_war_counterfactual.png, q2_irf.png, q2_transmission_chain.png, q3_panel_irf.png, q3_pass_through_6m.png, q3_policy_counterfactual.png, q3_policy_macro_counterfactual.png, q3_resilience_metrics.png, q4_macro_policy_stress.png, q4_price_tail_risk.png, q4_sapr_2026_macro_paths.png, q4_sapr_pareto_front.png, q4_sapr_policy_heatmap.png, q4_sapr_strategy_comparison.png。

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
- `oecd_gdp_fetch_failed`：china_real_gdp_yoy_pct: HTTPSConnectionPool(host='sdmx.oecd.org', port=443): Max retries exceeded with url: /public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_GROWTH_OECD/Q.....B1GQ......GY.?startPeriod=2010-Q1&endPeriod=2026-Q2&dimensionAtObservation=AllDimensions&format=csvfile (Caused by ProxyError('Cannot connect to proxy.', NewConnectionError('<urllib3.connection.HTTPSConnection object at 0x000002162DAA6510>: Failed to establish a new connection: [WinError 10061] 由于目标计算机积极拒绝，无法连接。')))
- `oecd_gdp_fetch_failed`：china_real_gdp_qoq_pct: HTTPSConnectionPool(host='sdmx.oecd.org', port=443): Max retries exceeded with url: /public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_GROWTH_OECD/Q.....B1GQ......G1.?startPeriod=2010-Q1&endPeriod=2026-Q2&dimensionAtObservation=AllDimensions&format=csvfile (Caused by ProxyError('Cannot connect to proxy.', NewConnectionError('<urllib3.connection.HTTPSConnection object at 0x000002162DB1C910>: Failed to establish a new connection: [WinError 10061] 由于目标计算机积极拒绝，无法连接。')))
- `china_fuel_price_proxy_only`：China historical fuel series is a reconstructed adjustment-index proxy and is excluded from the formal cross-country price-level ranking.
- `q2_gdp_validation_limited`：Too few GDP validation observations after lags.
- `q3_buffer_quantitative_results_withheld`：Continuous buffer interactions were withheld because the country-year table is an unaudited proxy.
- `q3_policy_joint_bootstrap`：Accepted 2000 joint three-equation moving-block draws from 2197 attempts.
- `q3_fuel_panel_leave_one_withheld`：Fuel panel leave-one-country inference is withheld because China is a proxy and excluded from the formal price-level panel.

## 8. 论文使用建议

论文正文可把当前结果作为封板数值使用，但必须区分预测表现、事件相关异常、结构冲击传导和政策情景模拟。第一问不得把 `ARBaselineGap` 写成严格战争净贡献；第二问不得在联合区间未排除零时写“显著增长损失”；第三问不得仅凭价格传导或单一价格监管变量断言中国政策具有一般因果优势；问题四不得把尾部概率写成确定结果，不得把 Q2 与 Q3 的不同证据层直接相加，也不得把 SAPR 的注册规则族最优写成全球福利最优。
