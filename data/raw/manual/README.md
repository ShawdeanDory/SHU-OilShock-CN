# 人工导出数据

此目录只在本机存放需要登录、验证码或手工导出的原始文件，默认不提交到 GitHub。

计划文件：

- `nbs_iav_monthly_2010_202606.csv`
- `nbs_ppi_monthly_2010_202606.csv`
- `gacc_crude_import_hs2709_monthly_2010_202606.xlsx`（可选验证项；官方政务入口匿名访问会进入登录）

要求：

1. 直接保存官方下载文件，不打开后另存。
2. 不改列名、日期、单位或缺失值。
3. 记录下载页面和下载日期。
4. API 密钥不得放入此目录。

国家统计局 CSV 使用 2010-01 至 2026-06 的完整查询范围。PPI 选择“工业生产者出厂价格指数（上年同月=100）”；工业增加值选择“规上工业增加值同比增长（%）”。工业增加值官方未发布的 1 月以及 2013 年起 1—2 月当月值保持为空，不插值。

导入命令：

```powershell
python code/data_processing/import_nbs_manual.py `
  --ppi data/raw/manual/nbs_ppi_monthly_2010_202606.csv `
  --iav data/raw/manual/nbs_iav_monthly_2010_202606.csv `
  --download-date 2026-07-31
```
