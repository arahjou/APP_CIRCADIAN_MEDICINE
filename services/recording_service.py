"""UI-independent deterministic analysis, run artifacts and atomic DB persistence."""
from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
import platform
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pandas as pd

from services.analysis_service import data_quality_report
from tools.recording import SIGNAL_UNITS, Recording
from tools.run_report import json_safe, render_run_report

ENGINE_VERSION = "1.0.0"


def apply_sleep_review(original: pd.DataFrame, reviewed: pd.DataFrame) -> pd.DataFrame:
    """Bring editor labels back onto canonical samples without losing timezone.

    The legacy editor uses naive local clock times. It must never replace the
    canonical timestamps or measurement columns when returning its edits.
    """
    clocks = pd.DatetimeIndex(original["DATE/TIME"]).tz_localize(None)
    editor = reviewed.copy().set_index("DATE/TIME")
    if clocks.has_duplicates or editor.index.has_duplicates or set(clocks) != set(editor.index):
        raise ValueError("Sleep review timestamps no longer match the original recording.")
    result = original.copy(deep=True)
    labels = pd.to_numeric(editor.reindex(clocks)["SLEEP_STATE"], errors="coerce")
    result["SLEEP_STATE"] = labels.where(labels.isin([0, 1])).to_numpy()
    result["EDITED"] = editor.reindex(clocks).get("EDITED", pd.Series(False, index=clocks)).to_numpy()
    return result


def infer_sleep_labels(df: pd.DataFrame) -> pd.Series:
    """Optional PIM-only preprocessing with no imputation or wake fallback."""
    quality = data_quality_report(df)
    if (not quality["eligible"]["activity"] or quality["gap_count"]
            or quality["signals"]["PIMn"]["missing_or_invalid_samples"]):
        raise ValueError("Sleep inference requires continuous, valid one-minute PIM samples without a DST transition.")
    from tools.sleep_algos import RawTS
    signal = df.set_index("DATE/TIME")["PIMn"].sort_index().tz_convert("UTC")
    try:
        state = RawTS(activity=signal).roenneberg(threshold_frac=0.15, min_seed_min=30, analysis_epoch_min=1)
    except Exception as exc:
        raise ValueError(f"Sleep inference failed; no labels were changed: {exc}") from exc
    aligned = state.reindex(pd.DatetimeIndex(df["DATE/TIME"]).tz_convert("UTC"))
    return pd.Series(aligned.to_numpy(), index=df.index, name="SLEEP_STATE", dtype=float)


