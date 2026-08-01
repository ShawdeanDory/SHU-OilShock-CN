# 建模到论文移交说明

[PAPER_READY]

原题三问与自拟问题四的建模、检验、数值冻结和论文移交材料已完成。当前 `overall_status=PASS`，`paper_finalize_allowed=true`，阻塞门禁数为 0。

## 验证命令

```powershell
python code\utils\freeze_results.py
python code\utils\verify_freeze.py
python code\utils\verify_freeze.py --require-final
```

最后一次运行结果均为 `PASS`。论文所有数字优先引用 `results/frozen_numbers.json`、`results/final_numbers.json` 和 `reports/paper_numbers.csv`。

## 问题一：预测与战争影响

主线：`no_change` 作为诚实胜出的主预测模型，交易日 CAR 与周末匹配 placebo 作为事件相关异常证据，递归 SVAR 提供三类结构冲击。

核心写法：

- h=1：预测 70.89 美元/桶，实际 103.13。
- h=3：预测 70.89 美元/桶，实际 107.14。
- h=6：预测 70.89 美元/桶，实际 未到期。
- E1_CAR_0：CAR=0.0797，经验 p=0.0112。
- E1_CAR_0_1：CAR=0.1561，经验 p=0.0102。
- E1_CAR_0_2：CAR=0.1355，经验 p=0.0208。

可用图表：`figures/q1_forecast_1m.png`、`figures/q1_war_counterfactual.png`、`figures/q1_structural_shocks.png`、`figures/paper_event_timeline.png`。

禁止写法：不得把 `ARBaselineGap` 称作严格战争净贡献；不得把 ARIMA/SARIMAX 未胜出解释成建模失败。

## 问题二：中国经济增长传导

主线：结构性油价冲击 → 人民币原油成本 → PPI → CPI/工业增加值 → 季度 GDP 验证。

油价特定风险冲击下的摘要：

- 人民币原油成本：峰值/谷值 8.832，h=0，0—12月累计 4.939，证据状态 INCONCLUSIVE。
- CPI：峰值/谷值 0.247，h=7，0—12月累计 2.155，证据状态 INCONCLUSIVE。
- 工业增加值：峰值/谷值 -0.427，h=12，0—12月累计 -0.340，证据状态 INCONCLUSIVE。
- PPI：峰值/谷值 0.762，h=10，0—12月累计 7.401，证据状态 INCONCLUSIVE。

结论边界：当前总体仍应写成“尚未发现稳健的总体增长损失证据”。若正文使用“增长损失”，必须同时满足工业活动负响应且联合区间排除零。

可用图表：`figures/q2_irf.png`、`figures/q2_transmission_chain.png`、`figures/paper_transmission_mechanism.png`。

## 问题三：中国政策与跨国比较

主线：中国使用官方受管制成品油价格层进入主燃油比较；面板 LP 只估计六个对照国相对中国的响应差；缓冲交互用于机制解释；政策关闭情景在官方成品油价格层上传播至 PPI/CPI/IAV。

综合韧性判断：`PARTIAL`。

- fuel_1m_cumulative_pass_through：中国值 0.333，六国中位数 0.240，判断 NOT_SUPPORTED。
- fuel_3m_cumulative_pass_through：中国值 0.370，六国中位数 0.232，判断 NOT_SUPPORTED。
- fuel_6m_cumulative_pass_through：中国值 0.373，六国中位数 0.227，判断 NOT_SUPPORTED。
- cpi_relative_to_china：中国值 0.000，六国中位数 0.245，判断 PARTIAL。
- ip_relative_to_china：中国值 0.000，六国中位数 -0.544，判断 PARTIAL。

政策关闭宏观反事实：

- 2026-06 CPI：无临时调控相对实际路径差额 0.819 个百分点，95%区间 [0.242, 1.395]。
- 2026-06 IAV：无临时调控相对实际路径差额 -2.093 个百分点，95%区间 [-4.164, -0.023]。
- 2026-06 PPI：无临时调控相对实际路径差额 3.370 个百分点，95%区间 [1.567, 5.173]。

可用图表：`figures/q3_pass_through_6m.png`、`figures/q3_panel_irf.png`、`figures/q3_resilience_metrics.png`、`figures/q3_policy_macro_counterfactual.png`、`figures/paper_policy_counterfactual_flow.png`。

禁止写法：不得仅凭价格传导或中国单一价格监管变量宣称“中国显著更好”；不得把价格平滑写成无成本福利改善。

## 问题四：极端油价尾部风险、政策压力测试与自适应调价规则优化

定位：该部分作为论文正式自拟问题四，不再设置其他自拟问题。问题四由两个互补模块构成：同事已有的 FHS–GJR-GARCH 尾部风险与宏观政策压力测试负责回答“极端冲击有多大概率、会形成多大压力”；本轮 SAPR-CVaR 自适应调价优化负责回答“在现行机制约束上应如何设置状态依赖的临时平滑层”。油价概率、Q2 结构冲击宏观情景、Q3 已实现政策反事实和 SAPR 策略优化是递进关系，不可简单相加为单一因果贡献。

FHS–GJR-GARCH 条件尾部预测：

- h=1：中位数 70.95 美元/桶，90%区间 [53.41, 89.82]，期末超过历史95%价格分位的条件概率 0.27%。
- h=3：中位数 71.46 美元/桶，90%区间 [44.15, 103.41]，期末超过历史95%价格分位的条件概率 2.27%。
- h=6：中位数 71.76 美元/桶，90%区间 [37.15, 117.90]，期末超过历史95%价格分位的条件概率 5.56%。

