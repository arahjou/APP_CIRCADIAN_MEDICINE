# Tools and Services API Contracts

This document captures orchestration-facing interfaces used by the Streamlit application and supporting scripts.

## 1) Services Layer

### services/analysis_service.py
- Function: data_quality_report(df: pandas.DataFrame) -> dict
- Required columns: DATE/TIME, PIMn, MELANOPIC EDI
- Output keys:
  - ok: bool
  - missing_columns: list[str]
  - date_coverage_days: int
  - sampling_minutes_median: float | None
  - timezone_present: bool

### services/report_service.py
- Function: build_comparison(ids: list[str]) -> tuple[str, Any, dict | None]
  - Delegates to tools/report_generator.generate_comparison_report.
  - Returns HTML report, combined dataframe, JSON report payload.
- Function: persist_report_json(json_data: dict) -> str
  - Delegates to tools/report_generator.save_json_report.
  - Returns absolute path to saved JSON.

### services/ai_pipeline_service.py
- Function: run_ai_pipeline(...)
- Signature:
  - json_filepath: str
  - model: str
  - audience: str
  - anamnesis: str
  - progress_callback: Callable[[str], None] | None
- Returns: tuple[str, dict]
  - run_id: short UUID fragment
  - results: pipeline payload from tools/llm_conversation.get_intermediate_results

## 2) Ingestion and Preprocessing

### tools/upload_file.py
- upload_file(upload_file) -> pandas.DataFrame | None
  - Detects header row and delimiter
  - Parses DATE/TIME and localizes to Europe/Berlin
  - Returns normalized subset columns and derived DATE/TIME/HOUR/Transition fields
- get_available_dates(df) -> list[str]
- filter_data_by_dates(df, selected_dates) -> pandas.DataFrame

### tools/sleep_editor.py (selected public app-facing APIs)
- run_sleep_editor(df, source_key="uploaded", show_export=True) -> pandas.DataFrame
- infer_sleep_state_roenneberg(...) -> pandas.Series
- infer_sleep_state_from_pimn(...) -> pandas.Series (deprecated compatibility wrapper)
- prepare_dataframe(df) -> pandas.DataFrame

## 3) Metric Engines

### Sleep modules
- tools/sleep_light_exposure.py
  - analyze_sleep_light_exposure(df_subset) -> dict
  - Includes metric1/metric2/metric3 structures for light around sleep.
- tools/sleep_on_off_mid.py
  - analyze_sleep_periods(data) -> pandas.DataFrame
  - Sleep onset/offset/midpoint per detected period.
- tools/sleep_CPD_ms.py
  - build_centered_midpoint_hours(df, ...) -> pandas.DataFrame
  - calculate_single_person_cpd(df, date_col, midpoint_col) -> pandas.DataFrame
- tools/sleep_SRI.py
  - calculate_sri_from_pimn(...) -> pandas.DataFrame

### Activity modules
- tools/activity_IS_IV.py
  - compute_rolling_2day_is_iv_activity(df, time_col='DATE/TIME', value_col='PIMn', ...) -> pandas.DataFrame
- tools/activity_L5_M10_RA.py
  - compute_daily_L5_M10_RA_activity(df, time_col='DATE/TIME', value_col='PIMn', ...) -> pandas.DataFrame
- tools/activity_cosinor.py
  - fit_cosinor_daily_activity(df, datetime_col='DATE/TIME', value_col='PIMn') -> pandas.DataFrame
- tools/activity_CPD.py
  - calculate_cpd_activity(df, ms_col='acrophase_hours', date_col='date', ...) -> pandas.DataFrame
- tools/activity_plotter.py
  - activity_plotter(df_subset) -> matplotlib.figure.Figure

### Light modules
- tools/light_IS_IV.py
  - compute_rolling_2day_is_iv_light(df, time_col='DATE/TIME', value_col='MELANOPIC EDI', ...) -> pandas.DataFrame
- tools/light_L5_M10_RA.py
  - compute_daily_L5_M10_RA_light(df, time_col='DATE/TIME', value_col='MELANOPIC EDI', ...) -> pandas.DataFrame
- tools/light_cosinor.py
  - fit_cosinor_daily_activity(df, datetime_col='DATE/TIME', value_col='MELANOPIC EDI') -> pandas.DataFrame
- tools/light_CPD.py
  - calculate_cpd_light(df, ms_col='acrophase_hours', date_col='date', ...) -> pandas.DataFrame
- tools/light_plotter.py
  - light_plotter(df_subset) -> matplotlib.figure.Figure

## 4) Reporting and Persistence

### tools/report_generator.py
- generate_comparison_report(ids) -> tuple[str, pandas.DataFrame, dict]
  - Reads aggregated metrics from DB
  - Builds domain tables
  - Produces HTML report and LLM-ready JSON structure
- save_json_report(json_data, filename='circadian_report.json') -> str

### tools/database.py (ActigraphDB)
- Core record APIs:
  - save_analysis_record(...)
  - save_sleep_analysis(...)
  - save_activity_analysis(...)
  - save_light_analysis(...)
  - get_all_records(), get_record_by_id(), record_exists(...)
- Aggregation APIs:
  - get_aggregated_metrics_for_ids(...)
- AI run APIs:
  - save_ai_analysis_run(...)
  - get_ai_analysis_run(...)
  - get_ai_analysis_runs_for_user(...)
- Auth and audit APIs:
  - create_or_update_user(...)
  - verify_user_password(...)
  - record_login_attempt(...), is_locked_out(...)
  - add_audit_log(...)

## 5) AI and Retrieval

### tools/llm_conversation.py
- analyze_circadian_report(json_filepath, model='phi4:14b', audience='expert') -> str
- get_intermediate_results(json_filepath, model='phi4:14b', audience='expert', anamnesis='', progress_callback=None) -> dict
- continue_conversation(previous_analysis, user_question, model='phi4:14b') -> str
- save_analysis(analysis_text, filename='llm_analysis.txt') -> str

### tools/pubmed_search.py
- search_pubmed(queries, ncbi_api_key=None, config=None) -> list[dict]
  - Structured output records include pmid/title/abstract/journal/year/score/query_source/compiled_query.
- evidence_to_text(evidence_items, max_chars=12000) -> str
- RetrievalConfig dataclass controls breadth and filtering.

### tools/settings.py
- get_settings() -> Settings dataclass
  - Parses APP_ENV, DB_PATH, NCBI_API_KEY, ALLOWED_MODELS, auth/session controls.

### tools/app_logging.py
- log_event(event, **kwargs) -> None
  - Redacts basic identifiers and emits structured JSON log line.

Last verified against codebase state: 2026-04-04.
