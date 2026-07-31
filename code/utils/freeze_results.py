"""Freeze stage outputs and run paper-finalization risk probes."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
CODE_DIR = REPO_ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from utils.plot_style import PALETTE, apply_paper_style, finish_figure, save_figure, style_axis

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RESULTS_DIR = REPO_ROOT / "results"
FIGURES_DIR = REPO_ROOT / "figures"
REPORTS_DIR = REPO_ROOT / "reports"
CUTOFF = "2026-06-30"
RISK_SCHEMA_VERSION = "1.0"
MANIFEST_SCHEMA_VERSION = "1.0"
STANDARD_FREEZE_SCHEMA_VERSION = 1
RANDOM_SEED = 20260730

CORE_RESULT_FILES = [
    "q1_forecast_metrics.csv",
    "q1_event_effects.csv",
    "q1_placebo_distribution.csv",
    "q1_daily_counterfactual.csv",
    "q1_monthly_shocks.csv",
    "q1_robustness.csv",
    "q1_summary.json",
    "q2_ardl_baseline.csv",
    "q2_irf.csv",
    "q2_gdp_validation.csv",
    "q2_asymmetry.csv",
    "q2_robustness.csv",
    "q2_summary.csv",
    "q2_summary.json",
    "q3_country_pass_through.csv",
    "q3_panel_irf.csv",
    "q3_policy_counterfactual.csv",
    "q3_robustness.csv",
    "q3_summary.csv",
    "q3_summary.json",
]

PROCESSED_INPUT_FILES = [
    "p0_daily_market.csv",
    "p0_monthly_market.csv",
    "model_daily_q1.csv",
    "model_monthly_q1.csv",
    "model_monthly_cn.csv",
    "model_quarterly_cn.csv",
    "model_country_monthly.csv",
    "oecd_g20_cpi_monthly.csv",
    "oecd_kei_ip_monthly.csv",
    "germany_eurosuper95_monthly.csv",
    "japan_regular_gasoline_monthly.csv",
    "korea_regular_gasoline_monthly.csv",
    "cn_fuel_policy_events.csv",
    "china_fuel_policy_monthly.csv",
    "china_fuel_proxy_monthly.csv",
]

CODE_FILES = [
    "code/data_processing/build_model_panels.py",
    "code/problem1/run_q1.py",
    "code/problem2/run_q2.py",
    "code/problem3/run_q3.py",
    "code/schemas/frozen_numbers.schema.json",
    "code/schemas/reproducibility_manifest.schema.json",
    "code/schemas/risk_probe_summary.schema.json",
    "code/utils/freeze_results.py",
    "code/utils/plot_style.py",
    "code/utils/verify_freeze.py",
    "requirements.in",
    "requirements.lock.txt",
]

COUNTRY_LABEL_ZH = {"CHN": "中国（代理）", "DEU": "德国", "JPN": "日本", "KOR": "韩国"}
CORE_PACKAGES = ["numpy", "pandas", "scipy", "statsmodels", "linearmodels", "matplotlib", "requests", "openpyxl", "xlrd"]


def read_csv(filename: str) -> pd.DataFrame:
    path = RESULTS_DIR / filename
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_json(filename: str) -> dict[str, Any]:
    path = RESULTS_DIR / filename
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    payload = path.read_bytes()
    if path.suffix.lower() in {".csv", ".json", ".md", ".py", ".txt"}:
        payload = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(payload).hexdigest()


def sha256_json(payload: dict[str, Any]) -> str:
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def clean_value(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        if not np.isfinite(value):
            return None
        return round(float(value), 8)
    if pd.isna(value):
        return None
    return value


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{key: clean_value(value) for key, value in row.items()} for row in frame.to_dict("records")]


def hash_existing(base_dir: Path, filenames: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for filename in filenames:
        path = base_dir / filename
        if path.exists():
            hashes[filename] = sha256_file(path)
    return hashes


def collect_figures() -> list[str]:
    if not FIGURES_DIR.exists():
        return []
    return sorted(path.name for path in FIGURES_DIR.glob("*.png") if path.name.startswith(("q", "data_")))


def git_commit() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


def environment_snapshot() -> dict[str, Any]:
    packages: dict[str, str] = {}
    for package in CORE_PACKAGES:
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = "NOT_INSTALLED"
    lock_path = REPO_ROOT / "requirements.lock.txt"
    return {
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "packages": packages,
        "requirements_lock_sha256": sha256_file(lock_path) if lock_path.exists() else None,
    }


def replay_environment_snapshot() -> dict[str, Any]:
    lock_path = REPO_ROOT / "requirements.lock.txt"
    lock_text = lock_path.read_text(encoding="utf-8") if lock_path.exists() else ""
    python_version = None
    packages: dict[str, str] = {}
    for line in lock_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# Python:"):
            python_version = stripped.split(":", 1)[1].strip()
        elif stripped and not stripped.startswith("#") and "==" in stripped:
            package, version = stripped.split("==", 1)
            if package.strip().lower() in CORE_PACKAGES:
                packages[package.strip().lower()] = version.strip()
    return {
        "python_version": python_version,
        "packages": packages,
        "requirements_lock_sha256": sha256_file(lock_path) if lock_path.exists() else None,
    }


def probe(
    probe_id: str,
    status: str,
    metric: Any,
    threshold: str,
    evidence_files: list[str],
    message: str,
    severity: str = "blocking",
) -> dict[str, Any]:
    return {
        "probe_id": probe_id,
        "status": status,
        "severity": severity,
        "metric": metric,
        "threshold": threshold,
        "evidence_files": evidence_files,
        "message": message,
    }


def combined_status(probes: list[dict[str, Any]]) -> str:
    statuses = {row["status"] for row in probes}
    if "FAIL" in statuses:
        return "FAIL"
    if "CONDITIONAL" in statuses:
        return "CONDITIONAL"
    return "PASS"


def has_rows(path: Path, minimum: int) -> bool:
    if not path.exists():
        return False
    frame = pd.read_csv(path)
    return len(frame.dropna(how="all")) >= minimum


def bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series
    return series.astype(str).str.lower().isin(["true", "1", "yes"])


def build_risk_probe_summary(output_hashes: dict[str, str], input_hashes: dict[str, str]) -> dict[str, Any]:
    probes: list[dict[str, Any]] = []

    metrics = read_csv("q1_forecast_metrics.csv")
    if metrics.empty or "model_status" not in metrics.columns:
        probes.append(probe("q1_forecast_baseline_gate", "FAIL", "missing model_status", "all forecast metrics carry model_status", ["results/q1_forecast_metrics.csv"], "Q1 forecast metrics cannot prove that advanced models were downgraded."))
    else:
        advanced_non_pass = metrics.loc[metrics["model"].ne("no_change") & metrics["model_status"].ne("PASS")]
        no_change_rows = metrics.loc[metrics["model"].eq("no_change")]
        status = "CONDITIONAL" if not advanced_non_pass.empty else "PASS"
        if no_change_rows.empty:
            status = "FAIL"
        probes.append(
            probe(
                "q1_forecast_baseline_gate",
                status,
                {
                    "selected_model": "no_change",
                    "advanced_non_pass_rows": int(len(advanced_non_pass)),
                    "no_change_rows": int(len(no_change_rows)),
                },
                "no-change rows exist; ARIMA/SARIMAX must be non-PASS when they fail the baseline",
                ["results/q1_forecast_metrics.csv", "results/q1_summary.json"],
                "No-change is selected as the main forecast. ARIMA/SARIMAX are not allowed to claim PASS when they do not beat the baseline.",
            )
        )

    q1_summary = load_json("q1_summary.json")
    event_calendar = q1_summary.get("event_calendar", {})
    event_ok = event_calendar.get("e1_trading_start") == "2026-03-02" and event_calendar.get("e2_trading_start") == "2026-03-05"
    effects = read_csv("q1_event_effects.csv")
    e1_rows = effects.loc[(effects.get("stage_id", pd.Series(dtype=str)).eq("E1")) & effects.get("identification_status", pd.Series(dtype=str)).eq("PASS")] if not effects.empty else pd.DataFrame()
    probes.append(
        probe(
            "q1_event_trading_day_gate",
            "PASS" if event_ok and not e1_rows.empty else "FAIL",
            {"event_calendar": event_calendar, "e1_identified_rows": int(len(e1_rows))},
            "E1 maps to 2026-03-02 and has identifiable nonzero trading observations",
            ["results/q1_event_effects.csv", "results/q1_summary.json"],
            "E1 weekend event has been remapped to the first common trading day and the zero-variance dummy problem is removed.",
        )
    )

    placebos = read_csv("q1_placebo_distribution.csv")
    empirical_p = q1_summary.get("placebo_min_empirical_pvalue")
    if placebos.empty or empirical_p is None or not 0.0 < float(empirical_p) <= 1.0:
        placebo_status = "FAIL"
    else:
        placebo_status = "PASS"
    probes.append(
        probe(
            "q1_placebo_distribution_gate",
            placebo_status,
            {"placebo_rows": int(len(placebos)), "min_empirical_pvalue": empirical_p},
            "matched weekend placebo distribution exists and finite-sample corrected empirical p-values lie in (0, 1]",
            ["results/q1_placebo_distribution.csv", "results/q1_summary.json"],
            "Matched weekend placebo evidence uses the add-one correction, so a finite pseudo-event sample cannot report an empirical p-value of exactly zero.",
        )
    )

    shocks = read_csv("q1_monthly_shocks.csv")
    language_ok = not shocks.empty and "ARBaselineGap" in shocks.columns and "WarPremium" not in shocks.columns
    probes.append(
        probe(
            "q1_counterfactual_language_gate",
            "PASS" if language_ok else "FAIL",
            {"has_ARBaselineGap": bool("ARBaselineGap" in shocks.columns), "has_WarPremium": bool("WarPremium" in shocks.columns)},
            "descriptive AR baseline field exists and old causal premium field is absent",
            ["results/q1_monthly_shocks.csv", "results/q1_daily_counterfactual.csv"],
            "The event-path gap is labeled as ARBaselineGap rather than a war premium or causal no-war contribution.",
        )
    )

    nbs_iav_ok = has_rows(REPO_ROOT / "data" / "processed" / "nbs_iav_monthly.csv", 120)
    nbs_ppi_ok = has_rows(REPO_ROOT / "data" / "processed" / "nbs_ppi_monthly.csv", 120)
    probes.append(
        probe(
            "q2_nbs_macro_completeness_gate",
            "PASS" if nbs_iav_ok and nbs_ppi_ok else "CONDITIONAL",
            {"nbs_iav_monthly": nbs_iav_ok, "nbs_ppi_monthly": nbs_ppi_ok},
            "NBS IAV and PPI monthly histories are present with enough observations",
            ["data/processed/nbs_iav_monthly.csv", "data/processed/nbs_ppi_monthly.csv", "results/q2_summary.json"],
            "Q2 remains conditional until official IAV and PPI histories enter the processed layer; no interpolation is used to fill the gap.",
        )
    )

    q2_summary = load_json("q2_summary.json")
    q2_irf = read_csv("q2_irf.csv")
    q2_guard_ok = (
        q2_summary.get("shock_identification", "").startswith("OilShock is a reduced-form")
        and not q2_irf.empty
        and {"ci95_contains_zero", "fdr_qvalue", "supports_growth_loss_language"}.issubset(q2_irf.columns)
    )
    probes.append(
        probe(
            "q2_claim_strength_gate",
            "PASS" if q2_guard_ok else "FAIL",
            {"irf_rows": int(len(q2_irf)), "guardrail_present": bool(q2_summary.get("conclusion_guardrail"))},
            "LP inference flags and reduced-form shock wording are present",
            ["results/q2_irf.csv", "results/q2_summary.json"],
            "Q2 output distinguishes reduced-form association from structural oil-supply transmission and blocks unsupported growth-loss wording.",
        )
    )

    q3_pass = read_csv("q3_country_pass_through.csv")
    if q3_pass.empty or "included_in_main_comparison" not in q3_pass.columns:
        q3_comp_status = "FAIL"
        q3_metric: Any = "missing comparability fields"
    else:
        chn_main = bool_series(q3_pass.loc[q3_pass["country"].eq("CHN"), "included_in_main_comparison"])
        q3_comp_status = "PASS" if not chn_main.empty and not bool(chn_main.any()) else "FAIL"
        q3_metric = q3_pass[["country", "horizon", "included_in_main_comparison", "price_measure_type"]].to_dict("records")
    probes.append(
        probe(
            "q3_china_proxy_exclusion_gate",
            q3_comp_status,
            q3_metric,
            "China proxy is excluded from the main fuel pass-through comparison",
            ["results/q3_country_pass_through.csv", "data/processed/model_country_monthly.csv"],
            "The Brent-CNY China proxy is retained only as a sensitivity/policy-scenario input, not as main cross-country evidence.",
        )
    )

    q3_policy = read_csv("q3_policy_counterfactual.csv")
    april = q3_policy.loc[q3_policy.get("period", pd.Series(dtype=str)).eq("2026-04")] if not q3_policy.empty else pd.DataFrame()
    policy_ok = False
    policy_metric: dict[str, Any] = {}
    if not april.empty:
        inc = float(april["incremental_gasoline_gap_cny_t"].iloc[0])
        cum = float(april["cumulative_gasoline_gap_cny_t"].iloc[0])
        response = float(april["response"].iloc[0])
        policy_metric = {"april_incremental": inc, "april_cumulative": cum, "april_response": response}
        policy_ok = abs(inc - 380.0) < 1e-6 and abs(cum - 1425.0) < 1e-6 and abs(response - 1425.0) < 1e-6
    probes.append(
        probe(
            "q3_policy_gap_annotation_gate",
            "PASS" if policy_ok else "FAIL",
            policy_metric,
            "April annotation separates incremental 380 from cumulative 1425 CNY/tonne",
            ["results/q3_policy_counterfactual.csv", "figures/q3_policy_counterfactual.png"],
            "Policy scenario fields distinguish incremental and cumulative gaps, matching the revised chart annotation.",
        )
    )

    chart_sources = [
        REPO_ROOT / "code" / "problem1" / "run_q1.py",
        REPO_ROOT / "code" / "problem2" / "run_q2.py",
        REPO_ROOT / "code" / "problem3" / "run_q3.py",
    ]
    old_terms = [
        "Actual Brent",
        "No-war counterfactual",
        "Q1 war-premium counterfactual",
        "USD per barrel",
        "95% interval",
        "Months after oil shock",
        "Cumulative coefficient",
        "Actual proxy",
        "No-control proxy",
        "Data overview:",
    ]
    leftovers: list[str] = []
    for path in chart_sources:
        text = path.read_text(encoding="utf-8")
        leftovers.extend([term for term in old_terms if term in text])
    figures = collect_figures()
    style_source = (REPO_ROOT / "code" / "utils" / "plot_style.py").read_text(encoding="utf-8")
    title_painted = "fig.text(rect[0], 0.965, title" in style_source or "fig.suptitle(" in style_source
    probes.append(
        probe(
            "figure_localization_gate",
            "PASS" if len(figures) >= 8 and not leftovers and not title_painted else "FAIL",
            {
                "figure_pngs": figures,
                "old_visible_terms": sorted(set(leftovers)),
                "large_title_painted_inside_figure": title_painted,
            },
            "eight figure PNGs exist, visible labels are localized, and large titles are left to LaTeX captions",
            ["figures", "code/problem1/run_q1.py", "code/problem2/run_q2.py", "code/problem3/run_q3.py", "code/utils/plot_style.py"],
            "Figure axes and legends are localized to Chinese; large titles are not painted into the figure canvas.",
        )
    )

    lock_path = REPO_ROOT / "requirements.lock.txt"
    env = environment_snapshot()
    lock_text = lock_path.read_text(encoding="utf-8") if lock_path.exists() else ""
    pinned_lines = [line.strip() for line in lock_text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    env_ok = "# Python: 3.11.9" in lock_text and bool(pinned_lines) and all("==" in line for line in pinned_lines)
    probes.append(
        probe(
            "environment_lock_gate",
            "PASS" if env_ok else "CONDITIONAL",
            {
                "target_python_version": "3.11.9",
                "generation_python_version": env["python_version"],
                "exact_package_pins": len(pinned_lines),
                "requirements_lock_sha256": env["requirements_lock_sha256"],
            },
            "Python 3.11.9 and exact dependency lock are recorded",
            ["requirements.in", "requirements.lock.txt"],
            "The replay target is pinned independently of the interpreter used only to package and verify artifacts.",
        )
    )

    hash_ok = len(output_hashes) == len(CORE_RESULT_FILES) and len(input_hashes) >= 10
    probes.append(
        probe(
            "freeze_hash_coverage_gate",
            "PASS" if hash_ok else "FAIL",
            {"output_hash_count": len(output_hashes), "input_hash_count": len(input_hashes)},
            "all core result files and processed model inputs are hashed",
            ["results/reproducibility_manifest.json", "results/frozen_numbers.json"],
            "The reproducibility manifest hashes model outputs and processed inputs, while frozen_numbers.json follows the standard numerical-freeze schema.",
        )
    )

    overall = combined_status(probes)
    return {
        "schema_version": RISK_SCHEMA_VERSION,
        "overall_status": overall,
        "paper_finalize_allowed": overall == "PASS",
        "cutoff": CUTOFF,
        "random_seed": RANDOM_SEED,
        "probes": probes,
        "blocking_probe_ids": [row["probe_id"] for row in probes if row["status"] != "PASS" and row["severity"] == "blocking"],
        "core_results_present": {filename: (RESULTS_DIR / filename).exists() for filename in CORE_RESULT_FILES},
        "figure_pngs": collect_figures(),
        "output_hash_count": len(output_hashes),
        "input_hash_count": len(input_hashes),
    }


def extract_final_numbers() -> dict[str, Any]:
    q1_metrics = read_csv("q1_forecast_metrics.csv")
    q1_events = read_csv("q1_event_effects.csv")
    q1_shocks = read_csv("q1_monthly_shocks.csv")
    q1_robust = read_csv("q1_robustness.csv")
    q2_ardl = read_csv("q2_ardl_baseline.csv")
    q2_irf = read_csv("q2_irf.csv")
    q2_gdp = read_csv("q2_gdp_validation.csv")
    q2_robust = read_csv("q2_robustness.csv")
    q3_pass = read_csv("q3_country_pass_through.csv")
    q3_irf = read_csv("q3_panel_irf.csv")
    q3_policy = read_csv("q3_policy_counterfactual.csv")
    q3_robust = read_csv("q3_robustness.csv")

    final: dict[str, Any] = {"cutoff": CUTOFF, "status_note": "stage snapshot; not a paper-final causal freeze unless risk gate passes", "q1": {}, "q2": {}, "q3": {}}
    if not q1_metrics.empty:
        final["q1"]["selected_forecast_model"] = "no_change"
        final["q1"]["forecast_best_by_rmse"] = records(q1_metrics.sort_values(["RMSE", "MAE"]).head(3))
        final["q1"]["forecast_metrics"] = records(q1_metrics.sort_values(["horizon", "model"]))
    if not q1_events.empty:
        final["q1"]["brent_event_stage_effects"] = records(
            q1_events.loc[q1_events["model"].eq("brent_usd_bbl_stage_dummy")].sort_values("stage_id")
        )
        final["q1"]["brent_event_car"] = records(
            q1_events.loc[q1_events["model"].eq("brent_usd_bbl_event_car")].sort_values("stage_id")
        )
        final["q1"]["wti_robustness_effects"] = records(
            q1_events.loc[q1_events["model"].eq("wti_usd_bbl_stage_dummy")].sort_values("stage_id")
        )
    if not q1_shocks.empty:
        event_months = q1_shocks.loc[q1_shocks["ARBaselineGap"].abs().gt(0)]
        final["q1"]["ar_baseline_gap_months"] = records(event_months[["period", "ARBaselineGap", "ARBaselineGap_days"]])
    if not q1_robust.empty:
        final["q1"]["robustness_rows"] = int(len(q1_robust))
        final["q1"]["robustness_types"] = sorted(q1_robust["robustness_type"].dropna().unique().tolist()) if "robustness_type" in q1_robust else []

    if not q2_ardl.empty:
        final["q2"]["ardl_main"] = records(q2_ardl.sort_values(["outcome", "term"]))
    if not q2_irf.empty:
        final["q2"]["lp_selected_horizons"] = records(
            q2_irf.loc[q2_irf["horizon"].isin([0, 6, 12])].sort_values(["outcome", "horizon"])
        )
    if not q2_gdp.empty:
        final["q2"]["gdp_validation"] = records(q2_gdp)
    if not q2_robust.empty:
        final["q2"]["robustness"] = records(q2_robust.sort_values(["outcome", "lag_max", "exclude_covid"]))

    if not q3_pass.empty:
        main_pass = q3_pass.loc[bool_series(q3_pass["included_in_main_comparison"])] if "included_in_main_comparison" in q3_pass else q3_pass
        final["q3"]["pass_through_h6_main_comparison"] = records(main_pass.loc[main_pass["horizon"].eq(6)].sort_values("country"))
        final["q3"]["china_proxy_sensitivity_h6"] = records(q3_pass.loc[q3_pass["country"].eq("CHN") & q3_pass["horizon"].eq(6)])
    if not q3_irf.empty:
        final["q3"]["panel_lp_selected_horizons"] = records(
            q3_irf.loc[q3_irf["horizon"].isin([0, 6, 12])].sort_values(["outcome", "country", "horizon"])
        )
    if not q3_policy.empty:
        final["q3"]["policy_counterfactual"] = records(q3_policy)
        final["q3"]["policy_max_cumulative_gap_cny_t"] = clean_value(q3_policy["cumulative_gasoline_gap_cny_t"].max())
        final["q3"]["policy_max_cpi_gap_pctpt"] = clean_value(q3_policy["cpi_counterfactual_gap_pctpt"].max())
    if not q3_robust.empty:
        final["q3"]["robustness_rows"] = int(len(q3_robust))
        final["q3"]["robustness_types"] = sorted(q3_robust["robustness_type"].dropna().unique().tolist()) if "robustness_type" in q3_robust else []
    return final


def build_data_overview_figures() -> None:
    apply_paper_style()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    monthly_path = REPO_ROOT / "data" / "processed" / "model_monthly_q1.csv"
    country_path = REPO_ROOT / "data" / "processed" / "model_country_monthly.csv"
    if monthly_path.exists():
        monthly = pd.read_csv(monthly_path, parse_dates=["month_end"])
        fig, ax1 = plt.subplots(figsize=(9.2, 5.1))
        ax1.plot(monthly["month_end"], monthly["brent_usd_bbl"], color=PALETTE["blue"], label="Brent", linewidth=1.8)
        style_axis(ax1, ylabel="Brent，美元/桶")
        ax2 = ax1.twinx()
        ax2.plot(monthly["month_end"], monthly["GPR_z"], color=PALETTE["rose"], alpha=0.82, label="GPR标准化值", linewidth=1.35, linestyle=(0, (4, 2)))
        ax2.set_ylabel("GPR标准化值")
        ax2.tick_params(colors=PALETTE["muted"], length=3.2, width=0.65)
        ax2.spines["right"].set_color(PALETTE["muted"])
        ax2.spines["right"].set_linewidth(0.7)
        ax2.grid(False)
        lines, labels = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines + lines2, labels + labels2, loc="upper left", ncol=2, handlelength=2.8)
        finish_figure(
            fig,
            title="数据概览：Brent 油价与地缘政治风险",
            subtitle="月度 Brent 现货价与标准化 GPR 指数，2010-01 至 2026-06。",
            source="来源：FRED Brent 与 Caldara-Iacoviello GPR 处理面板；由 code/utils/freeze_results.py 生成。",
        )
        save_figure(fig, FIGURES_DIR / "data_overview_oil_gpr")
        plt.close(fig)
    if country_path.exists():
        panel = pd.read_csv(country_path, parse_dates=["month_end"])
        panel = panel.dropna(subset=["fuel_price_local"]).copy()
        panel["fuel_index"] = panel.groupby("country")["fuel_price_local"].transform(lambda s: 100.0 * s / s.iloc[0])
        fig, ax = plt.subplots(figsize=(9.2, 5.1))
        style_map = {
            "CHN": (PALETTE["blue"], "solid"),
            "DEU": (PALETTE["gold"], (0, (4, 2))),
            "JPN": (PALETTE["olive"], (0, (2, 2))),
            "KOR": (PALETTE["rose"], (0, (1, 2))),
        }
        for country, group in panel.groupby("country"):
            color, linestyle = style_map.get(country, (PALETTE["slate"], "solid"))
            ax.plot(group["month_end"], group["fuel_index"], label=COUNTRY_LABEL_ZH.get(country, country), color=color, linestyle=linestyle, linewidth=1.55)
        style_axis(ax, ylabel="指数，2010-01=100")
        ax.legend(loc="upper left", ncol=4, handlelength=2.8)
        finish_figure(
            fig,
            title="数据概览：燃油价格指数",
            subtitle="各国燃油价格序列以 2010-01 为100；中国为 Brent-CNY 政策代理值。",
            source="来源：欧盟周度油价公报、日本METI、韩国KOSIS/KNOC 与中国代理值；由 code/utils/freeze_results.py 生成。",
        )
        save_figure(fig, FIGURES_DIR / "data_overview_fuel_panel")
        plt.close(fig)


def summarize_warnings() -> list[dict[str, Any]]:
    warnings_list: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for filename in ["data_warnings.json", "q1_summary.json", "q2_summary.json", "q3_summary.json", "model_panel_summary.json"]:
        payload = load_json(filename)
        for warning in payload.get("warnings", []):
            row = dict(warning)
            key = (str(row.get("code", "warning")), str(row.get("message", "")))
            if key not in seen:
                row["sources"] = [filename]
                seen[key] = row
                warnings_list.append(row)
            elif filename not in seen[key]["sources"]:
                seen[key]["sources"].append(filename)
        for stage, stage_warnings in payload.get("stage_warnings", {}).items():
            for warning in stage_warnings:
                row = dict(warning)
                source = f"{filename}:{stage}"
                key = (str(row.get("code", "warning")), str(row.get("message", "")))
                if key not in seen:
                    row["sources"] = [source]
                    seen[key] = row
                    warnings_list.append(row)
                elif source not in seen[key]["sources"]:
                    seen[key]["sources"].append(source)
    return warnings_list


def markdown_table(frame: pd.DataFrame, columns: list[str], limit: int = 12) -> str:
    if frame.empty:
        return "_暂无可用结果。_"
    subset = frame.copy()
    for column in columns:
        if column not in subset.columns:
            subset[column] = ""
    subset = subset[columns].head(limit).copy()
    for column in subset.columns:
        if pd.api.types.is_numeric_dtype(subset[column]):
            subset[column] = subset[column].map(lambda value: "" if pd.isna(value) else f"{float(value):.4f}")
        else:
            subset[column] = subset[column].fillna("").astype(str)
    header = "| " + " | ".join(subset.columns) + " |"
    divider = "| " + " | ".join(["---"] * len(subset.columns)) + " |"
    body = []
    for row in subset.to_dict("records"):
        body.append("| " + " | ".join(str(row[column]).replace("\n", " ") for column in subset.columns) + " |")
    return "\n".join([header, divider] + body)


def build_report(risk_summary: dict[str, Any], final_numbers: dict[str, Any], warnings_list: list[dict[str, Any]]) -> str:
    q1_metrics = read_csv("q1_forecast_metrics.csv")
    q1_events = read_csv("q1_event_effects.csv")
    q2_irf = read_csv("q2_irf.csv")
    q2_gdp = read_csv("q2_gdp_validation.csv")
    q3_pass = read_csv("q3_country_pass_through.csv")
    q3_policy = read_csv("q3_policy_counterfactual.csv")
    figures = collect_figures()

    q3_main = q3_pass.loc[bool_series(q3_pass["included_in_main_comparison"])] if not q3_pass.empty and "included_in_main_comparison" in q3_pass else q3_pass
    warning_lines = []
    for warning in warnings_list[:20]:
        warning_lines.append(f"- `{warning.get('code', 'warning')}`：{warning.get('message', '')}")
    if not warning_lines:
        warning_lines.append("- 暂无模型执行 warning。")
    blocker_lines = [f"- `{probe_id}`" for probe_id in risk_summary["blocking_probe_ids"]]
    if not blocker_lines:
        blocker_lines.append("- 无。")

    return f"""# 国际油价三问阶段性建模结果报告

