# 国际油价三问阶段性建模结果报告

## Material Passport

- Origin Skill: `academic-research-suite / experiment-agent`
- Execution Mode: `goal`
- Verification Status: `ANALYZED`
- Cutoff: `2026-06-30`
- Random Seed: `20260730`

## 1. 总体结论

本轮已经完成三问主线的可复现结果冻结：Q1 生成油价预测、战争事件冲击和月度 `OilShock` 接口；Q2 在中国 IAV/PPI 历史处理层暂缺的情况下，完成 CPI、汇率与季度 GDP 验证；Q3 完成日德韩真实零售汽油价格传导、中国 proxy 价格层反事实和跨国 panel LP。

关键边界：所有观测截止于 `2026-06-30`；IAV/PPI 暂未进入正式估计；中国燃油零售价使用 Brent-CNY 加 NDRC 政策差额的 proxy，不作为真实零售价格声称。

## 2. Q1 预测与战争冲击

月度预测评估保留 no-change、ARIMA 和 SARIMAX，未按显著性或好看程度筛选。

| model | horizon | n | MAE | RMSE | direction_accuracy | coverage_80 | coverage_95 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ARIMA | 1.0000 | 78.0000 | 0.0892 | 0.1437 | 0.5974 | 0.8590 | 0.9231 |
| SARIMAX | 1.0000 | 78.0000 | 0.0910 | 0.1442 | 0.5844 | 0.8590 | 0.9231 |
| no_change | 1.0000 | 78.0000 | 0.0914 | 0.1408 | 0.5584 | 0.8718 | 0.9231 |
| ARIMA | 3.0000 | 78.0000 | 0.1785 | 0.2977 | 0.5584 | 0.8205 | 0.8974 |
| SARIMAX | 3.0000 | 78.0000 | 0.1768 | 0.2938 | 0.5455 | 0.8205 | 0.8974 |
| no_change | 3.0000 | 78.0000 | 0.1657 | 0.2660 | 0.4935 | 0.8205 | 0.8846 |
| ARIMA | 6.0000 | 78.0000 | 0.2314 | 0.3432 | 0.4805 | 0.8077 | 0.9231 |
| SARIMAX | 6.0000 | 78.0000 | 0.2313 | 0.3394 | 0.4935 | 0.7949 | 0.9231 |
| no_change | 6.0000 | 78.0000 | 0.2207 | 0.3082 | 0.5455 | 0.7821 | 0.8974 |

战争事件效应采用日度 AR(3)+美元收益率与阶段 dummy，标准误为 Newey-West；WTI 和 2025 placebo 作为稳健性/负对照。

| model | stage_id | estimate_log_return | std_error | lower_95 | upper_95 | pvalue | n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| brent_placebo_2025 | E1 | -0.0091 | 0.0024 | -0.0138 | -0.0043 | 0.0002 | 531.0000 |
| brent_placebo_2025 | E2 | 0.0011 | 0.0036 | -0.0060 | 0.0081 | 0.7612 | 531.0000 |
| brent_placebo_2025 | E3 | -0.0119 | 0.0070 | -0.0256 | 0.0018 | 0.0892 | 531.0000 |
| brent_usd_bbl_stage_dummy | E1 | 0.0000 | 0.0000 | -0.0000 | 0.0000 | 0.0968 | 531.0000 |
| brent_usd_bbl_stage_dummy | E2 | 0.0067 | 0.0065 | -0.0059 | 0.0194 | 0.2957 | 531.0000 |
| brent_usd_bbl_stage_dummy | E3 | -0.0150 | 0.0045 | -0.0239 | -0.0062 | 0.0009 | 531.0000 |
| wti_usd_bbl_stage_dummy | E1 | 0.0000 | 0.0000 | -0.0000 | 0.0000 | 0.8365 | 497.0000 |
| wti_usd_bbl_stage_dummy | E2 | 0.0047 | 0.0054 | -0.0060 | 0.0154 | 0.3901 | 497.0000 |
| wti_usd_bbl_stage_dummy | E3 | -0.0087 | 0.0047 | -0.0179 | 0.0006 | 0.0656 | 497.0000 |

