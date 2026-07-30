# P0 数据下载

下载器只访问 `p0_sources.json` 中登记的免费公开来源。默认行为：

- 原始文件写入 `data/raw/`，文件名包含下载日期；
- 同一天已有快照时不覆盖，除非显式使用 `--refresh`；
- 每个文件计算 SHA-256；
- 下载元数据写入 `data/raw/_meta/`；
- 汇总登记写入 `data/raw/source_manifest.csv` 和 `.json`；
- 任何密钥只从环境变量读取，不打印、不写入仓库。
- KOSIS 韩国燃油价为版本化浏览器读取快照；下载器校验文件头、SHA-256 和固定文件名，不再需要 Opinet 密钥。

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

列出数据源：

```powershell
python code/data_download/download_p0.py --list
```

下载全部自动来源：

```powershell
python code/data_download/download_p0.py
```

只重下指定来源：

```powershell
python code/data_download/download_p0.py --source fred_brent_daily --refresh
```

若以后增加需要密钥的可选来源，密钥只能通过本机环境变量传入，禁止写入脚本、终端截图或 GitHub。