def software_manifest() -> dict:
    root = Path(__file__).resolve().parents[1]
    files = [root / "app.py", *sorted((root / "tools").glob("*.py")),
             *sorted((root / "services").glob("*.py"))]
    packages = {}
    for name in ("pandas", "numpy", "scipy"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "unavailable"
    return {"engine_version": ENGINE_VERSION, "python": platform.python_version(), "packages": packages,
            "source_hashes": {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in files}}


def analyze_recording(recording: Recording, *, record_id: str, description: str = "",
                      selected_dates: list[str] | None = None, parameters: dict | None = None) -> dict:
    """Calculate without side effects. Missing/failed metrics are explicit outcomes."""
    if not record_id.strip():
        raise ValueError("record_id must not be empty")
    params = {"minimum_day_coverage": 0.7, "anchor_hour": 12,
              "sleep_source": recording.metadata.get("sleep_source", "absent"),
              **(parameters or {})}
    if not 0 < params["minimum_day_coverage"] <= 1:
        raise ValueError("minimum_day_coverage must be in (0, 1]")
    if not 0 <= params["anchor_hour"] < 24:
        raise ValueError("anchor_hour must be in [0, 24)")
    df = recording.data.copy(deep=True)
    # Callers can supply edited frames; enforce the same missing-value policy as
    # the importer without changing their source frame.
    for signal in SIGNAL_UNITS:
        if signal in df:
            values = pd.to_numeric(df[signal], errors="coerce").replace([float("inf"), -float("inf")], float("nan"))
            if signal == "SLEEP_STATE":
                values = values.where(values.isin([0, 1]))
            elif signal != "TEMPERATURE":
                values = values.where(values >= 0)
            df[signal] = values
    if selected_dates is not None:
        df = df[df["DATE"].isin(selected_dates)].copy()
    quality = data_quality_report(df)
    if not quality["ok"]:
        raise ValueError(" ".join(quality["errors"]))
    metrics: dict = {}

    def calculate(name, modality, eligible, function, reason="Required signal, one-minute sampling, or complete sleep labels unavailable."):
        if not eligible:
            metrics[name] = {"modality": modality, "status": "skipped", "reason": reason, "data": None}
            return None
        try:
            result = function()
            empty = isinstance(result, pd.DataFrame) and result.empty
            metrics[name] = {"modality": modality, "status": "unavailable" if empty else "completed",
                             "reason": "Insufficient eligible observations." if empty else None,
                             "data": json_safe(result)}
            return result
        except Exception as exc:
            metrics[name] = {"modality": modality, "status": "failed", "reason": str(exc), "data": None}
            return None

    from tools.sleep_CPD_ms import (
        build_centered_midpoint_hours,
        calculate_single_person_cpd,
    )
    from tools.sleep_light_exposure import analyze_sleep_light_exposure
    from tools.sleep_on_off_mid import analyze_sleep_periods
    from tools.sleep_SRI import calculate_sri_from_pimn

    eligible = quality["eligible"]
    periods = calculate("sleep_periods", "sleep", eligible["sleep"], lambda: analyze_sleep_periods(df))
    if periods is not None and not periods.empty:
        durations = periods["duration_minutes"]
        metrics["sleep_duration_summary"] = {
            "modality": "sleep", "status": "completed", "reason": None,
            "data": [{"statistic": key, "value": float(value), "unit": "minutes"}
                     for key, value in {"mean": durations.mean(), "minimum": durations.min(),
                                        "maximum": durations.max(), "SD (population)": durations.std(ddof=0)}.items()],
        }
    calculate("cpd_mid_sleep", "sleep", periods is not None and not periods.empty,
              lambda: calculate_single_person_cpd(build_centered_midpoint_hours(periods),
                                                  date_col="mid_sleep_DATE", midpoint_col="midpoint_hours_centered"))
    calculate("sri_sleep", "sleep", eligible["sri"], lambda: calculate_sri_from_pimn(
        df, "DATE/TIME", "PIMn", sleep_state_col="SLEEP_STATE", local_tz=recording.metadata["timezone"]))
    calculate("sleep_light_exposure", "sleep", eligible["sleep_light"], lambda: analyze_sleep_light_exposure(df))

    from tools.activity_cosinor import fit_cosinor_daily_activity
    from tools.activity_CPD import calculate_cpd_activity
    from tools.activity_IS_IV import compute_rolling_2day_is_iv_activity
    from tools.activity_L5_M10_RA import compute_daily_L5_M10_RA_activity
    from tools.light_cosinor import fit_cosinor_daily_activity as fit_light
    from tools.light_CPD import calculate_cpd_light
    from tools.light_IS_IV import compute_rolling_2day_is_iv_light
    from tools.light_L5_M10_RA import compute_daily_L5_M10_RA_light

    for modality, signal, is_iv, l5, cosinor, cpd in (
        ("activity", "PIMn", compute_rolling_2day_is_iv_activity, compute_daily_L5_M10_RA_activity, fit_cosinor_daily_activity, calculate_cpd_activity),
        ("light", "MELANOPIC EDI", compute_rolling_2day_is_iv_light, compute_daily_L5_M10_RA_light, fit_light, calculate_cpd_light),
    ):
        subset = df.iloc[:0]
        if signal in df:
            counts = df.groupby("DATE")[signal].count()
            accepted = counts[counts >= 1440 * params["minimum_day_coverage"]].index
            subset = df[df["DATE"].isin(accepted)].copy()
            if len(accepted) < df["DATE"].nunique():
                quality["warnings"].append(f"{modality}: days below {params['minimum_day_coverage']:.0%} coverage excluded from rhythm metrics.")
        can_run = eligible[modality] and not subset.empty
        calculate(f"{modality}_is_iv", modality, can_run, lambda: is_iv(subset, value_col=signal, anchor_hour=params["anchor_hour"]))
        calculate(f"{modality}_l5_m10_ra", modality, can_run, lambda: l5(subset, value_col=signal, anchor_hour=params["anchor_hour"]))
        fit = calculate(f"{modality}_cosinor", modality, can_run, lambda: cosinor(subset, value_col=signal))
        calculate(f"cpd_{modality}_acrophase", modality, fit is not None and not fit.empty,
                  lambda: cpd(fit, ms_col="acrophase_hours", date_col="date"))

    daily = {}
    for signal in SIGNAL_UNITS:
        if signal in df:
            summary = df.groupby("DATE")[signal].agg(["mean", "min", "max", "count"]).reset_index()
            daily[signal] = json_safe(summary.rename(columns={"DATE": "date"}))
    status = "partial" if any(m["status"] == "failed" for m in metrics.values()) else "completed"
    if not any(m["status"] == "completed" for m in metrics.values()):
        status = "summary_only" if status != "partial" else status
    snapshot = df.to_csv(index=False).encode("utf-8")
    run = json_safe({
        "schema_version": "analysis-run-1", "run_id": uuid.uuid4().hex,
        "record_id": record_id, "description": description, "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selected_dates": sorted(df["DATE"].unique()), "metadata": recording.metadata,
        "parameters": params, "quality": quality, "metrics": metrics,
        "daily_signals": daily, "software": software_manifest(),
        "normalized_sha256": sha256(snapshot).hexdigest(),
    })
    # Snapshot includes exact reviewed sleep labels and EDITED flags. Not part of JSON.
    return {"report": run, "snapshot": snapshot}


def persist_recording_run(result: dict, *, output_dir: str | Path = "analysis_runs", db=None) -> Path:
    """Write a unique directory; insert legacy rows + immutable run in one transaction.

    On ordinary failures this run's directory is removed. A process crash between
    filesystem and SQLite commits may leave an orphan directory (documented).
    """
    run = result["report"]
    if sha256(result["snapshot"]).hexdigest() != run["normalized_sha256"]:
        raise ValueError("Normalized snapshot fingerprint does not match the report")
    run_id = run["run_id"]
    if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
        raise ValueError("Invalid run identifier")
    directory = Path(output_dir).resolve() / run_id
    directory.mkdir(parents=True, exist_ok=False)
    try:
        (directory / "normalized.csv").write_bytes(result["snapshot"])
        blob = json.dumps(run, indent=2, allow_nan=False)
        (directory / "report.json").write_text(blob, encoding="utf-8")
        (directory / "report.html").write_text(render_run_report(run), encoding="utf-8")
        if db is not None:
            with sqlite3.connect(db.db_path) as conn:
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("INSERT INTO analysis_records (id, description, date, created_at, file_name, selected_dates) VALUES (?, ?, ?, ?, ?, ?)",
                             (run["record_id"], run["description"], run["created_at"], run["created_at"],
                              run["metadata"].get("source_name"), json.dumps(run["selected_dates"])))
                for name, metric in run["metrics"].items():
                    if metric["status"] != "completed":
                        continue
                    modality = metric["modality"]
                    if modality not in {"sleep", "activity", "light"}:
                        raise ValueError("Invalid metric modality")
                    conn.execute(f"INSERT INTO {modality}_analysis (record_id, analysis_type, results) VALUES (?, ?, ?)",
                                 (run["record_id"], name, json.dumps(metric["data"], allow_nan=False)))
                conn.execute("INSERT INTO recording_runs (run_id, record_id, created_at, report_json, artifact_path) VALUES (?, ?, ?, ?, ?)",
                             (run_id, run["record_id"], run["created_at"], blob, str(directory)))
        return directory
    except Exception:
        shutil.rmtree(directory)
        raise