## Material Passport

- Origin Skill: `3coding-visual`
- Execution Mode: `staged modeling audit`
- Verification Status: `{risk_summary['overall_status']}`
- Paper Finalize Allowed: `{str(risk_summary['paper_finalize_allowed']).lower()}`
- Cutoff: `{CUTOFF}`
- Random Seed: `{RANDOM_SEED}`

## 1. 总体结论

本轮结果已经从“可直接定稿”降级为 `CONDITIONAL` 阶段快照。代码、图表和结果可以继续作为建模推进基础，但论文正文不能把当前输出写成严格因果结论。

当前最重要的边界是：问题一预测主模型改为 `no_change`，ARIMA/SARIMAX 只作解释性补充；事件后价格差额改名为 `ARBaselineGap`，不再称战争溢价；问题二的 `OilShock` 是约化形式油价创新；问题三中国燃油 proxy 不参与主跨国燃油传导排名。

阻塞定稿的门禁：

{chr(10).join(blocker_lines)}

## 2. 问题一：预测与事件窗口

月度预测表已经加入相对基线指标和逐模型状态。当前主预测模型是 `no_change`。

{markdown_table(q1_metrics.sort_values(['horizon', 'model']) if not q1_metrics.empty else q1_metrics, ['model', 'horizon', 'RMSE', 'relative_RMSE_vs_no_change', 'dm_hln_pvalue_rmse_loss', 'model_status'])}

