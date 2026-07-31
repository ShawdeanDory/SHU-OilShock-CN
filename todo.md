# 待办事项

> 同事接手提示（2026-07-31）：当前仓库代码和远端 `origin/main` 已同步到提交 `5112fe8`。模型框架、图表中文化、风险探针和冻结校验已经完成一轮修复；当前正式状态仍是 `CONDITIONAL`，不是论文定稿状态。不要为了“显著”而改模型，下一步只补真实数据与价格口径，让门禁自然判断是否可定稿。

## A. 接手优先级与当前状态

### A1. 当前可直接复用的阶段成果

- [x] Q1 预测部分已允许 no-change 合法胜出；ARIMA/SARIMAX/ETS/Theta 等高级模型不胜基线只作为实证结果记录，不再错误阻塞。
- [x] Q1 事件窗口已改为交易日口径：E1 即时窗口从 2026-03-02 开始，正式推断使用 CAR 与经验 placebo 分布。
- [x] Q1 “无战争反事实”已降级为 `AR基准情景路径 / ARBaselineGap`，不再表述为严格战争净因果贡献。
- [x] Q1 已新增结构冲击接口与 GJR-GARCH 波动模块。
- [x] Q2 已改为结构冲击主接口，并输出逐期区间、联合区间、FDR 与 `SUPPORTED / INCONCLUSIVE / UNSUPPORTED` 证据状态。
- [x] Q2 当前结论是 `INCONCLUSIVE`：可以说“尚未发现稳健总体增长损失证据”，不能说“油价冲击显著造成中国增长损失”。
- [x] Q3 已扩展为中国、德国、法国、意大利、西班牙、日本、韩国七国面板；中国 Brent-CNY 代理燃油价已退出主燃油排名。
- [x] Q3 已加入政策缓冲交互项，但中国主比较仍缺官方受管制成品油价格序列。
- [x] 图表读者可见英文已中文化，保留 ARIMA、SARIMAX、GPR、CPI、PPI、LP、HAC 等通用缩写。
- [x] `results/frozen_numbers.json`、`results/reproducibility_manifest.json` 和 `results/risk_probe_summary.json` 已可被 schema 与哈希验证。

### A2. 当前三个定稿阻塞项

- [ ] **P0 / Q2 数据完整性**：补齐国家统计局工业增加值 IAV 与 PPI 月度历史，解决 `q2_nbs_macro_completeness_gate`。
- [ ] **P0 / Q3 中国可比性**：重建中国官方受管制成品油价格连续序列，使中国能进入 Q3 主燃油传导比较，解决 `q3_china_comparability`。
- [ ] **P0 / Q3 政策价格层**：把中国政策反事实从 Brent-CNY 代理层改为官方成品油价格层，解决 `q3_policy_counterfactual_price_layer`。

### A2.1 NBS IAV/PPI 数据补齐任务包

- [ ] 从国家统计局“国家数据”或可核验官方发布页导出 2010-01 至 2026-06 工业增加值与 PPI 月度历史。
- [ ] 生成或更新 `data/processed/nbs_iav_monthly.csv`，建议字段：
  `period, china_iav_yoy_pct, china_iav_mom_sa_pct, period_aggregation, release_date, vintage_date, source_url`。
- [ ] 生成或更新 `data/processed/nbs_ppi_monthly.csv`，建议字段：
  `period, china_ppi_yoy_pct, base_note, release_date, vintage_date, source_url`。
- [ ] 处理 1—2 月合并发布：合并同比值只写入 2 月，`period_aggregation=jan_feb_cumulative`；1 月保留缺失，不插值。
- [ ] 在 `data/raw/source_manifest.csv` 和 `data/raw/source_manifest.json` 中记录来源 URL、下载/导出日期、SHA-256、缓存状态。
- [ ] 修改 `code/data_processing/build_model_panels.py` 或相邻处理脚本，使 `model_monthly_cn.csv` 和 `model_country_monthly.csv` 中真正出现非空的中国 IAV/PPI 字段。
- [ ] 重跑 Q2 后检查 `results/q2_summary.json`：数据完整性阻塞项应消失；即使结果仍不显著，也可以作为正式“不显著/不确定”结果。

### A2.2 NDRC 中国成品油价格任务包

