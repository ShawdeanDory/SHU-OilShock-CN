# SHU-OilShock-CN

上海大学 2026 年数学建模校赛 A 题“国际油价预测建模”的完整研究与复现仓库。项目围绕国际油价预测、地缘冲突识别、中国宏观经济传导、政策韧性评估与尾部风险优化，形成“预测与识别—宏观传导—政策反事实—风险优化”的四问闭环。仓库包含免费公开数据的处理流程、Q1—Q4 建模代码、冻结结果、论文图表、LaTeX 源码和最终论文 PDF。

> **项目状态：已完成并归档。** 当前版本作为本项目最终协作版本；量化结论以冻结数值和 [`paper/main.pdf`](./paper/main.pdf) 为准，复现与验收状态见 [`reports/VERIFY_REPORT.md`](./reports/VERIFY_REPORT.md)。

## 项目约定

- 论文语言：中文
- 排版引擎：LaTeX
- 数据范围：仅使用免费、可公开访问且允许学术使用的数据
- 主样本观测截止日：2026-06-30（最后一个完整自然月和季度）
- 比赛提交日：2026-08-01
- 任务结构：3 项题面核心任务 + 1 项自拟拓展
- 建模方案：B 档平衡方案
- 当前阶段：Q1—Q4 建模、稳健性检验、数据图表、数值冻结和论文撰写均已完成，项目进入归档状态

题面文件：[A题：国际油价预测建模.docx](./A题：国际油价预测建模.docx)

## 已锁定的研究主线

```text
月度 Brent 扩展窗口预测与 no-change 胜出基线
  + 日度状态匹配事件研究、CAR 与 GJR-GARCH 条件波动
  + 月度递归 SVAR 结构冲击分解
  -> 中国宏观变量 Local Projection 与移动块 bootstrap
  -> 六国燃油价格传导、部分识别与中国动态政策反事实
  -> FHS–GJR-GARCH 尾部路径模拟
  -> SAPR–CVaR 三状态自适应调价与 Pareto 优化
```

需要特别区分：

- 预测模型用于回答油价未来如何变化；当前滚动评估选择 no-change 为主预测。
- 事件研究用于报告事件窗口内的异常变化，AR 基准情景差额不解释为严格战争因果贡献。
- 相关性、预测误差和特征重要性不能单独证明因果关系。

主频率为月度，日度只用于问题一事件证据，季度 GDP 只作问题二验证。问题三主指标为燃油价格传导率、CPI 响应、工业增加值损失与恢复时间；主对照为日本、韩国、德国，印度为扩展样本。

## 目录结构

```text
.
├── A题：国际油价预测建模.docx
├── README.md
├── CONTRIBUTING.md
├── plan.md
├── todo.md
├── data/
│   ├── event_timeline.csv
│   ├── raw/
│   └── processed/
├── code/
│   ├── problem1/ ... problem4/
├── figures/
├── results/
├── reports/
│   └── ANALYSIS_MODELING_REPORT.md
└── paper/
    └── sections/
```

各目录的用途和文件命名规则见目录内的 `README.md`。

## 当前产物

- [最终论文 PDF](./paper/main.pdf)
- [最终验收报告](./reports/VERIFY_REPORT.md)
- [题目分析与建模设计](./reports/ANALYSIS_MODELING_REPORT.md)
- [国际油价建模文献与方法路线](./reports/国际油价建模文献与方法路线.md)
- [国际油价建模文献矩阵](./reports/国际油价建模文献矩阵.csv)
- [三问创新建模推进指南（候选方法库）](./reports/三问创新建模推进指南.md)
- [B 档执行方案](./plan.md)
- [阶段待办清单](./todo.md)
- [战争与政策事件表](./data/event_timeline.csv)
- [结果报告](./reports/RESULTS_REPORT.md)
- [风险探针汇总](./results/risk_probe_summary.json)
- [Q4 尾部风险结果](./results/q4_price_tail_risk.csv)
- [Q4 宏观压力结果](./results/q4_macro_stress.csv)

## 当前门禁与复现

- Q1：no-change 在统一滚动评估中胜出并作为主预测；ARIMA/SARIMAX 保留为未胜基线的解释性对照。
- Q2：国家统计局工业增加值与 PPI 月度历史已进入处理层；官方春节合并发布空值不插值，Q2 四个结果变量已完成重跑。
- Q3：中国 Brent-CNY 构造代理值只用于政策情景，不参与跨国燃油传导主排名。
- Q4：FHS–GJR-GARCH 与高斯随机游走使用统一滚动回测；宏观结构冲击情景与政策关闭反事实分层报告，不作加总。
- 风险门禁：全部 `PASS`，`paper_finalize_allowed=true`。
- `results/frozen_numbers.json` 使用 `3coding-visual` 标准数值冻结格式。
- 风险状态、运行环境以及代码/输入/输出哈希保存在 `results/reproducibility_manifest.json`。

项目级检查：

```powershell
python code/utils/verify_freeze.py
```

该命令会把与锁定回放环境（Python 3.11.9）的差异列为 warning；只有在精确回放环境中才使用 `--strict-environment`。

使用 `3coding-visual` 标准脚本检查数值冻结：

```powershell
python "<SKILL_DIR>/scripts/freeze_results.py" check --source results/final_numbers.json --freeze results/frozen_numbers.json
```

当前技术风险门禁已经全部 `PASS`。论文与结果均已归档；后续若修改数据、模型或量化结论，必须重新执行数值冻结校验和三重审计。

## 免费数据源原则

优先使用能够追溯版本和下载日期的官方来源：

- EIA、OPEC、World Bank、IMF：国际油价、供需、库存和商品价格
- 国家统计局、海关总署、中国人民银行、国家发展改革委：中国宏观、贸易、金融和成品油政策
- OECD Data Explorer：跨国可比的 GDP、CPI、能源 CPI 和工业生产

任何进入模型的数据都应在 `data/README.md` 中记录来源链接、下载日期、时间范围、频率、单位、许可条件和处理脚本。

主样本只使用观测日期不晚于 2026-06-30 的数据。若某个来源存在发布滞后，则使用该日期之前的最新可得观测，并单独记录其实际末期；不得用7月的不完整宏观数据填补6月缺失值。

## 团队协作

1. 从最新 `main` 分支创建任务分支。
2. 一项任务对应一个分支和一个 Pull Request。
3. 数据处理必须可复现，禁止只上传手工修改后的结果表。
4. 模型输出先写入 `results/` 和 `reports/RESULTS_REPORT.md`，再引用到论文。
5. 合并前检查路径、数据来源、随机种子和关键数值一致性。

详细规则见 [CONTRIBUTING.md](./CONTRIBUTING.md)。