E1 已从 2026-02-28 周末映射到 2026-03-02 交易日，同时输出 CAR[0]、CAR[0,+1]、CAR[0,+2] 和匹配周末 placebo 经验 p 值。经验 p 值采用 \\((b+1)/(B+1)\\) 的有限样本修正，不报告严格的 0。

{markdown_table(q1_events.loc[q1_events['model'].isin(['brent_usd_bbl_stage_dummy', 'brent_usd_bbl_event_car'])].sort_values(['model', 'stage_id']) if not q1_events.empty else q1_events, ['model', 'stage_id', 'estimate_log_return', 'std_error', 'lower_95', 'upper_95', 'pvalue', 'pvalue_empirical', 'event_observations'])}

## 3. 问题二：中国宏观传导

Q2 当前只能写为“尚未发现稳健的总体增长损失证据”。IAV/PPI 官方历史序列尚未进入处理层，CPI、汇率和 GDP 结果均需带区间与识别 caveat 报告。

{markdown_table(q2_irf.loc[q2_irf['horizon'].isin([0, 6, 12])].sort_values(['outcome', 'horizon']) if not q2_irf.empty else q2_irf, ['outcome', 'horizon', 'response', 'lower_95', 'upper_95', 'ci95_contains_zero', 'fdr_qvalue', 'shock_identification'])}

