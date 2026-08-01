"""Verify the standard numerical freeze and the project reproducibility manifest."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "results"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
SCHEMA_DIR = REPO_ROOT / "code" / "schemas"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

STANDARD_FROZEN_REQUIRED = [
    "schema_version",
    "frozen_at",
    "source_file",
    "source_sha256",
    "values",
]
MANIFEST_REQUIRED = [
    "schema_version",
    "snapshot_mode",
    "overall_status",
    "paper_finalize_allowed",
    "git_commit",
    "source_commit",
    "cutoff",
    "random_seed",
    "replay_environment",
    "packaging_environment",
    "code_hashes",
    "processed_input_hashes",
    "core_result_hashes",
    "risk_gate_hash",
    "final_numbers_source_sha256",
    "standard_freeze_file",
    "manifest_hash",
]
RISK_REQUIRED = [
    "schema_version",
    "overall_status",
    "paper_finalize_allowed",
    "cutoff",
    "random_seed",
    "probes",
    "blocking_probe_ids",
    "core_results_present",
    "figure_pngs",
    "output_hash_count",
    "input_hash_count",
    "model_code_hash_count",
]


def sha256_file(path: Path) -> str:
    payload = path.read_bytes()
    if path.suffix.lower() in {".csv", ".json", ".md", ".py", ".txt"}:
        payload = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(payload).hexdigest()


def sha256_json(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require_keys(payload: dict[str, Any], keys: list[str], label: str, errors: list[str]) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        errors.append(f"{label} missing required keys: {missing}")


def validate_schema(payload: dict[str, Any], schema_filename: str, label: str, errors: list[str]) -> None:
    schema_path = SCHEMA_DIR / schema_filename
    if not schema_path.exists():
        errors.append(f"{label} schema missing: {schema_filename}")
        return
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema)
    schema_errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.path))
    for error in schema_errors:
        location = ".".join(str(part) for part in error.path) or "<root>"
        errors.append(f"{label} schema error at {location}: {error.message}")


def verify_source_commit_lineage(frozen: dict[str, Any], errors: list[str]) -> None:
    source_commit = frozen.get("source_commit")
    if not source_commit or source_commit == "UNKNOWN":
        errors.append("frozen source_commit is missing or UNKNOWN")
        return
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", source_commit, "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"current HEAD does not contain frozen source_commit {source_commit}")


def verify_hashes(base_dir: Path, hashes: dict[str, str], label: str, errors: list[str]) -> None:
    for filename, expected in hashes.items():
        path = base_dir / filename
        if not path.exists():
            errors.append(f"{label} file missing: {filename}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            errors.append(f"{label} hash mismatch: {filename}")


def bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series
    return series.astype(str).str.lower().isin(["true", "1", "yes"])


def verify_environment(manifest: dict[str, Any], messages: list[str]) -> None:
    env = manifest.get("replay_environment", {})
    if env.get("python_version") != platform.python_version():
        messages.append(f"replay python mismatch: required={env.get('python_version')} current={platform.python_version()}")
    packages = env.get("packages", {})
    for package, manifest_version in packages.items():
        try:
            current = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            current = "NOT_INSTALLED"
        if current != manifest_version:
            messages.append(f"replay package mismatch: {package} required={manifest_version} current={current}")


def verify_key_result_shapes(errors: list[str]) -> None:
    q1_metrics = pd.read_csv(RESULTS_DIR / "q1_forecast_metrics.csv")
    required_q1 = {"model", "horizon", "relative_RMSE_vs_no_change", "model_status"}
    if not required_q1.issubset(q1_metrics.columns):
        errors.append("q1_forecast_metrics.csv lacks forecast gate columns")
    else:
        advanced_pass = q1_metrics.loc[q1_metrics["model"].ne("no_change") & q1_metrics["model_status"].eq("PASS")]
        advanced_worse = q1_metrics.loc[q1_metrics["model"].ne("no_change") & q1_metrics["relative_RMSE_vs_no_change"].gt(1.0)]
        if not advanced_pass.merge(advanced_worse[["model", "horizon"]], on=["model", "horizon"], how="inner").empty:
            errors.append("advanced Q1 model with RMSE worse than no-change is still marked PASS")

    q1_events = pd.read_csv(RESULTS_DIR / "q1_event_effects.csv")
    empirical = pd.to_numeric(
        q1_events.loc[q1_events["model"].eq("brent_usd_bbl_event_car"), "pvalue_empirical"],
        errors="coerce",
    ).dropna()
    if empirical.empty or not empirical.between(0.0, 1.0, inclusive="right").all() or empirical.eq(0.0).any():
        errors.append("Q1 empirical placebo p-values are missing, outside (0, 1], or still report zero")

    q1_origin = pd.read_csv(RESULTS_DIR / "q1_origin_forecast.csv")
    origin_horizons = sorted(pd.to_numeric(q1_origin.get("horizon_months", pd.Series(dtype=float)), errors="coerce").dropna().astype(int).tolist())
    if origin_horizons != [1, 3, 6]:
        errors.append("q1_origin_forecast.csv must contain exactly 1/3/6 month horizons")
    six_month = q1_origin.loc[q1_origin["horizon_months"].eq(6)]
    if six_month.empty or not six_month["forecast_status"].astype(str).eq("FORECAST_ONLY").all():
        errors.append("Q1 2026-08 six-month origin forecast must be retained and marked FORECAST_ONLY")

    q1_svar = pd.read_csv(RESULTS_DIR / "q1_svar_diagnostics.csv")
    selected = q1_svar.loc[q1_svar.get("is_selected", pd.Series(dtype=bool)).astype(str).str.lower().isin(["true", "1"])]
    if len(selected) != 1 or not selected["is_stable"].astype(str).str.lower().isin(["true", "1"]).all():
        errors.append("q1_svar_diagnostics.csv must identify exactly one selected stable VAR specification")

    q2_irf = pd.read_csv(RESULTS_DIR / "q2_irf.csv")
    q2_metrics = pd.read_csv(RESULTS_DIR / "q2_transmission_metrics.csv")
    iav_horizons = sorted(pd.to_numeric(q2_irf.loc[q2_irf["outcome"].eq("china_iav_yoy_pct"), "horizon"], errors="coerce").dropna().astype(int).unique().tolist())
    if iav_horizons != [0, 3, 6, 12]:
        errors.append("Q2 IAV response horizons must be the pre-specified 0/3/6/12 grid")
    if q2_metrics.empty or not {"evidence_status", "allows_growth_loss_language", "cumulative_response_0_6", "cumulative_response_0_12"}.issubset(q2_metrics.columns):
        errors.append("q2_transmission_metrics.csv lacks required transmission-metric columns")

    q3_pass = pd.read_csv(RESULTS_DIR / "q3_country_pass_through.csv")
    required_q3 = {"price_measure_type", "observed_or_regulated", "included_in_main_comparison", "comparability_note"}
    if not required_q3.issubset(q3_pass.columns):
        errors.append("q3_country_pass_through.csv lacks comparability columns")
    else:
        chn_rows = q3_pass.loc[q3_pass["country"].eq("CHN")]
        chn_included = bool_series(chn_rows["included_in_main_comparison"]) if not chn_rows.empty else pd.Series(dtype=bool)
        chn_proxy = chn_rows["price_measure_type"].astype(str).str.contains("proxy", case=False, na=False) if not chn_rows.empty else pd.Series(dtype=bool)
        if bool((chn_included & chn_proxy).any()):
            errors.append("China proxy is included in the main Q3 fuel comparison")
        if chn_rows.empty or not bool(chn_included.any()):
            errors.append("China official regulated fuel series is not included in the main Q3 comparison")

    q3_buffer = pd.read_csv(RESULTS_DIR / "q3_buffer_interactions.csv")
    required_buffer = {"outcome", "buffer", "shock", "estimate", "lower_95", "upper_95", "specification"}
    if not required_buffer.issubset(q3_buffer.columns):
        errors.append("q3_buffer_interactions.csv lacks policy-buffer interaction columns")
    required_buffers = {"fuel_price_regulation", "oil_import_dependency", "oil_intensity", "import_source_hhi"}
    if not required_buffers.issubset(set(q3_buffer.get("buffer", pd.Series(dtype=str)).dropna().unique())):
        errors.append("q3_buffer_interactions.csv must include all four planned buffer variables")

    q3_panel = pd.read_csv(RESULTS_DIR / "q3_panel_irf.csv")
    if "reference_country" not in q3_panel.columns or not q3_panel["reference_country"].astype(str).eq("CHN").all():
        errors.append("q3_panel_irf.csv must use China as the explicit reference country")
    if "response_type" not in q3_panel.columns or not q3_panel["response_type"].astype(str).str.contains("control_country_minus_china", na=False).all():
        errors.append("q3_panel_irf.csv must report control-country-minus-China relative responses")

    q3_resilience = pd.read_csv(RESULTS_DIR / "q3_resilience_metrics.csv")
    required_dimensions = {"fuel_pass_through", "cpi_peak_response", "industrial_activity_trough", "policy_counterfactual_macro"}
    if q3_resilience.empty or not required_dimensions.issubset(set(q3_resilience.get("dimension", pd.Series(dtype=str)).dropna().unique())):
        errors.append("q3_resilience_metrics.csv lacks required resilience dimensions")

    policy = pd.read_csv(RESULTS_DIR / "q3_policy_counterfactual.csv")
    april = policy.loc[policy["period"].eq("2026-04")]
    if april.empty:
        errors.append("q3_policy_counterfactual.csv lacks 2026-04 row")
    else:
        incremental = float(april["incremental_gasoline_gap_cny_t"].iloc[0])
        cumulative = float(april["cumulative_gasoline_gap_cny_t"].iloc[0])
        if abs(incremental - 380.0) > 1e-6 or abs(cumulative - 1425.0) > 1e-6:
            errors.append("Q3 April policy gap no longer matches incremental 380 and cumulative 1425")
    if "price_layer_status" not in policy.columns:
        errors.append("q3_policy_counterfactual.csv lacks price_layer_status")

    policy_macro = pd.read_csv(RESULTS_DIR / "q3_policy_macro_counterfactual.csv")
    macro_outcomes = set(policy_macro.get("outcome", pd.Series(dtype=str)).dropna().unique())
    if not {"china_ppi_yoy_pct", "china_cpi_yoy_pct", "china_iav_yoy_pct"}.issubset(macro_outcomes):
        errors.append("q3_policy_macro_counterfactual.csv must include PPI/CPI/IAV propagated paths")
    if not {"lower_95", "upper_95", "macro_counterfactual_gap_pctpt"}.issubset(policy_macro.columns):
        errors.append("q3_policy_macro_counterfactual.csv lacks macro interval columns")

    q3_kernel = pd.read_csv(RESULTS_DIR / "q3_policy_macro_kernel.csv")
    q3_cov = pd.read_csv(RESULTS_DIR / "q3_policy_macro_covariance.csv")
    kernel_outcomes = set(q3_kernel.get("outcome", pd.Series(dtype=str)).dropna().unique())
    if not {"china_ppi_yoy_pct", "china_cpi_yoy_pct", "china_iav_yoy_pct"}.issubset(kernel_outcomes):
        errors.append("q3_policy_macro_kernel.csv must expose PPI/CPI/IAV macro kernels for Q4 SAPR")
    required_kernel_cols = {f"beta_fuel_lag{i}" for i in range(7)} | {"phi_outcome_lag1"}
    if q3_kernel.empty or not required_kernel_cols.issubset(q3_kernel.columns):
        errors.append("q3_policy_macro_kernel.csv lacks usable coefficient columns")
    if q3_cov.empty or not {"outcome", "row_term", "column_term", "covariance"}.issubset(q3_cov.columns):
        errors.append("q3_policy_macro_covariance.csv lacks covariance matrix columns")

    q4_risk = pd.read_csv(RESULTS_DIR / "q4_price_tail_risk.csv")
    q4_backtest = pd.read_csv(RESULTS_DIR / "q4_risk_backtest.csv")
    if set(q4_risk.get("model", pd.Series(dtype=str)).dropna().unique()) != {"FHS_GJR_GARCH", "Gaussian_random_walk"}:
        errors.append("q4_price_tail_risk.csv must include both FHS_GJR_GARCH and Gaussian_random_walk")
    q4_horizons = sorted(pd.to_numeric(q4_risk.get("horizon_months", pd.Series(dtype=float)), errors="coerce").dropna().astype(int).unique().tolist())
    if q4_horizons != [1, 3, 6]:
        errors.append("q4_price_tail_risk.csv must report 1/3/6 month horizons")
    if q4_backtest.empty or not {"origins", "all_no_future_information", "mean_pinball_loss"}.issubset(q4_backtest.columns):
        errors.append("q4_risk_backtest.csv lacks backtest integrity columns")
    elif not bool_series(q4_backtest["all_no_future_information"]).all():
        errors.append("Q4 tail-risk backtest uses future information")

    q4_sapr_scenarios = pd.read_csv(RESULTS_DIR / "q4_sapr_scenarios.csv")
    q4_sapr_grid = pd.read_csv(RESULTS_DIR / "q4_sapr_policy_grid.csv")
    q4_sapr_optimal = pd.read_csv(RESULTS_DIR / "q4_sapr_optimal_rule.csv")
    q4_sapr_comparison = pd.read_csv(RESULTS_DIR / "q4_sapr_strategy_comparison.csv")
    q4_sapr_paths = pd.read_csv(RESULTS_DIR / "q4_sapr_macro_paths.csv")
    q4_sapr_sensitivity = pd.read_csv(RESULTS_DIR / "q4_sapr_sensitivity.csv")
    q4_sapr_summary = load_json(RESULTS_DIR / "q4_sapr_summary.json")

    q4_dev = q4_sapr_scenarios.loc[q4_sapr_scenarios["sample_split"].eq("development")]
    q4_holdout = q4_sapr_scenarios.loc[q4_sapr_scenarios["sample_split"].eq("holdout")]
    if q4_dev.empty or q4_holdout.empty:
        errors.append("q4_sapr_scenarios.csv must include development and holdout scenarios")
    else:
        if str(q4_dev["source_end"].max()) > "2021-12":
            errors.append("Q4 SAPR development scenarios leak post-2021 data")
        if str(q4_holdout["source_start"].min()) < "2022-01":
            errors.append("Q4 SAPR holdout scenarios overlap the development period")
    if int(bool_series(q4_sapr_scenarios.get("is_2026_anchor", pd.Series(dtype=bool))).sum()) == 0:
        errors.append("q4_sapr_scenarios.csv lacks the 2026 anchor scenario")
    if len(q4_sapr_grid) != 1771:
        errors.append("q4_sapr_policy_grid.csv must contain exactly 1771 monotone rules")
    if int(bool_series(q4_sapr_grid.get("is_knee", pd.Series(dtype=bool))).sum()) != 1:
        errors.append("q4_sapr_policy_grid.csv must identify exactly one knee rule")
    if q4_sapr_optimal.empty or len(q4_sapr_optimal) != 1:
        errors.append("q4_sapr_optimal_rule.csv must contain exactly one optimal rule")
    else:
        opt = q4_sapr_optimal.iloc[0]
        if not (float(opt["rho_normal"]) >= float(opt["rho_stress"]) >= float(opt["rho_extreme"])):
            errors.append("Q4 SAPR optimal pass-through rates violate monotonicity")
    required_sapr_strategies = {"full_mechanism", "uniform_75_smoothing", "temporary_2026_approx", "SAPR_CVaR_knee"}
    holdout_strategies = set(q4_sapr_comparison.loc[q4_sapr_comparison["sample_split"].eq("holdout"), "strategy"].dropna())
    war_strategies = set(q4_sapr_comparison.loc[q4_sapr_comparison["sample_split"].eq("war_2026"), "strategy"].dropna())
    if not required_sapr_strategies.issubset(holdout_strategies):
        errors.append("q4_sapr_strategy_comparison.csv lacks required holdout strategies")
    if not required_sapr_strategies.issubset(war_strategies):
        errors.append("q4_sapr_strategy_comparison.csv lacks required 2026-war strategies")
    interval_cols = [
        "J1_macro_loss_lower_95",
        "J1_macro_loss_upper_95",
        "J2_cvar95_macro_loss_lower_95",
        "J2_cvar95_macro_loss_upper_95",
    ]
    if not set(interval_cols).issubset(q4_sapr_comparison.columns):
        errors.append("q4_sapr_strategy_comparison.csv lacks uncertainty interval columns")
    elif not np.isfinite(q4_sapr_comparison[interval_cols].apply(pd.to_numeric, errors="coerce").to_numpy()).all():
        errors.append("Q4 SAPR strategy intervals contain non-finite values")
    if q4_sapr_paths.empty or not {"strategy", "sample_split", "month_index", "cumulative_deferred_gap_cny_t"}.issubset(q4_sapr_paths.columns):
        errors.append("q4_sapr_macro_paths.csv lacks required macro-path columns")
    if len(q4_sapr_sensitivity) < 6:
        errors.append("q4_sapr_sensitivity.csv must include threshold, block-length, CPI-weight and IAV-weight variants")
    if q4_sapr_summary.get("execution_status") != "PASS":
        errors.append("q4_sapr_summary.json execution_status must be PASS")
    if q4_sapr_summary.get("evidence_status") not in {"SUPPORTED", "PARTIAL", "NOT_SUPPORTED"}:
        errors.append("q4_sapr_summary.json has invalid evidence_status")
    if int(q4_sapr_summary.get("valid_parameter_draw_count", 0)) != 2000:
        errors.append("Q4 SAPR must retain exactly 2000 valid parameter draws")
    if float(q4_sapr_summary.get("valid_parameter_draw_rate", 0.0)) < 0.95:
        errors.append("Q4 SAPR valid parameter draw rate is below 95%")
    identity = q4_sapr_summary.get("identity_checks", {})
    if abs(float(identity.get("official_2026_03_gap", 0.0)) - 1045.0) > 1e-6:
        errors.append("Q4 SAPR official 2026-03 policy gap must equal 1045 CNY/t")
    if abs(float(identity.get("official_2026_04_gap", 0.0)) - 380.0) > 1e-6:
        errors.append("Q4 SAPR official 2026-04 incremental policy gap must equal 380 CNY/t")
    if abs(float(identity.get("official_2026_04_cumulative_gap", 0.0)) - 1425.0) > 1e-6:
        errors.append("Q4 SAPR official 2026-04 cumulative policy gap must equal 1425 CNY/t")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-final", action="store_true", help="Return nonzero unless the risk gate allows paper finalization.")
    parser.add_argument("--strict-environment", action="store_true", help="Treat replay-environment differences as errors.")
    args = parser.parse_args()

    errors: list[str] = []
    environment_messages: list[str] = []
    final_path = RESULTS_DIR / "final_numbers.json"
    frozen_path = RESULTS_DIR / "frozen_numbers.json"
    risk_path = RESULTS_DIR / "risk_probe_summary.json"
    manifest_path = RESULTS_DIR / "reproducibility_manifest.json"

    final_numbers = load_json(final_path)
    frozen = load_json(frozen_path)
    risk = load_json(risk_path)
    manifest = load_json(manifest_path)

    require_keys(frozen, STANDARD_FROZEN_REQUIRED, "frozen_numbers.json", errors)
    require_keys(manifest, MANIFEST_REQUIRED, "reproducibility_manifest.json", errors)
    require_keys(risk, RISK_REQUIRED, "risk_probe_summary.json", errors)
    validate_schema(frozen, "frozen_numbers.schema.json", "frozen_numbers.json", errors)
    validate_schema(manifest, "reproducibility_manifest.schema.json", "reproducibility_manifest.json", errors)
    validate_schema(risk, "risk_probe_summary.schema.json", "risk_probe_summary.json", errors)

    expected_source_hash = sha256_json(final_numbers)
    if frozen.get("schema_version") != 1:
        errors.append(f"frozen_numbers.json schema_version must be 1, got {frozen.get('schema_version')!r}")
    if frozen.get("source_file") != "results/final_numbers.json":
        errors.append("frozen_numbers.json source_file is not results/final_numbers.json")
    if frozen.get("source_sha256") != expected_source_hash:
        errors.append("frozen_numbers.json source_sha256 does not match final_numbers.json")
    if frozen.get("values") != final_numbers:
        errors.append("frozen_numbers.json values do not match final_numbers.json")

    manifest_source = {key: manifest[key] for key in MANIFEST_REQUIRED if key != "manifest_hash" and key in manifest}
    if manifest.get("manifest_hash") != sha256_json(manifest_source):
        errors.append("manifest_hash does not match canonical reproducibility manifest")
    if manifest.get("risk_gate_hash") != sha256_file(risk_path):
        errors.append("risk_gate_hash does not match risk_probe_summary.json")
    if manifest.get("final_numbers_source_sha256") != expected_source_hash:
        errors.append("manifest final_numbers_source_sha256 does not match final_numbers.json")

    verify_hashes(RESULTS_DIR, manifest.get("core_result_hashes", {}), "result", errors)
    verify_hashes(PROCESSED_DIR, manifest.get("processed_input_hashes", {}), "processed input", errors)
    verify_hashes(REPO_ROOT, manifest.get("code_hashes", {}), "code", errors)
    verify_environment(manifest, errors if args.strict_environment else environment_messages)
    verify_source_commit_lineage(manifest, errors)
    verify_key_result_shapes(errors)

    probe_status = {probe.get("probe_id"): probe.get("status") for probe in risk.get("probes", [])}
    required_probe_ids = {
        "q4_method_risk_probe_gate",
        "q4_probability_calibration_gate",
        "q4_evidence_layer_guardrail",
        "q4_sapr_scenario_no_leakage_gate",
        "q4_sapr_macro_kernel_gate",
        "q4_sapr_policy_identity_gate",
        "q4_sapr_pareto_selection_gate",
        "q4_sapr_holdout_validation_gate",
        "q4_sapr_uncertainty_gate",
        "q4_sapr_claim_strength_gate",
    }
    missing_probe_ids = sorted(required_probe_ids - set(probe_status))
    if missing_probe_ids:
        errors.append(f"risk_probe_summary.json lacks Q4 probe ids: {missing_probe_ids}")
    failed_probe_ids = sorted(pid for pid in required_probe_ids if probe_status.get(pid) != "PASS")
    if failed_probe_ids:
        errors.append(f"Q4 probe ids are not PASS: {failed_probe_ids}")

    if risk.get("paper_finalize_allowed") != (risk.get("overall_status") == "PASS"):
        errors.append("risk paper_finalize_allowed is inconsistent with overall_status")
    if manifest.get("paper_finalize_allowed") != risk.get("paper_finalize_allowed"):
        errors.append("manifest paper_finalize_allowed differs from risk gate")
    if manifest.get("overall_status") != risk.get("overall_status"):
        errors.append("manifest overall_status differs from risk gate")

    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors, "environment_warnings": environment_messages}, ensure_ascii=False, indent=2))
        return 1
    if args.require_final and not risk.get("paper_finalize_allowed"):
        print(
            json.dumps(
                {
                    "status": risk.get("overall_status"),
                    "paper_finalize_allowed": False,
                    "blocking_probe_ids": risk.get("blocking_probe_ids", []),
                    "environment_warnings": environment_messages,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": risk.get("overall_status"),
                "paper_finalize_allowed": risk.get("paper_finalize_allowed"),
                "environment_warnings": environment_messages,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
