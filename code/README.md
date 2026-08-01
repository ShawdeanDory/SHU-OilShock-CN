# 代码目录

后续阶段按问题拆分：

```text
code/
├── data_download/
├── data_processing/
├── problem1/
├── problem2/
├── problem3/
├── problem4/
└── utils/
```

当前四个模块均已进入可复跑状态：

- `data_download/p0_sources.json`：P0 免费公开来源的机器可读配置。
- `data_download/download_p0.py`：原始快照下载、版本化浏览器读取快照校验、SHA-256 与来源登记。
- `data_download/README.md`：安全配置和运行方式。
- `problem1/run_q1.py`：预测、事件 CAR、结构冲击和波动分析。
- `problem2/run_q2.py`：中国宏观动态响应。
- `problem3/run_q3.py`：跨国比较与政策关闭反事实。
- `problem4/run_q4.py`：问题四的尾部风险、统一基线回测和宏观政策压力测试。
- `problem4/run_q4_sapr.py`：问题四的 SAPR-CVaR 自适应调价规则优化、Pareto 筛选、检验样本策略比较和 2026 情景路径。

德国、法国、意大利、西班牙、日本、韩国零售燃油价格均已进入处理层，NBS IAV/PPI 和中国官方受管制燃油价格序列也已补齐。Q1/Q2/Q3 与自拟问题四的风险探针和冻结验证均为 `PASS`。
