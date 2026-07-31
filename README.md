# SHU-OilShock-CN

上海大学数学建模校赛 A 题协作项目：国际油价预测、战争冲击识别、中国宏观经济传导与政策韧性分析。

## 项目约定

- 论文语言：中文
- 排版引擎：LaTeX
- 数据范围：仅使用免费、可公开访问且允许学术使用的数据
- 主样本观测截止日：2026-06-30（最后一个完整自然月和季度）
- 比赛提交日：2026-08-01
- 子问题数量：3
- 建模方案：B 档平衡方案
- 当前阶段：三问模型、稳健性、数据图表和数值冻结已完成，风险门禁全部 `PASS`，进入非数据图和论文撰写阶段

题面文件：[A题：国际油价预测建模.docx](./A题：国际油价预测建模.docx)

## 已锁定的研究主线

```text
月度 Brent no-change 基线预测
  + ARIMA/SARIMAX 解释性补充
  + 日度多阶段事件研究和 AR 基准情景差额
  -> 月度中国 Local Projection / ARDL
  -> 跨国价格传导比较
  -> 关闭中国临时调控的反事实
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
├── figures/
├── results/
├── reports/
│   └── ANALYSIS_MODELING_REPORT.md
└── paper/
    └── sections/
```

各目录的用途和文件命名规则见目录内的 `README.md`。

## 当前产物

- [题目分析与建模设计](./reports/ANALYSIS_MODELING_REPORT.md)
- [国际油价建模文献与方法路线](./reports/国际油价建模文献与方法路线.md)
- [国际油价建模文献矩阵](./reports/国际油价建模文献矩阵.csv)
- [三问创新建模推进指南（候选方法库）](./reports/三问创新建模推进指南.md)
- [B 档执行方案](./plan.md)
- [阶段待办清单](./todo.md)
- [战争与政策事件表](./data/event_timeline.csv)
- [阶段性结果报告](./reports/RESULTS_REPORT.md)
- [风险探针汇总](./results/risk_probe_summary.json)

## 当前门禁与复现

- Q1：no-change 在统一滚动评估中胜出并作为主预测；ARIMA/SARIMAX 保留为未胜基线的解释性对照。
- Q2：国家统计局工业增加值与 PPI 月度历史已进入处理层；官方春节合并发布空值不插值，Q2 四个结果变量已完成重跑。
- Q3：中国 Brent-CNY 构造代理值只用于政策情景，不参与跨国燃油传导主排名。
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

当前风险门禁已经全部 `PASS`；论文写作必须继续只引用已冻结数值，并在完成后执行最终三重审计。

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
