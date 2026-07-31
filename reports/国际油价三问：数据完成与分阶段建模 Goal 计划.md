# 国际油价三问：数据完成与分阶段建模 Goal 计划

## Material Passport

- Origin Skill: `academic-research-suite / experiment-agent`
- Origin Mode: `plan`
- Verification Status: `UNVERIFIED`
- Version Label: `oilshock_goal_plan_v1`

## 1. Goal 与执行原则

**Goal objective：** 在不让可选数据或复现检查阻塞主线的前提下，补齐核心建模数据，完成三个原题的基线、主模型、稳健性、图表与冻结结果。

当前问题不全由防御性编程造成：

- Git 自动换行转换和 `.gitignore` 与 manifest 不一致属于配置缺陷；
- 校验器把这些非建模问题升级为全流程失败，属于门禁过强。

后续采用“最小数值校验”：

- 只硬性检查日期不越过 `2026-06-30`、关键列存在、时间顺序正确、模型输入输出为有限数值、无未来信息泄漏；
- SHA、精确行数、固定末期值、可选数据缺失只写入 warning，不中止建模；
- 单个模型失败只记录错误，其他模型和子问题继续运行；
- 不伪造缺失值、不插值月度 GDP、不用未来真实外生变量预测历史；
- 模型不优于基线也照常保存，不通过换窗口或删结果制造成功。

## 2. 分阶段执行

### Stage 0：立即解除非必要阻塞

与 Stage 1、Stage 2 并行完成，不等待其结束才建模。

- 增加 `.gitattributes`，令 `data/raw/** -text`，防止 Git 修改原始字节。
- 将 `validate_p0.py` 改为诊断器：哈希、缺失快照和固定行数输出 warning；仅解析失败、主键重复、截止日期越界和核心数值非有限时返回失败。
- 不重新审计已经生成的全部 P0 数据；直接使用当前 `data/processed/` 开始模型工作。
- 将所有 warning 汇总到 `results/data_warnings.json`。

### Stage 1：生成正式建模面板

新增 `code/data_processing/build_model_panels.py`，一次生成：

| 面板 | 主要内容 |
| --- | --- |
| `model_daily_q1.csv` | Brent、WTI、汇率、收益率、战争阶段 |
| `model_monthly_q1.csv` | Brent、库存、美元、GPR、汇率 |
| `model_monthly_cn.csv` | Q1 冲击、中国 IAV、PPI、CPI、汇率 |
| `model_quarterly_cn.csv` | GDP 与季度聚合油价冲击 |
| `model_country_monthly.csv` | 中日韩德燃油价、本币 Brent、CPI、工业活动 |

并行补充三类数据：

1. 从国家统计局取得 2010-01—2026-06 工业增加值同比、可得的环比季调序列和 PPI 同比；1 月保持缺失或使用官方 1—2 月联合口径，不自行插值。
2. 整理季度实际 GDP 增速至 2026-Q2。
3. 从国家发改委历史公告构造中国汽油、柴油调价月度链式指数，完整记录实际调幅、机制调幅和政策差额；汽油为主口径，柴油作稳健性。

若 IAV/PPI 暂时未取得，Q1 和 Q3 价格传导照常运行；Q2 先运行 CPI、汇率和季度 GDP，数据到位后增量补跑。

停止追逐以下非必要数据：历史 STEO vintage、实际进口单位价值、印度、能源 CPI 和付费数据库。

### Stage 2：问题一——预测与战争冲击

新增 `code/problem1/run_q1.py`。

**月度预测：**

- 目标：月均 Brent 对数价格。
- 预测期：1、3、6 个月。
- 评估期：2020-01—2026-06，采用 expanding-window rolling origin。
- 基线：no-change 和无外生变量 ARIMA。
- 主模型：SARIMAX；`p,q∈{0,1,2}`、`d=1`，外生变量为美国商业库存、美元指数、GPR，均按当时可用信息滞后。
- 多步预测所需未来外生变量采用预测起点值持平，不使用未来真实值。
- 指标：MAE、RMSE、方向准确率、80%/95% 区间覆盖率。

**日度战争模块：**

- 用 2024-01-01—2026-02-27 估计 AR(3)+美元收益率模型；
- 对 E1 冲突开始、E2 海峡中断、E3 缓和阶段生成递归 AR 基准情景路径；
- 估计阶段 dummy 与 Newey–West 区间；
- 使用战前匹配日期做负对照；
- EGARCH 或 WTI 替代只作稳健性。

**跨问接口：**

- `q1_forecasts.csv`
- `q1_event_effects.csv`
- `q1_monthly_shocks.csv`

其中结构冲击为 Q2/Q3 主输入，`OilShock` 为约化形式稳健性，`ARBaselineGap` 为实际与 AR 基准情景路径的描述性月度价格缺口。

### Stage 3：问题二——中国宏观传导

新增 `code/problem2/run_q2.py`。

**ARDL 基线：**

- 结果变量：IAV 同比、PPI 同比、CPI 同比、人民币汇率变化；
- 使用结果变量一阶滞后和 `OilShock` 的 0—6 阶滞后；
- 控制美元指数、GPR、月份季节项和疫情阶段；
- 报告短期、累计和长期效应。

