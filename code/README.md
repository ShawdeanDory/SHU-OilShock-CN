# 代码目录

后续阶段按问题拆分：

```text
code/
├── data_download/
├── data_processing/
├── problem1/
├── problem2/
├── problem3/
└── utils/
```

当前已经开始数据采集阶段：

- `data_download/p0_sources.json`：P0 免费公开来源的机器可读配置。
- `data_download/download_p0.py`：原始快照下载、版本化浏览器读取快照校验、SHA-256 与来源登记。
- `data_download/README.md`：安全配置和运行方式。

德国、法国、意大利、西班牙、日本、韩国零售燃油价格均已进入处理层。Q1/Q2/Q3 阶段模型、风险探针与冻结验证已经可复跑；当前仍因 NBS IAV/PPI 和中国官方受管制燃油价格序列缺失而保持 `CONDITIONAL`。