## 3. Q2 中国宏观传导

ARDL 基线使用 `OilShock` 的 0-6 阶滞后、结果变量一阶滞后、美元、GPR、月份季节项和疫情阶段。由于 IAV/PPI 缺历史处理层，本轮正式月度输出聚焦 CPI 与汇率。

| outcome | term | estimate | std_error | lower_95 | upper_95 | n |
| --- | --- | --- | --- | --- | --- | --- |
| china_cpi_yoy_pct | cumulative_lag0_6 | 0.1792 | 0.0764 | 0.0295 | 0.3289 | 190.0000 |
| china_cpi_yoy_pct | long_run_multiplier | 2.9574 |  |  |  | 190.0000 |
| china_cpi_yoy_pct | short_run_lag0 | 0.0178 | 0.0287 | -0.0384 | 0.0740 | 190.0000 |
| china_fx_log_change_pct | cumulative_lag0_6 | 0.0520 | 0.1343 | -0.2112 | 0.3152 | 190.0000 |
| china_fx_log_change_pct | long_run_multiplier | 0.0833 |  |  |  | 190.0000 |
| china_fx_log_change_pct | short_run_lag0 | 0.0711 | 0.0517 | -0.0302 | 0.1724 | 190.0000 |

Local Projection 生成 h=0..12 的响应，下表只展示 h=0/6/12 以便开题汇报。

| outcome | horizon | response | std_error | lower_95 | upper_95 | n |
| --- | --- | --- | --- | --- | --- | --- |
| china_cpi_yoy_pct | 0.0000 | 0.0189 | 0.0303 | -0.0555 | 0.0876 | 195.0000 |
| china_cpi_yoy_pct | 6.0000 | 0.1049 | 0.0787 | -0.0992 | 0.3002 | 189.0000 |
| china_cpi_yoy_pct | 12.0000 | 0.0932 | 0.0788 | -0.1184 | 0.2558 | 183.0000 |
| china_fx_log_change_pct | 0.0000 | 0.0674 | 0.0555 | -0.0816 | 0.1605 | 195.0000 |
| china_fx_log_change_pct | 6.0000 | 0.3567 | 0.2226 | -0.3289 | 0.6423 | 189.0000 |
| china_fx_log_change_pct | 12.0000 | 0.5996 | 0.3952 | -0.7634 | 1.1070 | 183.0000 |

季度 GDP 验证不把 GDP 插值到月度。

| outcome | estimate | std_error | correlation | n | sample_start | sample_end |
| --- | --- | --- | --- | --- | --- | --- |
| china_real_gdp_yoy_pct | 0.6643 | 0.3806 | 0.3540 | 65.0000 | 2010-Q2 | 2026-Q2 |

## 4. Q3 政策缓冲与跨国比较

燃油价格传导采用各国本币 Brent 到汽油价格的 0-6 月 distributed lag。日德韩为官方零售燃油价格，中国为 policy-adjusted Brent-CNY proxy。

| country | horizon | response | std_error | lower_95 | upper_95 | fuel_source |
| --- | --- | --- | --- | --- | --- | --- |
| CHN | 6.0000 | 0.6395 | 0.0525 | 0.5365 | 0.7424 | Brent-CNY proxy net of NDRC policy gaps |
| DEU | 6.0000 | 0.2367 | 0.0515 | 0.1358 | 0.3376 | European Commission Weekly Oil Bulletin |
| JPN | 6.0000 | 0.1989 | 0.0386 | 0.1233 | 0.2745 | Japan METI weekly fuel survey monthly average |
| KOR | 6.0000 | 0.2374 | 0.0440 | 0.1513 | 0.3236 | KOSIS / Korea National Oil Corporation monthly gasoline |

中国调价反事实把 2026-03-23 和 2026-04-07 的政策差额加回，先报告价格层，再用中国 proxy fuel ARDL 传播到 CPI。