- [ ] 从国家发改委成品油价格公告档案整理 2013 至 2026 年逐次调价、不调价、暂停/延迟/缩小调价公告。
- [ ] 生成 `data/processed/cn_fuel_adjustment_events.csv`，至少包含：
  `announcement_date, effective_date, product, actual_adjustment_cny_per_ton, rule_implied_adjustment_cny_per_ton, carried_gap_cny_per_ton, policy_type, source_url`。
- [ ] 生成 `data/processed/china_regulated_gasoline_monthly.csv`，至少包含：
  `period, china_regulated_gasoline_index, china_regulated_gasoline_cny_per_ton, measure_type, source_url`。
- [ ] 不再用 `Brent-CNY - 政策差额` 当作中国主燃油价格；该代理值只允许保留在附录敏感性分析。
- [ ] 将 2026 年 3 月、4 月临时调控的 1045 和 380 元/吨作为“机制应调—实际调价”的政策缺口，不从原油成本价格层直接相减。
- [ ] 重跑 Q3 后检查 `results/q3_country_pass_through.csv`：中国应以 `observed_or_regulated` 官方受管制价格进入主比较，`included_in_main_comparison=true`。
- [ ] 重跑政策反事实后检查 `results/q3_policy_counterfactual.csv`：4 月应同时保留“新增 380 元/吨”和“累计 1425 元/吨”，并在官方成品油价格层上传播到 CPI/IAV。

### A3. 接手后建议的最短执行顺序

1. 先补 NBS 工业增加值与 PPI 月度表，形成可审计的处理后 CSV。
2. 重跑数据处理、Q2、冻结校验；确认 Q2 至少从“数据缺失型 CONDITIONAL”变为“可回答但可能 INCONCLUSIVE”。
3. 再补 NDRC 成品油调价公告序列，构造中国官方受管制汽油/柴油价格指数。
4. 重跑数据处理、Q3、冻结校验；确认中国进入主燃油传导比较，且政策反事实在官方成品油价格层上计算。
5. 只有 `results/risk_probe_summary.json` 中 `overall_status=PASS` 且 `paper_finalize_allowed=true` 时，才开始锁定论文正文数值。

### A4. 推荐重跑命令

在仓库根目录执行：

```powershell
python code\data_processing\build_p0_datasets.py
python code\data_processing\validate_p0.py
python code\data_processing\build_model_panels.py
python code\problem1\run_q1.py
python code\problem2\run_q2.py
python code\problem3\run_q3.py
python code\utils\freeze_results.py
python code\utils\verify_freeze.py
python code\utils\verify_freeze.py --require-final
```

说明：当前 `--require-final` 应该失败并列出三个阻塞项；补齐数据前不要把这个失败当成程序错误。

### A5. 接手时不要做的事

- [ ] 不要把高级预测模型调参到强行战胜 no-change；no-change 胜出是允许的数学建模结果。
- [ ] 不要把 2026-03-02 之后的实际收益放进 Q1 事件期正常收益预测路径。
- [ ] 不要把 Brent-CNY 代理价格与其他国家观测零售价直接排名。
- [ ] 不要用插值伪造 NBS 1 月工业增加值或 PPI；1—2 月合并口径必须显式标注。
- [ ] 不要在风险探针非 `PASS` 时把论文写成定稿口吻。

## 0. 项目与口径

- [x] 确认项目名称和 GitHub 仓库
- [x] 确认中文 LaTeX 排版
- [x] 确认只使用免费公开数据
- [x] 确认主样本观测截止日为 2026-06-30
- [x] 确认比赛提交日为 2026-08-01
- [x] 选择 B 档平衡建模方案
- [x] 锁定月度主线、日度事件补充和季度 GDP 验证
- [x] 锁定 Brent 主口径和 1、3、6 个月预测期
- [x] 锁定 Q3 三个评价指标
- [x] 锁定德国、法国、意大利、西班牙、日本、韩国为主对照；中国代理燃油价不进主排名

## 1. 赛题分析与建模设计 - `2analysis-modeling`

- [x] 提取题面并确认共有 3 个子问题
- [x] 完成题意、关键歧义和数据需求分析
- [x] 整理文献路线和文献矩阵
- [x] 确定每问的主方法、可用基线和失败回退
- [x] 设计每问的方法风险探针
- [x] 明确三问变量接口
- [x] 建立多阶段战争与政策事件表
- [x] 完成 P0 数据源逐项可访问性检查
- [x] 将最终变量字典与下载接口核对到字段级
- [x] 用无需账号的 KOSIS 官方月表替代韩国 Opinet 密钥方案
- [ ] 手工导出国家统计局工业增加值、PPI，并核验 1 月口径
- [x] 用浏览器下载并核验日本普通汽油历史 Excel
- [x] 检查海关总署 2026 月度原油进口量值表入口（匿名访问会进入登录，保留为验证条件项）

