# Database Schema and Persistence

Primary database file: Actigraph_record.db (SQLite)
Primary access layer: tools/database.py (ActigraphDB)

## 1) Entity Relationship View

```mermaid
erDiagram
    analysis_records ||--o{ sleep_analysis : has
    analysis_records ||--o{ activity_analysis : has
    analysis_records ||--o{ light_analysis : has

    app_users ||--o{ auth_login_attempts : records
    app_users ||--o{ app_audit_logs : triggers

    app_users ||--o{ ai_analysis_runs : owns
    ai_analysis_runs ||--o{ ai_agent_traces : contains

    analysis_records {
        TEXT id PK
        TEXT description
        TEXT date
        TEXT created_at
        TEXT file_name
        TEXT selected_dates
        TEXT anamnesis
    }

    sleep_analysis {
        TEXT record_id FK
        TEXT analysis_type
        TEXT results
    }

    activity_analysis {
        TEXT record_id FK
        TEXT analysis_type
        TEXT results
    }

    light_analysis {
        TEXT record_id FK
        TEXT analysis_type
        TEXT results
    }

    ai_analysis_runs {
        TEXT username PK
        TEXT period_id_1 PK
        TEXT period_id_2 PK
        TEXT model PK
        TEXT audience PK
        TEXT anamnesis
        TEXT json_filepath
        TEXT json_input
        TEXT pipeline_outputs
        TEXT final_result
        TEXT schema_version
        TEXT created_at
        TEXT updated_at
    }

    ai_agent_traces {
        TEXT username PK
        TEXT period_id_1 PK
        TEXT period_id_2 PK
        TEXT model PK
        TEXT audience PK
        TEXT agent_name PK
        TEXT agent_input
        TEXT agent_output
        TEXT created_at
        TEXT updated_at
    }

    app_users {
        TEXT username PK
        TEXT salt
        TEXT password_hash
        TEXT role
        INTEGER is_active
        TEXT created_at
        TEXT updated_at
    }

    auth_login_attempts {
        INTEGER id PK
        TEXT username
        INTEGER success
        TEXT attempt_time
    }

    app_audit_logs {
        INTEGER id PK
        TEXT event_type
        TEXT username
        TEXT run_id
        TEXT details
        TEXT created_at
    }
```

ASCII relationship view:

```text
analysis_records (1) -> (many) sleep_analysis/activity_analysis/light_analysis
app_users (1) -> (many) auth_login_attempts
app_users (1) -> (many) app_audit_logs
ai_analysis_runs (composite key) -> (many) ai_agent_traces
```

## 2) Table Roles

- analysis_records:
  - Master row per uploaded/processed period.
  - Stores metadata and selected_dates context.
- sleep_analysis, activity_analysis, light_analysis:
  - Metric storage by analysis_type with JSON results.
- ai_analysis_runs:
  - Cached complete AI run per user + period pair + model + audience.
- ai_agent_traces:
  - Per-agent input/output trace for audit and reproducibility.
- app_users:
  - PBKDF2 password entries and role.
- auth_login_attempts:
  - Lockout and brute-force resistance support.
- app_audit_logs:
  - Security and workflow audit events.

## 3) Write Paths

- app.py writes:
  - analysis_records
  - modality analysis tables via save_*_analysis
  - ai_analysis_runs and ai_agent_traces
  - audit entries
- tools/report_generator.py reads modality tables and writes report JSON (file).
- tools/database.py owns schema creation and migrations.

## 4) Read Paths

- app.py tab views read records and analyses.
- report generation reads aggregated metrics by selected IDs.
- AI tab optionally loads cached ai_analysis_runs by exact key.

## 5) Artifacts Outside DB

- circadian_report.json
  - Created by tools/report_generator.save_json_report.
  - Serves as AI pipeline input.
- ai_analyses/*.txt and *.meta.json
  - Snapshot outputs created by app.py for user-level history.

## 6) Modality Extension Rules

To add a new modality table:

1. Add CREATE TABLE block in ActigraphDB.init_database.
2. Add save/get/aggregate support methods.
3. Include table in allowed table list used by aggregation routines.
4. Update report generator and docs to include modality in output contracts.

Last verified against codebase state: 2026-04-04.
