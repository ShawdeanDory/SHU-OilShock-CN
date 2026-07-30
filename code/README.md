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

德国、日本、韩国零售燃油价格均已进入处理层。正式模型尚未开始；下一步运行数据覆盖与低成本模型风险探针。
