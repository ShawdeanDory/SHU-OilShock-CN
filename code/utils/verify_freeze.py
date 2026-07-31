"""Verify frozen modeling outputs without mutating the repository."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "results"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FROZEN_REQUIRED = [
    "schema_version",
    "freeze_hash",
    "freeze_mode",
    "overall_status",
    "paper_finalize_allowed",
    "git_commit",
    "cutoff",
    "random_seed",
    "environment",
    "processed_input_hashes",
    "core_result_hashes",
    "risk_gate_hash",
    "candidate_numbers",
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
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require_keys(payload: dict[str, Any], keys: list[str], label: str, errors: list[str]) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        errors.append(f"{label} missing required keys: {missing}")


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


def verify_environment(frozen: dict[str, Any], errors: list[str]) -> None:
    env = frozen.get("environment", {})
    if env.get("python_version") != platform.python_version():
        errors.append(f"python version mismatch: frozen={env.get('python_version')} current={platform.python_version()}")
    packages = env.get("packages", {})
    for package, frozen_version in packages.items():
        try:
            current = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            current = "NOT_INSTALLED"
        if current != frozen_version:
            errors.append(f"package version mismatch: {package} frozen={frozen_version} current={current}")


def verify_key_result_shapes(errors: list[str]) -> None:
    q1_metrics = pd.read_csv(RESULTS_DIR / "q1_forecast_metrics.csv")
    required_q1 = {"model", "horizon", "relative_RMSE_vs_no_change", "model_status"}
    if not required_q1.issubset(q1_metrics.columns):
        errors.append("q1_forecast_metrics.csv lacks forecast gate columns")
    advanced_bad = q1_metrics.loc[q1_metrics["model"].ne("no_change") & q1_metrics["model_status"].eq("PASS")]
    advanced_worse = q1_metrics.loc[q1_metrics["model"].ne("no_change") & q1_metrics["relative_RMSE_vs_no_change"].gt(1.0)]
    if not advanced_bad.merge(advanced_worse[["model", "horizon"]], on=["model", "horizon"], how="inner").empty:
        errors.append("advanced Q1 model with RMSE worse than no-change is still marked PASS")

    q3_pass = pd.read_csv(RESULTS_DIR / "q3_country_pass_through.csv")
    required_q3 = {"price_measure_type", "observed_or_regulated", "included_in_main_comparison", "comparability_note"}
    if not required_q3.issubset(q3_pass.columns):
        errors.append("q3_country_pass_through.csv lacks comparability columns")
    chn = bool_series(q3_pass.loc[q3_pass["country"].eq("CHN"), "included_in_main_comparison"])
    if chn.any():
        errors.append("China proxy is included in the main Q3 fuel comparison")

    policy = pd.read_csv(RESULTS_DIR / "q3_policy_counterfactual.csv")
    april = policy.loc[policy["period"].eq("2026-04")]
    if april.empty:
        errors.append("q3_policy_counterfactual.csv lacks 2026-04 row")
    else:
        inc = float(april["incremental_gasoline_gap_cny_t"].iloc[0])
        cum = float(april["cumulative_gasoline_gap_cny_t"].iloc[0])
        if abs(inc - 380.0) > 1e-6 or abs(cum - 1425.0) > 1e-6:
            errors.append("Q3 April policy gap no longer matches incremental 380 and cumulative 1425")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-final", action="store_true", help="Return nonzero unless the risk gate allows paper finalization.")
    args = parser.parse_args()

    errors: list[str] = []
    frozen_path = RESULTS_DIR / "frozen_numbers.json"
    risk_path = RESULTS_DIR / "risk_probe_summary.json"
    frozen = load_json(frozen_path)
    risk = load_json(risk_path)

    require_keys(frozen, FROZEN_REQUIRED, "frozen_numbers.json", errors)
    require_keys(risk, RISK_REQUIRED, "risk_probe_summary.json", errors)

    freeze_source = {key: frozen[key] for key in FROZEN_REQUIRED if key != "freeze_hash" and key in frozen}
    expected_freeze_hash = sha256_json(freeze_source)
    if frozen.get("freeze_hash") != expected_freeze_hash:
        errors.append("freeze_hash does not match canonical frozen payload")

    if frozen.get("risk_gate_hash") != sha256_file(risk_path):
        errors.append("risk_gate_hash does not match risk_probe_summary.json")

    verify_hashes(RESULTS_DIR, frozen.get("core_result_hashes", {}), "result", errors)
    verify_hashes(PROCESSED_DIR, frozen.get("processed_input_hashes", {}), "processed input", errors)
    verify_environment(frozen, errors)
    verify_key_result_shapes(errors)

    if risk.get("paper_finalize_allowed") != (risk.get("overall_status") == "PASS"):
        errors.append("risk paper_finalize_allowed is inconsistent with overall_status")
    if frozen.get("paper_finalize_allowed") != risk.get("paper_finalize_allowed"):
        errors.append("frozen paper_finalize_allowed differs from risk gate")
    if frozen.get("overall_status") != risk.get("overall_status"):
        errors.append("frozen overall_status differs from risk gate")

    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    if args.require_final and not risk.get("paper_finalize_allowed"):
        print(
            json.dumps(
                {
                    "status": risk.get("overall_status"),
                    "paper_finalize_allowed": False,
                    "blocking_probe_ids": risk.get("blocking_probe_ids", []),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    print(json.dumps({"status": risk.get("overall_status"), "paper_finalize_allowed": risk.get("paper_finalize_allowed")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
