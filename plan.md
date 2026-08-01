# SHU-OilShock-CN 建模封板计划

更新日期：2026-08-01

数据截止日：2026-06-30

当前状态：`overall_status=PASS`，`paper_finalize_allowed=true`

本文件记录当前进入论文写作前的可执行口径。所有正式论文数字必须来自 `results/frozen_numbers.json`、`results/final_numbers.json` 或 `reports/paper_numbers.csv`，不得手工改写。

## 1. 当前已完成的建模主线

### 问题一：油价预测与战争影响

- 主预测模型：`no_change`。ARIMA、SARIMAX、ETS、Theta 和 EqualWeight 作为对照模型记录；高级模型未战胜 no-change 是实证结论，不是失败。
- 最终预测表：`results/q1_origin_forecast.csv`，以 2026-02 为原点，包含 1、3、6 月目标；2026-08 因截止日未到，保留为 `FORECAST_ONLY`。
- 事件窗口：E1 从 2026-03-02 首个共同交易日开始；正式事件证据使用 CAR 与匹配周末 placebo 经验 p 值。
- 描述性反事实：`ARBaselineGap` 只表示 AR 基准情景差额，不写成战争净因果贡献。
- 结构冲击：`results/q1_structural_shocks.csv` 由 2010 起历史递归 VAR / Cholesky 分解生成，三类冲击各 186 个非空月，SVAR 诊断见 `results/q1_svar_diagnostics.csv`。
- 波动性：GJR-GARCH 阶段波动汇总见 `results/q1_volatility_summary.csv`。

### 问题二：中国经济传导

- 主冲击：Q1 输出的 `supply_shock`、`aggregate_demand_shock`、`oil_specific_risk_shock`；`OilShock` 仅作约化形式稳健性。
- 传导链：结构冲击 → 人民币原油成本 → PPI → CPI / 工业增加值 → 季度 GDP 低频验证。
- 月度变量：IAV、PPI、CPI、汇率、人民币原油成本均已进入 `data/processed/model_monthly_cn.csv`。
- IAV 因官方 1—2 月结构性缺失，只输出预注册 0、3、6、12 月期限；不插值。
- 主要结果：`results/q2_irf.csv` 与 `results/q2_transmission_metrics.csv`。
- 证据状态：`INCONCLUSIVE`。论文可以写“尚未发现稳健总体增长损失证据”，不能写“油价冲击显著造成中国增长损失”。

### 问题三：中国政策缓冲与跨国比较

- 主燃油比较国家：中国、德国、法国、意大利、西班牙、日本、韩国。
- 中国燃油主口径：官方受管制汽油标准品最高零售限价（元/吨），不再使用 Brent-CNY 代理进入主排名。
- 中国燃油覆盖：2013-03 至 2026-06 共 160 个非空月，已进入主比较。
- 西班牙 CPI：使用 Eurostat HICP yoy fallback，解决 OECD G20 表中西班牙缺口。
- 面板识别：完整年月固定效应下只估计“对照国相对中国”的响应差；中国绝对响应由分国模型给出。
- 缓冲变量：价格监管、石油进口依赖度、石油强度、进口来源 HHI 均已进入年度表并出现在交互输出中。
- 政策反事实：在官方受管制燃油价格层移除 2026 年临时调控缺口，输出 PPI、CPI、IAV 宏观传播路径。
- 综合判断：`results/q3_resilience_metrics.csv` 给出 `PARTIAL`，即部分维度点估计支持中国缓冲，但燃油传导率本身不优于六国中位数。

### 自拟拓展：油价尾部风险与政策压力测试

- 题面依据：“包括且不限于下述问题”；该模块在论文中标记为自拟拓展，不替代前三项核心任务。
- 主方法：FHS–GJR-GARCH；可用基线：恒定波动高斯随机游走。
- 概率输出：以 2026-06-30 为信息截止，报告未来 1、3、6 个月价格分布和超过历史 90%/95%价格分位的条件概率。
- 回测口径：15 个完整季度末原点，主方法与基线使用相同期限、路径数、随机种子策略和分位损失/覆盖率指标。
- 宏观压力：Q1 油价特定风险结构冲击的 75%/90%/95%分位情景乘以 Q2 IRF，并保留联合置信区间和 `INCONCLUSIVE` 标记。
- 政策压力：只重述 Q3 已实现的 2026 年临时调控关闭反事实，不外推到模拟油价路径。
- 主要结果：`results/q4_price_tail_risk.csv`、`results/q4_risk_backtest.csv`、`results/q4_macro_stress.csv`、`results/q4_policy_stress.csv`。
- 图表：`figures/q4_price_tail_risk.*`、`figures/q4_macro_policy_stress.*`。

## 2. 当前冻结与验证

固定重跑顺序：

```powershell
python code\data_processing\build_p0_datasets.py
python code\data_processing\validate_p0.py
python code\data_processing\build_model_panels.py
python code\problem1\run_q1.py
python code\data_processing\build_model_panels.py
python code\problem2\run_q2.py
python code\problem3\run_q3.py
python code\problem4\run_q4.py --probe
python code\problem4\run_q4.py
python code\utils\freeze_results.py
python code\utils\build_paper_handoff.py
python code\utils\verify_freeze.py
python code\utils\verify_freeze.py --require-final
```

当前验证结果：

- `results/risk_probe_summary.json`：`overall_status=PASS`
- `results/risk_probe_summary.json`：`paper_finalize_allowed=true`
- `python code\utils\verify_freeze.py --require-final`：返回 0

## 3. 论文写作边界

允许表述：

- Q1：no-change 在固定回测中合法胜出；事件影响以 CAR/placebo 报告；ARBaselineGap 是描述性基准差额。
- Q2：油价冲击对人民币原油成本和部分价格变量存在响应，但总体增长损失证据不稳健。
- Q3：中国政策缓冲证据为 `PARTIAL`；官方价格层反事实显示若移除临时调控，PPI/CPI 上行、IAV 下行的代理路径更明显。
- Q4：可报告固定截止日下的条件尾部概率、历史结构冲击分位压力和已实现政策缓冲；三层证据不可加总。

禁止表述：

- ARIMA/SARIMAX 明显优于 no-change。
- ARBaselineGap 等同战争净因果贡献。
- Q2 已证明中国增长显著受损。
- 中国“全面优于”其他国家；当前综合结论只能写为部分支持。
- 价格平滑无成本；累计未调价差额应解释为政策成本或延期负担代理。
- Q4 尾部概率是确定性结果，或 Q4 已证明未来必然出现某一油价。
- 将 Q2 条件宏观响应与 Q3 政策反事实直接相加成单一因果贡献。

## 4. 建模阶段剩余事项

建模主线已封板，不再把以下增强项作为进入论文写作的阻塞项：

- IAV 官方历史环比；
- 海关原油进口单位价值；
- 印度扩展样本；
- Polymarket / 预测市场；
- CGE、DSGE、TFT/LSTM、GNN 等 Innovation Track。

这些内容只可作为附录或赛后扩展，不应再改动当前冻结主线与已完成的 Q4 拓展。
