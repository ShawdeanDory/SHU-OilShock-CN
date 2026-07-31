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

    q3_pass = pd.read_csv(RESULTS_DIR / "q3_country_pass_through.csv")
    required_q3 = {"price_measure_type", "observed_or_regulated", "included_in_main_comparison", "comparability_note"}
    if not required_q3.issubset(q3_pass.columns):
        errors.append("q3_country_pass_through.csv lacks comparability columns")
    else:
        chn = bool_series(q3_pass.loc[q3_pass["country"].eq("CHN"), "included_in_main_comparison"])
        if chn.any():
            errors.append("China proxy is included in the main Q3 fuel comparison")

    q3_buffer = pd.read_csv(RESULTS_DIR / "q3_buffer_interactions.csv")
    required_buffer = {"outcome", "buffer", "shock", "estimate", "lower_95", "upper_95", "specification"}
    if not required_buffer.issubset(q3_buffer.columns):
        errors.append("q3_buffer_interactions.csv lacks policy-buffer interaction columns")

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