与高斯随机游走的同口径滚动回测：

- FHS_GJR_GARCH，h=1：平均分位损失 1.639，80%/90%覆盖率 0.667/0.933。
- Gaussian_random_walk，h=1：平均分位损失 1.624，80%/90%覆盖率 0.933/0.933。
- FHS_GJR_GARCH，h=3：平均分位损失 2.303，80%/90%覆盖率 0.867/1.000。
- Gaussian_random_walk，h=3：平均分位损失 2.483，80%/90%覆盖率 1.000/1.000。
- FHS_GJR_GARCH，h=6：平均分位损失 3.888，80%/90%覆盖率 0.867/0.933。
- Gaussian_random_walk，h=6：平均分位损失 3.814，80%/90%覆盖率 0.933/0.933。

95%分位油价特定风险结构冲击的宏观压力：

- CPI，h=6：95%分位结构冲击条件响应 0.267 个百分点，联合95%区间 [-0.192, 0.726]，INCONCLUSIVE。
- CPI，h=12：95%分位结构冲击条件响应 0.240 个百分点，联合95%区间 [-0.223, 0.703]，INCONCLUSIVE。
- 工业增加值，h=6：95%分位结构冲击条件响应 -0.435 个百分点，联合95%区间 [-1.239, 0.369]，INCONCLUSIVE。
- 工业增加值，h=12：95%分位结构冲击条件响应 -0.628 个百分点，联合95%区间 [-1.420, 0.164]，INCONCLUSIVE。
- PPI，h=6：95%分位结构冲击条件响应 0.875 个百分点，联合95%区间 [-0.290, 2.041]，INCONCLUSIVE。
- PPI，h=12：95%分位结构冲击条件响应 0.493 个百分点，联合95%区间 [-0.859, 1.845]，INCONCLUSIVE。

2026年已实现临时调控的政策缓冲重述：

- 2026-06 CPI：政策缓冲收益 0.819 个百分点，95%区间 [0.242, 1.395]。
- 2026-06 工业增加值：政策缓冲收益 2.093 个百分点，95%区间 [0.023, 4.164]。
- 2026-06 PPI：政策缓冲收益 3.370 个百分点，95%区间 [1.567, 5.173]。

SAPR-CVaR 自适应调价规则：

- SAPR-CVaR 膝点规则：普通/压力/极端传导率 = (0.20, 0.05, 0.05)；压力阈值 436.0 元/吨，极端阈值 702.5 元/吨。

隔离检验样本策略比较：

- SAPR_CVaR_knee：检验样本宏观损失均值 0.091，95%CVaR 0.558，累计缺口比例 0.239，调价波动率 0.026。
- full_mechanism：检验样本宏观损失均值 0.315，95%CVaR 1.957，累计缺口比例 0.000，调价波动率 0.050。
- temporary_2026_approx：检验样本宏观损失均值 0.294，95%CVaR 1.768，累计缺口比例 0.022，调价波动率 0.043。
- uniform_75_smoothing：检验样本宏观损失均值 0.281，95%CVaR 1.792，累计缺口比例 0.037，调价波动率 0.044。

2026实际冲击情景策略比较：

- SAPR_CVaR_knee：2026情景宏观损失均值 0.794，95%CVaR 0.794，累计缺口比例 1.444。
- actual_2026_event_path：2026情景宏观损失均值 1.648，95%CVaR 1.648，累计缺口比例 0.710。
- full_mechanism：2026情景宏观损失均值 2.413，95%CVaR 2.413，累计缺口比例 0.000。
- temporary_2026_approx：2026情景宏观损失均值 2.235，95%CVaR 2.235，累计缺口比例 0.175。
- uniform_75_smoothing：2026情景宏观损失均值 2.236，95%CVaR 2.236，累计缺口比例 0.159。

敏感性检验：

- bootstrap_block_3：规则=(0.20,0.05,0.05)，检验期非支配概率 1.000。
- bootstrap_block_6：规则=(0.20,0.05,0.05)，检验期非支配概率 1.000。
- cpi_weight_plus20：规则=(0.20,0.05,0.05)，检验期非支配概率 1.000。
- iav_weight_plus20：规则=(0.20,0.05,0.05)，检验期非支配概率 1.000。
- threshold_70_90：规则=(0.20,0.10,0.00)，检验期非支配概率 1.000。
- threshold_80_975：规则=(0.15,0.05,0.05)，检验期非支配概率 1.000。

证据状态：`SUPPORTED`；检验期非支配 bootstrap 概率为 `1.000`。

可用图表：`figures/q4_price_tail_risk.png`、`figures/q4_macro_policy_stress.png`、`figures/q4_sapr_pareto_front.png`、`figures/q4_sapr_policy_heatmap.png`、`figures/q4_sapr_strategy_comparison.png`、`figures/q4_sapr_2026_macro_paths.png`。

禁止写法：不得把尾部概率写成确定结果，不得把宏观情景写成确定性 GDP 损失，不得把 Q2 条件响应与 Q3 政策差额相加为单一因果贡献；不得把 SAPR 的注册规则族最优写成全球最优、完整福利收益或财政成本估计。

## 论文接手顺序

1. 先按 `reports/paper_numbers.csv` 抽取数值，填入摘要、问题重述、模型假设和结果表。
2. 四个问题均按“目标—数据—公式—估计—结果—检验—解释边界”写；问题四单列为自拟问题，明确从前三问结果递进而来。
3. 所有图表从 `figures/` 选择 PNG 入文，PDF 留作高清备份。
4. 写作期间如改动模型代码、输入数据或核心结果，必须重新运行冻结和 `--require-final`。
