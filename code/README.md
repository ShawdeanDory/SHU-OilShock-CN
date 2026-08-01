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
- `problem4/run_q4.py`：自拟拓展的尾部风险、统一基线回测和宏观政策压力测试。

德国、法国、意大利、西班牙、日本、韩国零售燃油价格均已进入处理层，NBS IAV/PPI 和中国官方受管制燃油价格序列也已补齐。Q1/Q2/Q3 与 Q4 拓展的风险探针和冻结验证均为 `PASS`。
