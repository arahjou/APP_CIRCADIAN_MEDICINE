from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from services.recording_service import analyze_recording, infer_sleep_labels, persist_recording_run, apply_sleep_review
from tools.database import ActigraphDB
from tools.recording import ImportOptions, import_recording
from tools.report_generator import generate_comparison_report, save_json_report
from tools.run_report import render_run_report


@pytest.fixture
def recording():
    ts = pd.date_range("2026-01-01", periods=3 * 1440, freq="min", tz="UTC")
    phase = np.arange(len(ts)) * 2 * np.pi / 1440
    data = pd.DataFrame({"Timestamp": ts, "PIMn": 50 + 45 * np.cos(phase - np.pi),
                         "MELANOPIC EDI": 100 + 99 * np.cos(phase - np.pi),
                         "SLEEP_STATE": ((ts.hour >= 23) | (ts.hour < 7)).astype(int)})
    return import_recording(BytesIO(data.to_csv(index=False).encode()), ImportOptions(timezone="UTC"))


def test_complete_workflow_reproducible_artifacts_and_db(recording, tmp_path):
    db = ActigraphDB(str(tmp_path / "test.db"))
    result = analyze_recording(recording, record_id="A", description="<script>alert(1)</script>")
    report = result["report"]
    assert report["status"] == "completed", report["metrics"]
    assert all(m["status"] == "completed" for m in report["metrics"].values())
    assert report["metrics"]["sri_sleep"]["data"][0]["SRI"] == 100
    assert report["metrics"]["sleep_periods"]["data"][0]["duration_minutes"] == 480
    directory = persist_recording_run(result, output_dir=tmp_path / "runs", db=db)
    assert sha256((directory / "normalized.csv").read_bytes()).hexdigest() == report["normalized_sha256"]
    assert db.get_recording_run("A") == report
    assert db.get_analysis_results("A", "sleep_analysis")
    assert "<script>" not in (directory / "report.html").read_text()
    assert "&lt;script&gt;" in render_run_report(report)
    json.loads((directory / "report.json").read_text(), parse_constant=lambda x: pytest.fail(x))
    second = analyze_recording(recording, record_id="B")
    assert second["report"]["run_id"] != report["run_id"]
    assert second["report"]["metrics"] == report["metrics"]
    with pytest.raises(FileExistsError):
        persist_recording_run(result, output_dir=tmp_path / "runs", db=db)


def test_optional_signal_and_inference_failure(recording):
    recording.data = recording.data.drop(columns=["MELANOPIC EDI", "SLEEP_STATE"])
    result = analyze_recording(recording, record_id="A")
    metrics = result["report"]["metrics"]
    assert metrics["activity_cosinor"]["status"] == "completed"
    assert metrics["light_cosinor"]["status"] == "skipped"
    assert metrics["sleep_periods"]["status"] == "skipped"
    recording.data.loc[1, "PIMn"] = np.nan
    with pytest.raises(ValueError, match="continuous"):
        infer_sleep_labels(recording.data)


def test_inference_preserves_index_and_input(recording):
    original = recording.data.copy(deep=True)
    inferred = infer_sleep_labels(recording.data)
    assert inferred.index.equals(recording.data.index)
    assert inferred.dropna().isin([0, 1]).all()
    pd.testing.assert_frame_equal(recording.data, original)


def test_editor_labels_preserve_canonical_time_and_signals(recording):
    original = recording.data
    edited = original.copy()
    edited["DATE/TIME"] = edited["DATE/TIME"].dt.tz_localize(None)
    edited.loc[10, "SLEEP_STATE"] = 0
    edited["EDITED"] = False
    edited.loc[10, "EDITED"] = True
    edited["PIMn"] = 999
    merged = apply_sleep_review(original, edited)
    pd.testing.assert_series_equal(merged["DATE/TIME"], original["DATE/TIME"])
    pd.testing.assert_series_equal(merged["PIMn"], original["PIMn"])
    assert merged.loc[10, "SLEEP_STATE"] == 0 and merged.loc[10, "EDITED"]
    with pytest.raises(ValueError, match="no longer match"):
        apply_sleep_review(original, edited.iloc[1:])


