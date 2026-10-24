# Tools and services API

Updated 2026-10-24. Python 3.10+.

## Import

```python
from tools.recording import ImportOptions, import_recording

with open("recording.csv", "rb") as source:
    recording = import_recording(source, ImportOptions(
        timezone="Europe/Berlin", date_order="dayfirst", device="research-device",
        column_map={"Time": "DATE/TIME"},
    ))
```

Returns `Recording(data: DataFrame, metadata: dict)`. See DATA_FLOW.md for signal
semantics. Import raises actionable errors for invalid structure/times. Invalid
signal values are counted and replaced by missing values. `upload_file(...)`
remains a compatibility wrapper returning the dataframe, with metadata in
`data.attrs['recording']`.

## Quality and numerical analysis

```python
from services.analysis_service import data_quality_report
from services.recording_service import analyze_recording, persist_recording_run

quality = data_quality_report(recording.data)
result = analyze_recording(recording, record_id="P001-week1",
                           description="Baseline research recording",
                           selected_dates=None,
                           parameters={"minimum_day_coverage": 0.7})
directory = persist_recording_run(result, output_dir="analysis_runs")
```

Quality returns `ok`, `errors`, `warnings`, `signals`, `eligible`, date coverage,
sampling interval, timezone presence, invalid/duplicate timestamps, gaps and DST.

Analysis returns `{report: dict, snapshot: bytes}`. `report` is strict-JSON-ready
and has schema `analysis-run-1`. It contains metadata, parameters, software hashes,
metrics, daily summaries and quality. It makes no filesystem or DB writes.

`infer_sleep_labels(data)` is optional and returns a Series aligned to the input
index. It requires continuous valid one-minute PIM counts and does no imputation.
Callers must retain its settings/method in analysis parameters when using it.

`persist_recording_run(result, output_dir=..., db=ActigraphDB(...))` additionally
inserts the record, successful metrics, and complete run into the existing database.
It raises on persistence failure and never overwrites a run or existing record ID.

## Rendering and historical access

- `tools.run_report.render_run_report(report) -> str`: standalone escaped HTML.
- `ActigraphDB.get_recording_run(record_id) -> dict | None`: new-style stored report;
  returns `None` for historical records without provenance.
- `tools.analysis_view.report_downloads(report, key=...)`: Streamlit HTML/JSON buttons.

## Comparison and optional AI

- `services.report_service.build_comparison(ids)` requires **two distinct existing**
  IDs and returns `(html, combined_dataframe, json_data)` in requested order.
- `persist_report_json(json_data)` returns a unique comparison path.
- `tools.report_generator.save_json_report(json_data, filename=None)` uses a unique
  default path; an explicit path must not exist already.
- `services.ai_pipeline_service.run_ai_pipeline(json_filepath=..., model=...,
  audience=..., anamnesis=..., progress_callback=...)` returns `(run_id, results)`.
  Its existing interface is unchanged. Pass the path returned by comparison
  persistence rather than assuming `circadian_report.json`.

## Batch use

```bash
python scripts/analyze_recording.py recording.csv \
  --record-id P001-week1 --timezone Europe/Berlin --date-order dayfirst \
  --device research-device --out analysis_runs --db pilot.db
```

Omit `--db` for artifacts only. `--column-map` accepts a JSON object;
`--dates 2026-01-01 2026-01-02` selects local dates. The CLI never implicitly infers
sleep and does not run an LLM. Exit 0 = completed/summary-only, 2 = partial metric
failure with saved report, 1 = import/analysis/persistence error.
