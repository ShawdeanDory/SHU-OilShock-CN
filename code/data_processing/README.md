# P0 数据处理

从 `data/raw/source_manifest.json` 读取已经校验的原始快照：

```powershell
python code/data_processing/build_p0_datasets.py
```

国家统计局人工导出的 PPI 与规模以上工业增加值 CSV 先运行：

```powershell
python code/data_processing/import_nbs_manual.py `
  --ppi data/raw/manual/nbs_ppi_monthly_2010_202606.csv `
  --iav data/raw/manual/nbs_iav_monthly_2010_202606.csv `
  --download-date 2026-07-31
```

该脚本生成 `nbs_ppi_monthly.csv`、`nbs_iav_monthly.csv` 和原始文件哈希元数据。PPI 从“上年同月=100”转换为同比百分点；工业增加值官方春节合并发布造成的空值保持为空，不做插值。

脚本不会插值缺失值，也不会使用 2026-06-30 之后的观测。主要产物：

- `data/processed/p0_daily_market.csv`
- `data/processed/p0_monthly_market.csv`
- `data/processed/eia_steo_selected.csv`
- `data/processed/oecd_g20_cpi_monthly.csv`
- `data/processed/oecd_kei_ip_monthly.csv`
- `data/processed/germany_eurosuper95_weekly.csv`
- `data/processed/germany_eurosuper95_monthly.csv`
- `data/processed/japan_regular_gasoline_weekly.csv`
- `data/processed/japan_regular_gasoline_monthly.csv`
- `data/processed/korea_regular_gasoline_monthly.csv`
- `data/processed/cn_fuel_policy_events.csv`
- `data/processed/release_date_matrix.csv`
- `data/processed/dataset_profile.csv`
- `reports/DATA_QUALITY_REPORT.md`

STEO 当前版本只覆盖 2022 年起并混合历史、估计与预测值。脚本保留 `vintage_date` 和 `data_status`，不会把它静默并入 2010 年起的主面板。

完成处理后运行独立校验：

```powershell
python code/data_processing/validate_p0.py
```

校验器会重新计算所有原始快照的 SHA-256，并检查核心时间范围、主键、跨国样本量、人民币油价换算、政策差额和 STEO 截止规则。