| period | actual | prediction | response | fuel_log_gap | cpi_counterfactual_gap_pctpt |
| --- | --- | --- | --- | --- | --- |
| 2026-02 | 3589.2274 | 3589.2274 | 0.0000 | 0.0000 | 0.0000 |
| 2026-03 | 4166.2262 | 5211.2262 | 1045.0000 | 0.2238 | 0.4874 |
| 2026-04 | 4454.0946 | 5879.0946 | 1425.0000 | 0.2776 | 0.6045 |
| 2026-05 | 3915.9735 | 5340.9735 | 1425.0000 | 0.3103 | 0.6758 |
| 2026-06 | 2817.2991 | 4242.2991 | 1425.0000 | 0.4093 | 0.8914 |

## 5. 图表与文件

核心图表（PNG）：data_overview_fuel_panel.png, data_overview_oil_gpr.png, q1_forecast_1m.png, q1_war_counterfactual.png, q2_irf.png, q3_panel_irf.png, q3_pass_through_6m.png, q3_policy_counterfactual.png。

冻结数值文件：

- `results/final_numbers.json`
- `results/frozen_numbers.json`
- `results/risk_probe_summary.json`

## 6. Warnings

- `raw_hash_mismatch`：fred_brent_daily SHA-256 mismatch; likely line-ending or refreshed snapshot drift
- `raw_hash_mismatch`：fred_cny_per_usd_daily SHA-256 mismatch; likely line-ending or refreshed snapshot drift
- `raw_hash_mismatch`：fred_jpy_per_usd_daily SHA-256 mismatch; likely line-ending or refreshed snapshot drift
- `raw_hash_mismatch`：fred_krw_per_usd_daily SHA-256 mismatch; likely line-ending or refreshed snapshot drift
- `raw_hash_mismatch`：fred_usd_broad_daily SHA-256 mismatch; likely line-ending or refreshed snapshot drift
- `raw_hash_mismatch`：fred_usd_per_eur_daily SHA-256 mismatch; likely line-ending or refreshed snapshot drift
- `raw_hash_mismatch`：fred_wti_daily SHA-256 mismatch; likely line-ending or refreshed snapshot drift
- `raw_hash_mismatch`：kosis_kr_gasoline_monthly SHA-256 mismatch; likely line-ending or refreshed snapshot drift
- `missing_raw_snapshot`：nbs_cpi_202606_release raw snapshot is absent
- `missing_raw_snapshot`：nbs_gdp_2026q2_release raw snapshot is absent
- `missing_raw_snapshot`：nbs_iav_202606_release raw snapshot is absent
- `missing_raw_snapshot`：nbs_ppi_202606_release raw snapshot is absent
- `missing_raw_snapshot`：ndrc_fuel_control_20260323 raw snapshot is absent
- `missing_raw_snapshot`：ndrc_fuel_control_20260407 raw snapshot is absent
- `missing_raw_snapshot`：oecd_g20_cpi_monthly raw snapshot is absent
- `missing_raw_snapshot`：oecd_kei_ip_monthly raw snapshot is absent
- `nbs_gdp_yoy_manual_supplement`：OECD GY lacks 2026-Q2; GDP yoy=4.3 added from NBS 2026-07-15 release.
- `optional_china_macro_missing`：nbs_iav_monthly.csv absent; Q2 will run available CPI/FX/GDP modules.
- `optional_china_macro_missing`：nbs_ppi_monthly.csv absent; Q2 will run available CPI/FX/GDP modules.
- `china_fuel_price_proxy`：China fuel price uses Brent-CNY tonne proxy adjusted by cumulative NDRC policy gaps; it is not an observed retail gasoline series.

## 7. 论文使用建议

正文主线建议按“Q1 可预测部分与战争溢价分离、Q2 CPI/汇率/GDP 动态响应、Q3 跨国传导与中国政策反事实”组织。不要把中国 proxy 燃油价格解释为观测零售价；它适合回答“如果没有 2026 年两次调控，价格层差额有多大”，不适合声称完整历史零售价格传导。