def test_streamlit_import_run_and_download(recording, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "synthetic.csv"
    recording.data.to_csv(source, index=False)
    script = f'''
from unittest.mock import patch
from tools.database import ActigraphDB
from tools.analysis_view import render_new_analysis
with open({str(source)!r}, "rb") as source:
    with patch("streamlit.file_uploader", return_value=source):
        render_new_analysis(ActigraphDB({str(tmp_path / "ui.db")!r}))
'''
    app = AppTest.from_string(script, default_timeout=30).run()
    assert not app.exception
    next(w for w in app.checkbox if w.label == "Review and edit sleep bouts").check()
    app.run()
    assert not app.exception
    next(w for w in app.text_input if w.label == "Analysis ID").set_value("UI-001")
    next(w for w in app.button if w.label == "Run Analysis").click()
    app.run()
    assert not app.exception
    assert not app.error
    assert any("Saved UI-001" in w.value for w in app.success)
    assert len(app.get("download_button")) == 2
    assert ActigraphDB(str(tmp_path / "ui.db")).get_recording_run("UI-001")


def test_persistence_rolls_back_and_cleans_own_artifacts(recording, tmp_path):
    db = ActigraphDB(str(tmp_path / "test.db"))
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("CREATE TRIGGER fail_run BEFORE INSERT ON recording_runs BEGIN SELECT RAISE(ABORT, 'simulated'); END")
    result = analyze_recording(recording, record_id="A")
    with pytest.raises(sqlite3.IntegrityError, match="simulated"):
        persist_recording_run(result, output_dir=tmp_path / "runs", db=db)
    assert db.get_all_records() == []
    assert db.get_analysis_results("A", "activity_analysis") == []
    assert not list((tmp_path / "runs").iterdir())


def test_metric_failure_is_partial_not_success(recording, monkeypatch):
    import tools.activity_cosinor as module
    def broken(*args, **kwargs):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(module, "fit_cosinor_daily_activity", broken)
    report = analyze_recording(recording, record_id="A")["report"]
    assert report["status"] == "partial"
    assert report["metrics"]["activity_cosinor"]["reason"] == "synthetic failure"
    assert report["metrics"]["cpd_activity_acrophase"]["status"] == "skipped"
    assert report["metrics"]["light_cosinor"]["status"] == "completed"


def test_comparison_mean_order_optional_modalities_and_unique_files(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.chdir(tmp_path)
    db = ActigraphDB(str(tmp_path / "test.db"))
    for name, durations in [("A", [240, 480]), ("B", [480, 600])]:
        assert db.save_analysis_record(name, "test", "2026-01-01")
        assert db.save_sleep_analysis(name, "sleep_periods", pd.DataFrame({"duration_minutes": durations}))
    _, _, report = generate_comparison_report(["B", "A"])
    rows = report["sections"]["Sleep and Circadian Health"]["Circadian Rhythms and Sleep Metrics"]
    mean = next(r for r in rows if r["Name"] == "Mean sleep duration (minutes)")
    assert mean["Period1"] == 540
    assert mean["Period2"] == 360
    assert mean["Difference"] == -180
    first, second = save_json_report(report), save_json_report(report)
    assert first != second
    assert Path(first).exists() and Path(second).exists()
    json.loads(Path(first).read_text(), parse_constant=lambda x: pytest.fail(x))
    with pytest.raises(ValueError, match="exactly two"):
        generate_comparison_report(["A"])


def test_cli_and_temperature_summary(tmp_path):
    source = tmp_path / "temperature.csv"
    source.write_text("Timestamp,TEMPERATURE\n2026-01-01T00:00:00Z,32\n2026-01-01T00:05:00Z,33\n")
    script = Path(__file__).resolve().parents[2] / "scripts" / "analyze_recording.py"
    run = subprocess.run([sys.executable, str(script), str(source), "--record-id", "T", "--out", str(tmp_path / "runs")], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    report = json.loads(next((tmp_path / "runs").glob("*/report.json")).read_text())
    assert report["status"] == "summary_only"
    assert report["daily_signals"]["TEMPERATURE"][0]["mean"] == 32.5