季度 GDP 只作低频验证，不插值成月度变量。

{markdown_table(q2_gdp, ['outcome', 'estimate', 'lower_95', 'upper_95', 'pvalue', 'n', 'sample_start', 'sample_end'])}

## 4. 问题三：政策缓冲与跨国比较

跨国燃油主排名现在只纳入德国、日本、韩国的观测官方零售汽油价格。中国 Brent-CNY 代理值保留为政策情景和附录敏感性材料。

{markdown_table(q3_main.loc[q3_main['horizon'].eq(6)].sort_values('country') if not q3_main.empty else q3_main, ['country', 'horizon', 'response', 'lower_95', 'upper_95', 'price_measure_type', 'included_in_main_comparison'])}

中国政策图与数据表已区分新增差额和累计差额，2026-04 的累计差额为 1425 元/吨，4月新增为 380 元/吨。

{markdown_table(q3_policy, ['period', 'policy_adjusted_proxy_cny_t', 'no_temporary_control_proxy_cny_t', 'incremental_gasoline_gap_cny_t', 'cumulative_gasoline_gap_cny_t', 'cpi_counterfactual_gap_pctpt'])}

## 5. 图表与冻结文件

核心 PNG 图表：{', '.join(figures) if figures else '暂无图表'}。

冻结文件：

