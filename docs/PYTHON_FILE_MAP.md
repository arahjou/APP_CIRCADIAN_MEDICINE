# Python File Map

This inventory covers all Python files in the repository and documents purpose, primary inputs/outputs, and interactions.

## Root

| File | Purpose | Main Inputs | Main Outputs | Interacts With |
|---|---|---|---|---|
| app.py | Primary Streamlit app and orchestrator | User input, uploaded CSV, DB records | UI views, saved analyses, JSON path, AI report | tools/*, services/*, SQLite, ai_analyses/ |
| stress_test.py | Synthetic-data stress validation for analysis modules | Generated synthetic dataframe | Console pass/fail checks | tools/sleep_*, tools/activity_*, tools/light_* |

## OpenAI

| File | Purpose | Main Inputs | Main Outputs | Interacts With |
|---|---|---|---|---|
| OpenAI/app_OpenAI.py | Alternate Streamlit app variant | User input, uploaded CSV | UI output, AI reports | tools/*, OpenAI/llm_conversation_OpenAI.py |
| OpenAI/llm_conversation_OpenAI.py | OpenAI-compatible multi-agent pipeline | report JSON path, model, audience, anamnesis | Intermediate pipeline dict, final report | tools/pubmed_search.py |

## Services

| File | Purpose | Main Inputs | Main Outputs | Interacts With |
|---|---|---|---|---|
| services/__init__.py | Package marker | None | None | Python import system |
| services/analysis_service.py | Data quality validation service | Parsed dataframe | Quality summary dict | app.py |
| services/report_service.py | Report orchestration wrapper | Record IDs, JSON payload | Comparison tuple, saved JSON path | tools/report_generator.py |
| services/ai_pipeline_service.py | AI pipeline orchestration wrapper | json_filepath, model, audience, anamnesis | run_id, pipeline results | tools/llm_conversation.py, tools/app_logging.py |

## Tools - Core Utilities

| File | Purpose | Main Inputs | Main Outputs | Interacts With |
|---|---|---|---|---|
| tools/__init__.py | Package marker | None | None | Python import system |
| tools/upload_file.py | CSV ingestion and date filtering | Uploaded file buffer, selected dates | Normalized dataframe, available date list | app.py |
| tools/database.py | SQLite access layer and auth/audit API | Record payloads, metric blobs, credentials | DB writes/reads, aggregates, audit records | app.py, report_generator.py, scripts |
| tools/settings.py | Environment-based configuration | Env vars | Settings dataclass | app.py, scripts, report_generator.py |
| tools/app_logging.py | Structured logging with redaction | Event type and kwargs | JSON log line | app.py, services/ai_pipeline_service.py, llm_conversation.py |
| tools/report_generator.py | Comparison table and JSON builder | Record ID list | HTML report, combined dataframe, JSON payload | tools/database.py, app.py |
| tools/pubmed_search.py | PubMed retrieval/ranking utilities | Structured query list | Ranked evidence items, text evidence blocks | tools/llm_conversation.py, scripts/evaluate_pubmed_retrieval.py |
| tools/llm_conversation.py | Primary Ollama multi-agent pipeline | report JSON path, model, audience, anamnesis | intermediate state payload, final report, saved analysis text | tools/pubmed_search.py, app.py |
| tools/sleep_editor.py | Sleep-state editor and inference tooling | Dataframe with DATE/TIME + activity columns | Edited dataframe with SLEEP_STATE | app.py, tools/sleep_algos.py |
| tools/sleep_algos.py | Sleep algorithm internals (Roenneberg/MASDA support) | Time-indexed activity series | Sleep/wake inference outputs | tools/sleep_editor.py |

## Tools - Sleep Metrics

| File | Purpose | Main Inputs | Main Outputs | Interacts With |
|---|---|---|---|---|
| tools/sleep_light_exposure.py | Light around sleep transitions | Dataframe with SLEEP_STATE and MELANOPIC EDI | metric1/2/3 dict payload | app.py, report_generator.py |
| tools/sleep_on_off_mid.py | Sleep onset/offset/midpoint extraction | Dataframe with SLEEP_STATE + DATE/TIME | Sleep periods dataframe | app.py, sleep_CPD_ms.py |
| tools/sleep_CPD_ms.py | Circular CPD for mid-sleep | Sleep periods dataframe | Centered midpoint dataframe, CPD dataframe | app.py |
| tools/sleep_SRI.py | Sleep regularity index computation | Timestamp and activity/sleep fields | SRI dataframe | app.py |

## Tools - Activity Metrics

| File | Purpose | Main Inputs | Main Outputs | Interacts With |
|---|---|---|---|---|
| tools/activity_plotter.py | Activity time-series plot | Filtered dataframe | Matplotlib figure | app.py |
| tools/activity_IS_IV.py | 2-day rolling IS/IV | DATE/TIME + PIMn | IS/IV dataframe | app.py, report_generator.py |
| tools/activity_L5_M10_RA.py | Daily L5/M10/RA | DATE/TIME + PIMn | L5/M10/RA dataframe | app.py, report_generator.py |
| tools/activity_cosinor.py | Daily cosinor fit for activity | DATE/TIME + PIMn | mesor/amplitude/acrophase dataframe | app.py, activity_CPD.py |
| tools/activity_CPD.py | CPD from activity acrophase | Cosinor output dataframe | CPD dataframe | app.py, report_generator.py |

## Tools - Light Metrics

| File | Purpose | Main Inputs | Main Outputs | Interacts With |
|---|---|---|---|---|
| tools/light_plotter.py | Light time-series plot | Filtered dataframe | Matplotlib figure | app.py |
| tools/light_IS_IV.py | 2-day rolling IS/IV for light | DATE/TIME + MELANOPIC EDI | IS/IV dataframe | app.py, report_generator.py |
| tools/light_L5_M10_RA.py | Daily L5/M10/RA for light | DATE/TIME + MELANOPIC EDI | L5/M10/RA dataframe | app.py, report_generator.py |
| tools/light_cosinor.py | Daily cosinor fit for light | DATE/TIME + MELANOPIC EDI | mesor/amplitude/acrophase dataframe | app.py, light_CPD.py |
| tools/light_CPD.py | CPD from light acrophase | Cosinor output dataframe | CPD dataframe | app.py, report_generator.py |

## Scripts

| File | Purpose | Main Inputs | Main Outputs | Interacts With |
|---|---|---|---|---|
| scripts/bootstrap_admin.py | Create or rotate admin user | username, password args | app_users row + audit log | tools/database.py, tools/settings.py |
| scripts/backup_db.py | Encrypted DB backup and integrity check | DB path, output dir, backup key | encrypted .db.enc backup file | SQLite, cryptography |
| scripts/evaluate_pubmed_retrieval.py | Retrieval benchmark utility | benchmark JSONL cases | precision/usefulness metrics | tools/pubmed_search.py |

## Tests

| File | Purpose | Main Inputs | Main Outputs | Interacts With |
|---|---|---|---|---|
| tests/conftest.py | Test path/bootstrap config | None | Import path setup | pytest |
| tests/unit/test_database_auth.py | Unit test for auth and lockout | Temporary DB path | Assertions over create/verify/lockout | tools/database.py |
| tests/unit/test_pubmed_search.py | Unit test for retrieval ranking | Monkeypatched API stubs | Assertions over result shape/ranking | tools/pubmed_search.py |
| tests/integration/test_pipeline_fallback.py | Integration fallback behavior test | Temporary report JSON, mocked graph failure | Assertion on fallback final_report/error | tools/llm_conversation.py |

## Notes

- app.py is the canonical runtime entry point.
- OpenAI/ files are alternate runtime/backend variants.
- services/ modules are intentionally thin wrappers around tools/ to keep app orchestration explicit.

Last verified against codebase state: 2026-04-04.
