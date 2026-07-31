# 处理后数据

本目录中的文件必须能由 `code/` 中的脚本从 `data/raw/` 完整重建。

处理步骤至少记录：

- 字段重命名与单位换算
- 缺失值和异常值处理
- 日、周、月、季度频率聚合
- 币种和实际价格调整
- 训练、验证和测试区间

当前 P0 数据由以下命令重建：

```powershell
python code/data_processing/build_p0_datasets.py
```

国家统计局人工导出数据由以下命令整理为长表：

```powershell
python code/data_processing/import_nbs_manual.py `
  --ppi data/raw/manual/nbs_ppi_monthly_2010_202606.csv `
  --iav data/raw/manual/nbs_iav_monthly_2010_202606.csv `
  --download-date 2026-07-31
```

对应产物为 `nbs_ppi_monthly.csv`、`nbs_iav_monthly.csv` 和 `nbs_manual_import_metadata.json`。工业增加值官方 1 月及春节合并发布空值保持为空，不插值。

`dataset_profile.csv` 记录覆盖范围、缺失和重复；`release_date_matrix.csv` 记录预测信息集规则。完整结论见 `reports/DATA_QUALITY_REPORT.md`。

跨国燃油价格当前包括德国周/月度、日本周/月度和韩国月度序列。韩国文件 `korea_regular_gasoline_monthly.csv` 来自 KOSIS 表 `TX_31802_A000`，单位为 KRW/litre。

中国成品油价格层由 `code/data_processing/build_model_panels.py` 生成：

- `cn_fuel_adjustment_events.csv`：逐次官方汽油调价事件表，当前先由已核验的 2026 年 3 月、4 月国家发改委/北京市发改委公告生成种子记录；后续补齐 2013-2026 历史公告时沿用同一字段。
- `china_regulated_gasoline_monthly.csv`：北京 92 号汽油最高零售限价按生效天数加权后的月度官方价格路径。该序列是 Q3 中国主燃油比较的唯一正式入口；覆盖不足 48 个非空月份时，中国仍退出主排名，Brent-CNY 代理只保留为附录敏感性分析。
