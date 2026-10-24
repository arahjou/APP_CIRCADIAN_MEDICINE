"""Streamlit boundary for the shared numerical workflow."""
from __future__ import annotations

import json
from hashlib import sha256

import pandas as pd
import streamlit as st

from services.analysis_service import data_quality_report
from services.recording_service import analyze_recording, persist_recording_run, infer_sleep_labels, apply_sleep_review
from tools.recording import ImportOptions, Recording, import_recording
from tools.run_report import render_run_report


def report_downloads(run: dict, *, key: str) -> None:
    st.download_button("Download research report (HTML)", render_run_report(run),
                       file_name=f"cmas-{run['run_id']}.html", mime="text/html", key=f"{key}-html")
    st.download_button("Download structured report (JSON)", json.dumps(run, indent=2, allow_nan=False),
                       file_name=f"cmas-{run['run_id']}.json", mime="application/json", key=f"{key}-json")


def render_new_analysis(db) -> None:
    st.subheader("New recording analysis")
    st.caption("Import → review quality and sleep → select dates → analyze → download report")
    analysis_id = st.text_input("Analysis ID", placeholder="Unique recording or study-period ID")
    description = st.text_input("Description")
    with st.expander("Import settings", expanded=True):
        tz = st.text_input("Recording timezone", value="Europe/Berlin")
        date_order = st.selectbox("Date format", ["dayfirst", "monthfirst", "iso"])
        device = st.text_input("Device / export source", value="unspecified")
        mapping_text = st.text_area("Optional column mapping (JSON)", value="{}",
                                    help='Source header to standard header, e.g. {"Time": "DATE/TIME"}. Map activity to PIMn only when it represents PIM counts.')
    source = st.file_uploader("Upload recording CSV", type=["csv", "txt", "tsv"])
    if source is None:
        st.info("Upload timestamped signals. Activity, light, temperature and sleep labels are optional individually.")
        return
    try:
        mapping = json.loads(mapping_text)
        if not isinstance(mapping, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()):
            raise ValueError("Column mapping must be a JSON object of string headers.")
        recording = import_recording(source, ImportOptions(tz, date_order, device, mapping))
    except Exception as exc:
        st.error(f"Cannot import recording: {exc}")
        return
    identity = sha256((recording.metadata["source_sha256"] + repr(recording.metadata["import_options"])).encode()).hexdigest()[:20]
    state_key = f"recording-review-{identity}"
    if state_key not in st.session_state:
        st.session_state[state_key] = recording.data.copy(deep=True)
        st.session_state[f"{state_key}-method"] = recording.metadata["sleep_source"]
    data = st.session_state[state_key]
    quality = data_quality_report(data)
    st.write(f"{quality['date_coverage_days']} recorded days · median interval {quality['sampling_minutes_median']} min")
    st.dataframe(pd.DataFrame(quality["signals"]).T)
    for message in quality["warnings"]:
        st.warning(message)
    for message in quality["errors"]:
        st.error(message)
    if not quality["ok"]:
        return
    st.caption("Missing sleep labels remain unknown. Sleep inference is optional and requires PIM activity.")
    if "PIMn" in data and quality["eligible"]["activity"]:
        if st.button("Infer sleep from PIM activity", key=f"{identity}-infer"):
            try:
                updated = data.copy(deep=True)
                updated["SLEEP_STATE"] = infer_sleep_labels(data)
                updated["EDITED"] = False
                st.session_state[state_key] = updated
                st.session_state[f"{state_key}-method"] = "roenneberg"
                st.session_state[f"{state_key}-inferred"] = True
                st.session_state[f"{state_key}-revision"] = st.session_state.get(f"{state_key}-revision", 0) + 1
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        if ("SLEEP_STATE" in data and data["SLEEP_STATE"].notna().all()
                and not quality["gap_count"] and data["PIMn"].notna().all()):
            if st.checkbox("Review and edit sleep bouts", key=f"{identity}-edit"):
                from tools.sleep_editor import run_sleep_editor
                revision = st.session_state.get(f"{state_key}-revision", 0)
                reviewed = run_sleep_editor(data.copy(deep=True), source_key=f"{identity}-{revision}",
                                             show_export=False, allow_auto_detection=False)
                data = apply_sleep_review(data, reviewed)
                st.session_state[state_key] = data
                if data.get("EDITED", pd.Series(False, index=data.index)).any():
                    st.session_state[f"{state_key}-method"] = "reviewed/edited"
    st.write(f"Sleep source: {st.session_state[f'{state_key}-method']}")
    preview = [c for c in ["PIMn", "MELANOPIC EDI", "TEMPERATURE", "SLEEP_STATE"] if c in data]
    if preview:
        st.line_chart(data.set_index("DATE/TIME")[preview])
    dates = sorted(data["DATE"].unique())
    selected = st.multiselect("Dates to analyze", dates, default=dates, key=f"{identity}-dates")
    if st.button("Run Analysis", type="primary"):
        if not analysis_id.strip() or not selected:
            st.error("Provide an Analysis ID and select at least one date.")
        elif db.record_exists(analysis_id):
            st.error("This Analysis ID exists. Choose a new ID to preserve the previous run.")
        else:
            try:
                method = st.session_state[f"{state_key}-method"]
                with st.spinner("Calculating and saving research report..."):
                    result = analyze_recording(Recording(data, recording.metadata), record_id=analysis_id,
                        description=description, selected_dates=selected, parameters={
                            "sleep_source": method, "edited_rows": int(data.get("EDITED", pd.Series(dtype=int)).sum()),
                            "sleep_inference": {"threshold_frac": 0.15, "min_seed_min": 30,
                                                "analysis_epoch_min": 1, "imputation": "none"}
                                                if st.session_state.get(f"{state_key}-inferred") else None})
                    persist_recording_run(result, db=db)
                    st.session_state[f"{state_key}-report"] = result["report"]
                st.success(f"Saved {analysis_id}: {result['report']['status']}.")
            except Exception as exc:
                st.error(f"Analysis could not be saved: {exc}")
    run = st.session_state.get(f"{state_key}-report")
    if run:
        st.write(f"Saved report for {run['record_id']} · {run['created_at']}")
        outcomes = [{"metric": name, "status": value["status"], "reason": value.get("reason")}
                    for name, value in run["metrics"].items()]
        st.dataframe(pd.DataFrame(outcomes))
        report_downloads(run, key=identity)