**Local Projection 主模型：**

- horizons：`h=0…12`；
- 利率/同比类结果以百分点响应表示，汇率使用累计对数变化；
- 每个方程控制结果变量与冲击的一阶滞后；
- 标准误使用 Newey–West `maxlags=h+1`；
- 使用 12 个月 moving-block bootstrap 生成区间；
- 正、负油价冲击分解作为 NARDL/非对称稳健性。

**季度验证：**

- 将月度冲击聚合到季度；
- 使用季度实际 GDP 同比做方向与量级验证；
- 不插值为月度 GDP。

输出：

- `q2_ardl_baseline.csv`
- `q2_irf.csv`
- `q2_gdp_validation.csv`
- `q2_summary.csv`

### Stage 4：问题三——跨国比较与政策反事实

新增 `code/problem3/run_q3.py`。

**价格传导基线：**

- 将 Brent 转为人民币、日元、韩元和欧元；
- 对各国分别估计本币 Brent 涨幅至汽油价格的 0—6 月 distributed lag；
- 报告 1、3、6 月累计传导率；
- 汽油为主，柴油或替代窗口为稳健性。

**跨国动态比较：**

- 对燃油价格、CPI 和工业活动分别估计 stacked panel LP；
- 使用国家固定效应、月份季节项、国家趋势和 `OilShock × country`；
- 不加入会与共同油价冲击完全共线的时间固定效应；
- 标准误使用 Driscoll–Kraay；
- 报告中国与日本、韩国、德国的响应差异，而不是强制形成单一排名。

**中国调价反事实：**

- 在 2026-03-23、2026-04-07 将官方政策差额加回实际调幅，构造“未缩小调价”的燃油价格路径；
- 价格层首先报告元/吨与指数差；
- 再通过 Q2 或国内燃油价格 ARDL 的 bootstrap 系数传播到 CPI 和工业活动；
- 宏观弹性不可用时仍输出价格层反事实，不阻塞 Q3。

输出：

- `q3_country_pass_through.csv`
- `q3_panel_irf.csv`
- `q3_policy_counterfactual.csv`
- `q3_summary.csv`

### Stage 5：统一稳健性与结果生成

- Q1：WTI、替代事件窗口、EGARCH、不同滚动起点。
- Q2：滞后 3/6/12、排除疫情、正负冲击、季度 GDP。
- Q3：逐个删除对照国、汽油/柴油、不同汇率口径。
- 所有规格写入同一结果表，正文主规格按预定口径选择，不按显著性选择。
- 生成数据图、预测图、战争反事实图、IRF、跨国传导图和政策反事实图，同时保存 PNG 与 PDF。
- `risk_probe_summary.json` 改为执行摘要，不再作为是否允许继续的门禁。

### Stage 6：结果冻结

新增 `code/utils/freeze_results.py`：

- 从各结果 CSV 自动抽取论文候选数值；
- 生成 `results/final_numbers.json`；
- 完成一次全流程重跑后生成 `results/frozen_numbers.json`；
- 生成 `reports/RESULTS_REPORT.md`，说明模型、样本、主要结果、稳健性和 warning；
- 当前 Goal 在三问结果、图表和冻结数值齐全时完成，不包含完整论文写作。

## 3. 稳定接口与依赖

补充依赖：`numpy`、`scipy`、`statsmodels`、`linearmodels`、`matplotlib`。

所有模型脚本从仓库根目录运行，输入只读 `data/processed/`，输出只写 `results/` 和 `figures/`。公共字段统一使用：

```text
period/date
actual
prediction/response
lower_80 upper_80
lower_95 upper_95
model
horizon
specification
sample_start sample_end
```

所有随机过程使用固定 `random_seed=20260730`。

## 4. 验收场景

- 缺少被忽略的 raw 快照时，打印 warning，但建模面板和模型继续生成。
- IAV/PPI 暂缺时，Q1、Q3 和 Q2 的 CPI/汇率/GDP 模块仍能完成。
- ARIMAX 劣于 no-change 时，两者结果均保留并如实汇总。
- 任一稳健性模型崩溃时，主模型和其他稳健性继续运行。
- 所有训练与预测输入均不晚于预测起点，所有观测不晚于 2026-06-30。
- 三问接口日期、单位和冲击方向一致。
- 相同数据与随机种子重复运行产生相同冻结数值。
- 最终至少存在三问主结果表、三问核心图、`RESULTS_REPORT.md` 和 `frozen_numbers.json`。

## 5. 后续 Innovation Track

不属于本次 Goal 完成条件；三问结果冻结后另建 Goal，研究团队自行提出的新问题：

1. **预测市场信息增量**：Polymarket 概率期限结构能否在 GPR、库存和美元之外提高 Brent 样本外预测？
2. **价格平滑的成本转移**：成品油调控是否只是把居民 CPI 风险转移到企业利润、财政或未来调价？
3. **政策对不同冲击的适配性**：中国缓冲机制对战争信息冲击和物理供应中断是否同样有效？

Innovation Track 必须复用本次冻结的数据和基线；TFT、状态模型、SFC、HJB、MARL 等用于回答这些新增研究问题，不反向拖延原三问主线。