- `results/final_numbers.json`
- `results/frozen_numbers.json`
- `results/risk_probe_summary.json`
- `results/reproducibility_manifest.json`

其中 `frozen_numbers.json` 遵循 `3coding-visual` 标准冻结格式；风险门禁以及代码、输入、输出文件哈希保存在独立的 reproducibility manifest 中。数值一致性使用标准 skill 脚本检查，项目级文件与环境检查使用 `python code/utils/verify_freeze.py`。

## 6. Warnings

{chr(10).join(warning_lines)}

## 7. 论文使用建议

论文正文应把当前状态写成阶段性结果：第一问主线是“基线预测 + 交易日事件窗口 + 描述性 AR 基准差额”；第二问主线是“约化形式冲击下未发现稳健增长损失证据”；第三问主线是“可比国家零售燃油传导 + 中国政策代理情景”。只有在风险门禁全部 `PASS` 后，才可把冻结文件作为定稿数值来源。
"""


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def standard_freeze_payload(final_numbers: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": STANDARD_FREEZE_SCHEMA_VERSION,
        "frozen_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_file": "results/final_numbers.json",
        "source_sha256": sha256_json(final_numbers),
        "values": final_numbers,
    }


def reproducibility_manifest(
    risk_summary: dict[str, Any],
    final_numbers: dict[str, Any],
    risk_hash: str,
    output_hashes: dict[str, str],
    input_hashes: dict[str, str],
    code_hashes: dict[str, str],
) -> dict[str, Any]:
    source = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "snapshot_mode": "paper_final" if risk_summary["paper_finalize_allowed"] else "stage_snapshot_not_paper_final",
        "overall_status": risk_summary["overall_status"],
        "paper_finalize_allowed": risk_summary["paper_finalize_allowed"],
        "git_commit": git_commit(),
        "cutoff": CUTOFF,
        "random_seed": RANDOM_SEED,
        "replay_environment": replay_environment_snapshot(),
        "packaging_environment": environment_snapshot(),
        "code_hashes": code_hashes,
        "processed_input_hashes": input_hashes,
        "core_result_hashes": output_hashes,
        "risk_gate_hash": risk_hash,
        "final_numbers_source_sha256": sha256_json(final_numbers),
        "standard_freeze_file": "results/frozen_numbers.json",
    }
    manifest = dict(source)
    manifest["manifest_hash"] = sha256_json(source)
    return manifest


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    build_data_overview_figures()

    output_hashes = hash_existing(RESULTS_DIR, CORE_RESULT_FILES)
    input_hashes = hash_existing(REPO_ROOT / "data" / "processed", PROCESSED_INPUT_FILES)
    code_hashes = hash_existing(REPO_ROOT, CODE_FILES)
    risk_summary = build_risk_probe_summary(output_hashes, input_hashes)
    risk_path = RESULTS_DIR / "risk_probe_summary.json"
    write_json(risk_path, risk_summary)
    risk_hash = sha256_file(risk_path)

    final_numbers = extract_final_numbers()
    final_path = RESULTS_DIR / "final_numbers.json"
    write_json(final_path, final_numbers)

    frozen_path = RESULTS_DIR / "frozen_numbers.json"
    frozen = standard_freeze_payload(final_numbers)
    write_json(frozen_path, frozen)

    manifest = reproducibility_manifest(risk_summary, final_numbers, risk_hash, output_hashes, input_hashes, code_hashes)
    manifest_path = RESULTS_DIR / "reproducibility_manifest.json"
    write_json(manifest_path, manifest)

    warnings_list = summarize_warnings()
    report = build_report(risk_summary, final_numbers, warnings_list)
    (REPORTS_DIR / "RESULTS_REPORT.md").write_text(report.rstrip() + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "status": risk_summary["overall_status"],
                "paper_finalize_allowed": risk_summary["paper_finalize_allowed"],
                "source_sha256": frozen["source_sha256"],
                "manifest_hash": manifest["manifest_hash"],
                "blocking_probe_ids": risk_summary["blocking_probe_ids"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
