# 待办事项：建模封板后论文接手

当前状态（2026-08-01）：原题三问与自拟问题四的建模、门禁和冻结已完成。

- `overall_status=PASS`
- `paper_finalize_allowed=true`
- `blocking_probe_ids=[]`
- `verify_freeze.py --require-final` 已通过

## A. 已完成，可直接用于论文

- [x] Q1 no-change 主预测、ARIMA/SARIMAX/ETS/Theta 对照、DM-HLN 与相对 RMSE/MAE。
- [x] Q1 2026-02 原点 1/3/6 月预测表，其中 2026-08 为 `FORECAST_ONLY`。
- [x] Q1 E1 周末事件映射至 2026-03-02，输出 CAR[0]、CAR[0,+1]、CAR[0,+2] 与匹配 placebo 经验 p 值。
- [x] Q1 `ARBaselineGap` 已替代旧“战争溢价/无战争反事实”表述。
- [x] Q1 历史 SVAR 结构冲击覆盖 186 个月，诊断文件完整。
- [x] Q1 GJR-GARCH 阶段波动汇总已输出。
- [x] Q2 IAV/PPI/CPI/汇率/人民币原油成本进入月度面板。
- [x] Q2 IAV 固定输出 0、3、6、12 月期限，不插值 1 月。
- [x] Q2 传导指标表 `results/q2_transmission_metrics.csv` 已输出。
- [x] Q3 中国官方受管制汽油标准品价格进入主燃油比较，覆盖 160 个月。
- [x] Q3 七国燃油、CPI、工业活动面板已生成；西班牙 CPI 使用 Eurostat fallback。
- [x] Q3 面板 LP 已改为对照国相对中国响应差。
- [x] Q3 四类缓冲变量和交互结果已输出。
- [x] Q3 政策关闭反事实已传播至 PPI、CPI、IAV。
- [x] Q4 FHS–GJR-GARCH 与高斯随机游走完成统一滚动回测。
- [x] Q4 生成 1、3、6 个月尾部概率、历史结构冲击分位宏观压力和政策缓冲表。
- [x] Q4 风险探针通过，固定种子精确复现，替代种子概率扰动有限。
- [x] Q4 两张论文数据图已生成，并保持 Q1/Q2/Q3 三层证据不可加总的结论边界。
- [x] Q4 SAPR-CVaR 自适应调价规则已与尾部风险/压力测试合并为正式问题四，不另设其他自拟问题。
- [x] Q4 SAPR 情景库完成 2013-03—2021-12 开发样本与 2022-01—2026-06 检验样本隔离，2026 冲击只用于检验展示。
- [x] Q4 SAPR 枚举 1771 组三档单调传导规则，输出 Pareto 前沿、唯一膝点、策略比较、2026 路径和敏感性结果。
- [x] 中文图表已重新生成。
- [x] `results/final_numbers.json`、`results/frozen_numbers.json`、`results/risk_probe_summary.json`、`results/reproducibility_manifest.json` 已冻结并验证。
- [x] `reports/paper_numbers.csv` 与 `reports/MODELING_TO_PAPER_HANDOFF.md` 已生成。

## B. 论文撰写必须完成

- [x] 根据 `reports/MODELING_TO_PAPER_HANDOFF.md` 搭建论文结构。
- [x] 从 `reports/paper_numbers.csv` 抽取正文数字，禁止手工重新计算或从中间表随意挑数。
- [ ] 写摘要：突出“预测基线胜出、事件 CAR 显著、Q2 增长损失不稳健、Q3 综合 PARTIAL”。
- [x] 写问题一：区分预测、事件关联、ARBaselineGap 描述性基准差额和波动检验。
- [x] 写问题二：按“人民币原油成本—PPI—CPI/IAV—GDP 验证”组织，不写成显著增长损失。
- [x] 写问题三：说明中国燃油传导率并不低于六国中位数，但 CPI/工业活动和政策反事实支持“部分缓冲”。
- [x] 写问题四：先说明条件尾部概率、结构冲击压力和已实现政策缓冲，再给出 SAPR-CVaR 三档传导率、检验样本策略比较和 2026 情景路径；不写成确定性预测或全球最优政策。
- [x] 从现有 PNG/PDF 中选择约 10 张核心图，并用论文图注解释证据边界。
- [x] 引用 `国际油价建模文献与方法路线.md` 和文献矩阵中的正式文献。
- [x] 在“模型评价”中说明数据源限制：EastMoney 历史调价表为公开数据中心镜像，2026 临时调控缺口由 NDRC/北京发改委公告核验。
- [x] XeLaTeX 编译两遍，检查中文字体、表格溢出、图号和参考文献。

## C. 最终提交前验证

在仓库根目录运行：

```powershell
python code\utils\verify_freeze.py --require-final
```

必须返回：

```json
{
  "status": "PASS",
  "paper_finalize_allowed": true
}
```

然后检查：

- [x] 论文正文所有数值均能在 `reports/paper_numbers.csv` 或 `results/final_numbers.json` 找到。
- [x] 正文没有“战争净因果贡献”“显著增长损失”“中国全面优于”“尾部概率等于确定结果”“SAPR全球最优或完整福利收益”等过度表述。
- [x] 图表标题、坐标轴、图例均为中文；ARIMA、SARIMAX、GPR、CPI、PPI、LP、HAC 等缩写可保留。
- [x] 附录说明 Polymarket 等 Innovation Track 未进入原三问主证据链。

## D. 不再阻塞建模封板的增强项

- [ ] 国家统计局 IAV 历史环比。
- [ ] 海关原油进口单位价值。
- [ ] 印度扩展样本。
- [ ] Polymarket 预测市场数据。
- [ ] CGE/DSGE/TFT/LSTM/GNN 等复杂增强模型。

这些只允许作为附录或团队自拟问题，不能再改动当前冻结主线数字。