## 2. 编程实现和图表生成 - `3coding-visual`

### 数据

- [x] 编写 P0 免费公开数据下载脚本
- [x] 保存原始文件、来源 URL、下载日期和校验值
- [x] 建立规则级 release-date matrix，并识别 STEO 单一版本泄漏风险
- [ ] 补齐模型所需变量的逐期实际发布日期或保守滞后规则
- [x] 在下载与处理脚本中区分 EIA STEO 历史、估计与预测区间
- [x] 保存并校验韩国 KOSIS 2010-01 至 2026-06 普通汽油月度快照
- [x] 生成 P0 市场月度面板和日度市场数据
- [x] 合并现有公开宏观数据和事件阶段，生成阶段性建模面板（六个对照国燃油价格已完成；NBS IAV/PPI 待补）
- [x] 输出数据质量报告并通过独立校验

### 风险探针

- [x] 运行 Q1 no-change/高级模型、事件 CAR、placebo、结构冲击和波动探针
- [x] 运行 Q2 LP、ARDL、GDP 验证和结论强度探针
- [x] 运行 Q3 跨国可比性、面板、缓冲交互和规则反事实探针
- [x] 写入 `results/risk_probe_summary.json`
- [x] 执行已触发的回退：Q1 选择 no-change；Q2 保持 `CONDITIONAL/INCONCLUSIVE`；Q3 中国代理值退出主排名

### 完整实现

- [x] Q1：no-change/随机游走与 ARIMAX/SARIMAX/ETS/Theta 滚动预测
- [x] Q1：多阶段日度事件研究、递归 AR 基准情景路径和 CAR/placebo 推断
- [x] Q1：WTI 与 GJR-GARCH 波动稳健性
- [x] Q2：ARDL 基线
- [x] Q2：Local Projection 及 0—12 月响应
- [x] Q2：sign-asymmetry DL 与季度 GDP 验证
- [x] Q3：分国传导率基线
- [x] Q3：跨国面板 LP 与政策缓冲交互
- [x] Q3：中国临时调控关闭代理情景
- [x] Q3：逐个删除对照国稳健性
- [x] 生成 `reports/RESULTS_REPORT.md`
- [x] 生成论文数据图表 PDF
- [x] 写入 `results/final_numbers.json`
- [x] 生成并检查 `results/frozen_numbers.json`
- [x] 生成并检查 `results/reproducibility_manifest.json`

### 当前阻塞项

- [ ] 补齐国家统计局工业增加值、PPI 月度历史后重跑 Q2
- [ ] 重建中国官方受管制成品油价格连续序列，使中国进入 Q3 主燃油比较
- [ ] 将政策反事实从 Brent-CNY 代理层改为官方成品油价格层
- [ ] 风险门禁全部 `PASS` 后允许论文数值定稿

## 3. 流程与架构图 - `4drawio`

- [ ] 绘制三问统一技术路线图
- [ ] 绘制战争冲击多阶段时间线
- [ ] 绘制油价到中国经济的传导机制图
- [ ] 绘制中国临时调控关闭反事实流程
- [ ] 导出论文可引用 PDF
- [ ] 生成 `reports/DRAWIO_REPORT.md`

## 4. 论文撰写 - `5writing`

- [ ] 确认校赛官方 LaTeX 版式要求
- [ ] 创建 `paper/main.tex`、章节和参考文献文件
- [ ] 写作前检查冻结数值
- [ ] 撰写问题重述、假设、符号、数据和模型
- [ ] 插入最终图表和结果表
- [ ] 撰写摘要、模型评价、局限和参考文献
- [ ] 使用 XeLaTeX 连续编译两遍

## 5. 最终验收 - `6verity`

- [ ] 生成 `reports/CONSISTENCY_AUDIT.md`
- [ ] 生成 `reports/COMPLETENESS_AUDIT.md`
- [ ] 生成 `reports/QUALITY_AUDIT.md`
- [ ] 检查冻结数值、正文、表格和图注一致
- [ ] 检查三个子问题、基线、探针和稳健性完整
- [ ] 检查引用、路径、匿名信息、占位符和提交文件
- [ ] 生成 `reports/VERIFY_REPORT.md`
- [ ] 三重审计全部通过后提交
