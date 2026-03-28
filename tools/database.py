"""
Database module for Actigraph Record Management
Handles SQLite operations for storing and retrieving analysis records
"""

import sqlite3
import json
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List, Optional
import os

class ActigraphDB:
    _ALLOWED_TABLES = frozenset({"sleep_analysis", "activity_analysis", "light_analysis"})

    def __init__(self, db_path: str = "Actigraph_record.db"):
        """Initialize database connection and create tables if they don't exist"""
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Create database tables if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Main analysis records table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS analysis_records (
                    id TEXT PRIMARY KEY,
                    description TEXT,
                    date TEXT,
                    created_at TEXT,
                    file_name TEXT,
                    selected_dates TEXT
                )
            ''')
            
            # Sleep analysis results
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sleep_analysis (
                    record_id TEXT,
                    analysis_type TEXT,
                    results TEXT,
                    FOREIGN KEY (record_id) REFERENCES analysis_records (id)
                )
            ''')
            
            # Activity analysis results
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS activity_analysis (
                    record_id TEXT,
                    analysis_type TEXT,
                    results TEXT,
                    FOREIGN KEY (record_id) REFERENCES analysis_records (id)
                )
            ''')
            
            # Light analysis results
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS light_analysis (
                    record_id TEXT,
                    analysis_type TEXT,
                    results TEXT,
                    FOREIGN KEY (record_id) REFERENCES analysis_records (id)
                )
            ''')

            # AI analysis runs (Tab 4) with upsert semantics per unique run key
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_analysis_runs (
                    username TEXT,
                    period_id_1 TEXT,
                    period_id_2 TEXT,
                    model TEXT,
                    audience TEXT,
                    anamnesis TEXT,
                    json_filepath TEXT,
                    json_input TEXT,
                    pipeline_outputs TEXT,
                    final_result TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (username, period_id_1, period_id_2, model, audience)
                )
            ''')

            # Per-agent input/output trace for medical-grade reproducibility and auditing
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_agent_traces (
                    username TEXT,
                    period_id_1 TEXT,
                    period_id_2 TEXT,
                    model TEXT,
                    audience TEXT,
                    agent_name TEXT,
                    agent_input TEXT,
                    agent_output TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (username, period_id_1, period_id_2, model, audience, agent_name)
                )
            ''')
            
            # Migrate existing databases — add anamnesis column if it doesn't exist yet
            try:
                cursor.execute("ALTER TABLE analysis_records ADD COLUMN anamnesis TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists

            conn.commit()

    def save_ai_analysis_run(
        self,
        username: str,
        period_id_1: str,
        period_id_2: str,
        model: str,
        audience: str,
        anamnesis: str,
        json_filepath: str,
        json_input: Any,
        pipeline_outputs: Any,
        final_result: str,
        agent_trace: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Insert or replace an AI analysis run for the same user/period pair/model/audience."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                cursor.execute(
                    """
                    SELECT created_at, anamnesis
                    FROM ai_analysis_runs
                    WHERE username = ? AND period_id_1 = ? AND period_id_2 = ? AND model = ? AND audience = ?
                    """,
                    (username, period_id_1, period_id_2, model, audience),
                )
                existing = cursor.fetchone()
                created_at = existing[0] if existing and existing[0] else now
                existing_anamnesis = existing[1] if existing and len(existing) > 1 else ""

                # Preserve previous anamnesis if rerun was triggered without new anamnesis text.
                incoming_anamnesis = (anamnesis or "").strip()
                effective_anamnesis = incoming_anamnesis or (existing_anamnesis or "")

                if agent_trace is None and isinstance(pipeline_outputs, dict):
                    candidate_trace = pipeline_outputs.get("agent_trace")
                    if isinstance(candidate_trace, dict):
                        agent_trace = candidate_trace

                json_input_blob = json.dumps(json_input, default=str)
                pipeline_outputs_blob = json.dumps(pipeline_outputs, default=str)

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO ai_analysis_runs (
                        username,
                        period_id_1,
                        period_id_2,
                        model,
                        audience,
                        anamnesis,
                        json_filepath,
                        json_input,
                        pipeline_outputs,
                        final_result,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        username,
                        period_id_1,
                        period_id_2,
                        model,
                        audience,
                        effective_anamnesis,
                        json_filepath,
                        json_input_blob,
                        pipeline_outputs_blob,
                        final_result,
                        created_at,
                        now,
                    ),
                )

                # Persist each agent input/output trace separately for structured DB queries.
                if isinstance(agent_trace, dict):
                    for agent_name, io_payload in agent_trace.items():
                        if not isinstance(io_payload, dict):
                            continue

                        agent_input_blob = json.dumps(io_payload.get("input"), default=str)
                        agent_output_blob = json.dumps(io_payload.get("output"), default=str)

                        cursor.execute(
                            """
                            SELECT created_at
                            FROM ai_agent_traces
                            WHERE username = ? AND period_id_1 = ? AND period_id_2 = ?
                              AND model = ? AND audience = ? AND agent_name = ?
                            """,
                            (
                                username,
                                period_id_1,
                                period_id_2,
                                model,
                                audience,
                                str(agent_name),
                            ),
                        )
                        existing_agent = cursor.fetchone()
                        agent_created_at = (
                            existing_agent[0] if existing_agent and existing_agent[0] else now
                        )

                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO ai_agent_traces (
                                username,
                                period_id_1,
                                period_id_2,
                                model,
                                audience,
                                agent_name,
                                agent_input,
                                agent_output,
                                created_at,
                                updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                username,
                                period_id_1,
                                period_id_2,
                                model,
                                audience,
                                str(agent_name),
                                agent_input_blob,
                                agent_output_blob,
                                agent_created_at,
                                now,
                            ),
                        )

                conn.commit()
                return True
        except Exception as e:
            print(f"Error saving AI analysis run: {e}")
            return False

    def get_ai_analysis_run(
        self,
        username: str,
        period_id_1: str,
        period_id_2: str,
        model: str,
        audience: str,
    ) -> Optional[Dict]:
        """Retrieve one persisted AI analysis run for exact Tab 4 context key."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT
                        username,
                        period_id_1,
                        period_id_2,
                        model,
                        audience,
                        anamnesis,
                        json_filepath,
                        json_input,
                        pipeline_outputs,
                        final_result,
                        created_at,
                        updated_at
                    FROM ai_analysis_runs
                    WHERE username = ? AND period_id_1 = ? AND period_id_2 = ? AND model = ? AND audience = ?
                    """,
                    (username, period_id_1, period_id_2, model, audience),
                )
                row = cursor.fetchone()
                if not row:
                    return None

                columns = [description[0] for description in cursor.description]
                record = dict(zip(columns, row))

                for key in ("json_input", "pipeline_outputs"):
                    try:
                        record[key] = json.loads(record[key]) if record.get(key) else None
                    except Exception:
                        pass

                cursor.execute(
                    """
                    SELECT agent_name, agent_input, agent_output, created_at, updated_at
                    FROM ai_agent_traces
                    WHERE username = ? AND period_id_1 = ? AND period_id_2 = ? AND model = ? AND audience = ?
                    ORDER BY agent_name ASC
                    """,
                    (username, period_id_1, period_id_2, model, audience),
                )
                trace_rows = cursor.fetchall()
                if trace_rows:
                    agent_trace: Dict[str, Any] = {}
                    for agent_name, agent_input, agent_output, created_at, updated_at in trace_rows:
                        try:
                            decoded_input = json.loads(agent_input) if agent_input else None
                        except Exception:
                            decoded_input = agent_input
                        try:
                            decoded_output = json.loads(agent_output) if agent_output else None
                        except Exception:
                            decoded_output = agent_output

                        agent_trace[str(agent_name)] = {
                            "input": decoded_input,
                            "output": decoded_output,
                            "created_at": created_at,
                            "updated_at": updated_at,
                        }
                    record["agent_trace"] = agent_trace

                return record
        except Exception as e:
            print(f"Error retrieving AI analysis run: {e}")
            return None

    def get_ai_analysis_runs_for_pair(
        self,
        username: str,
        period_id_1: str,
        period_id_2: str,
        include_reversed: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return all cached AI runs for a pair of period IDs (optionally both directions)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if include_reversed:
                    cursor.execute(
                        """
                        SELECT
                            username,
                            period_id_1,
                            period_id_2,
                            model,
                            audience,
                            anamnesis,
                            json_filepath,
                            json_input,
                            pipeline_outputs,
                            final_result,
                            created_at,
                            updated_at
                        FROM ai_analysis_runs
                        WHERE username = ?
                          AND (
                                (period_id_1 = ? AND period_id_2 = ?)
                             OR (period_id_1 = ? AND period_id_2 = ?)
                          )
                        ORDER BY COALESCE(updated_at, created_at) DESC
                        """,
                        (username, period_id_1, period_id_2, period_id_2, period_id_1),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT
                            username,
                            period_id_1,
                            period_id_2,
                            model,
                            audience,
                            anamnesis,
                            json_filepath,
                            json_input,
                            pipeline_outputs,
                            final_result,
                            created_at,
                            updated_at
                        FROM ai_analysis_runs
                        WHERE username = ? AND period_id_1 = ? AND period_id_2 = ?
                        ORDER BY COALESCE(updated_at, created_at) DESC
                        """,
                        (username, period_id_1, period_id_2),
                    )

                columns = [description[0] for description in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

                for record in rows:
                    for key in ("json_input", "pipeline_outputs"):
                        try:
                            record[key] = json.loads(record[key]) if record.get(key) else None
                        except Exception:
                            pass

                return rows
        except Exception as e:
            print(f"Error retrieving AI analysis run history: {e}")
            return []
    
    def save_anamnesis(self, record_id: str, text: str) -> bool:
        """Save or update the anamnesis text for a record."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE analysis_records SET anamnesis = ? WHERE id = ?",
                    (text.strip(), record_id),
                )
                conn.commit()
                return True
        except Exception as e:
            print(f"Error saving anamnesis: {e}")
            return False

    def get_anamnesis(self, record_id: str) -> str:
        """Return the anamnesis text for a record, or empty string if none."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT anamnesis FROM analysis_records WHERE id = ?", (record_id,)
                )
                row = cursor.fetchone()
                if row and row[0]:
                    return row[0]
                return ""
        except Exception as e:
            print(f"Error retrieving anamnesis: {e}")
            return ""

    def save_analysis_record(self, analysis_id: str, description: str, date: str, 
                           file_name: Optional[str] = None, selected_dates: Optional[List[str]] = None) -> bool:
        """Save a new analysis record"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if ID already exists
                cursor.execute("SELECT id FROM analysis_records WHERE id = ?", (analysis_id,))
                if cursor.fetchone():
                    return False  # ID already exists
                
                created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                selected_dates_json = json.dumps(selected_dates) if selected_dates else None
                
                cursor.execute('''
                    INSERT INTO analysis_records (id, description, date, created_at, file_name, selected_dates)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (analysis_id, description, date, created_at, file_name, selected_dates_json))
                
                conn.commit()
                return True
        except Exception as e:
            print(f"Error saving analysis record: {e}")
            return False
    
    def save_sleep_analysis(self, record_id: str, analysis_type: str, results: Any) -> bool:
        """Save sleep analysis results"""
        return self._save_analysis_results("sleep_analysis", record_id, analysis_type, results)
    
    def save_activity_analysis(self, record_id: str, analysis_type: str, results: Any) -> bool:
        """Save activity analysis results"""
        return self._save_analysis_results("activity_analysis", record_id, analysis_type, results)
    
    def save_light_analysis(self, record_id: str, analysis_type: str, results: Any) -> bool:
        """Save light analysis results"""
        return self._save_analysis_results("light_analysis", record_id, analysis_type, results)
    
    def _safe_table(self, table_name: str) -> str:
        """Validate table_name against the allowed list to prevent SQL injection."""
        if table_name not in self._ALLOWED_TABLES:
            raise ValueError(f"Unknown table '{table_name}'. Allowed: {sorted(self._ALLOWED_TABLES)}")
        return table_name

    def _save_analysis_results(self, table_name: str, record_id: str, analysis_type: str, results: Any) -> bool:
        """Helper method to save analysis results to specific table"""
        table_name = self._safe_table(table_name)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Convert results to JSON string
                if isinstance(results, pd.DataFrame):
                    results_json = results.to_json(orient='records', date_format='iso')
                elif isinstance(results, dict):
                    results_json = json.dumps(results)
                else:
                    results_json = json.dumps(str(results))
                
                cursor.execute(f'''
                    INSERT INTO {table_name} (record_id, analysis_type, results)
                    VALUES (?, ?, ?)
                ''', (record_id, analysis_type, results_json))
                
                conn.commit()
                return True
        except Exception as e:
            print(f"Error saving {analysis_type} analysis: {e}")
            return False
    
    def get_all_records(self) -> List[Dict]:
        """Get all analysis records"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM analysis_records ORDER BY created_at DESC")
                columns = [description[0] for description in cursor.description]
                records = [dict(zip(columns, row)) for row in cursor.fetchall()]
                return records
        except Exception as e:
            print(f"Error retrieving records: {e}")
            return []
    
    def get_record_by_id(self, record_id: str) -> Optional[Dict]:
        """Get a specific analysis record by ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM analysis_records WHERE id = ?", (record_id,))
                row = cursor.fetchone()
                if row:
                    columns = [description[0] for description in cursor.description]
                    return dict(zip(columns, row))
                return None
        except Exception as e:
            print(f"Error retrieving record: {e}")
            return None
    
    def get_analysis_results(self, record_id: str, table_name: str) -> List[Dict]:
        """Get analysis results for a specific record from a specific table"""
        table_name = self._safe_table(table_name)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT * FROM {table_name} WHERE record_id = ?", (record_id,))
                columns = [description[0] for description in cursor.description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                
                # Parse JSON results back to original format
                for result in results:
                    try:
                        result['results'] = json.loads(result['results'])
                    except:
                        pass  # Keep as string if JSON parsing fails
                
                return results
        except Exception as e:
            print(f"Error retrieving analysis results: {e}")
            return []
    
    def delete_record(self, record_id: str) -> bool:
        """Delete an analysis record and all its associated analysis results"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Delete from all tables
                cursor.execute("DELETE FROM sleep_analysis WHERE record_id = ?", (record_id,))
                cursor.execute("DELETE FROM activity_analysis WHERE record_id = ?", (record_id,))
                cursor.execute("DELETE FROM light_analysis WHERE record_id = ?", (record_id,))
                cursor.execute("DELETE FROM analysis_records WHERE id = ?", (record_id,))
                
                conn.commit()
                return True
        except Exception as e:
            print(f"Error deleting record: {e}")
            return False
    
    def get_analysis_results_as_dataframe(self, record_id: str, table_name: str, analysis_type: str) -> Optional[pd.DataFrame]:
        """Get specific analysis results as a pandas DataFrame"""
        table_name = self._safe_table(table_name)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT results FROM {table_name} WHERE record_id = ? AND analysis_type = ?", 
                             (record_id, analysis_type))
                row = cursor.fetchone()
                
                if row:
                    try:
                        results_data = json.loads(row[0])
                        if isinstance(results_data, list):
                            return pd.DataFrame(results_data)
                        elif isinstance(results_data, dict):
                            return pd.DataFrame([results_data])
                        else:
                            return pd.DataFrame({'result': [results_data]})
                    except Exception as e:
                        print(f"Error converting to DataFrame: {e}")
                        return None
                return None
        except Exception as e:
            print(f"Error retrieving analysis results as DataFrame: {e}")
            return None
    
    def export_analysis_results(self, record_id: str, export_format: str = 'csv') -> Dict[str, str]:
        """Export all analysis results for a record to files"""
        try:
            export_files = {}
            tables = ['sleep_analysis', 'activity_analysis', 'light_analysis']
            
            for table in tables:
                results = self.get_analysis_results(record_id, table)
                for result in results:
                    analysis_type = result['analysis_type']
                    try:
                        if isinstance(result['results'], list):
                            df = pd.DataFrame(result['results'])
                        elif isinstance(result['results'], dict):
                            df = pd.DataFrame([result['results']])
                        else:
                            df = pd.DataFrame({'result': [result['results']]})
                        
                        filename = f"{record_id}_{analysis_type}.{export_format}"
                        if export_format == 'csv':
                            df.to_csv(filename, index=False)
                        elif export_format == 'excel':
                            df.to_excel(filename, index=False)
                        
                        export_files[analysis_type] = filename
                    except Exception as e:
                        print(f"Error exporting {analysis_type}: {e}")
            
            return export_files
        except Exception as e:
            print(f"Error exporting analysis results: {e}")
            return {}

    def record_exists(self, record_id: str) -> bool:
        """Check if a record ID already exists"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM analysis_records WHERE id = ?", (record_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            print(f"Error checking record existence: {e}")
            return False

    def get_aggregated_metrics_for_ids(
        self,
        record_ids: List[str],
        include_tables: Optional[List[str]] = None,
        include_analysis_types: Optional[List[str]] = None,
        agg: str = "mean",
    ) -> pd.DataFrame:
        """
        Aggregate numeric metrics for given IDs across saved analyses.

        For each record_id, this function:
        - Loads all results from sleep/activity/light tables (or a subset via include_tables)
        - Optionally filters by analysis_type via include_analysis_types
        - Converts result payloads to DataFrames when possible
        - Collects all numeric columns and computes the requested aggregation (default mean)
        - Returns a single row per record_id with columns prefixed by "{table}.{analysis_type}.{column}_{agg}"

        Parameters
        ----------
        record_ids : List[str]
            IDs to aggregate
        include_tables : Optional[List[str]]
            Subset of tables to include; default is all ['sleep_analysis','activity_analysis','light_analysis']
        include_analysis_types : Optional[List[str]]
            If provided, only include these analysis_type names
        agg : str
            Aggregation to compute on numeric columns ('mean', 'median', etc. supported by pandas)

        Returns
        -------
        pd.DataFrame
            One row per record_id; numeric aggregates as columns
        """
        tables = include_tables or ["sleep_analysis", "activity_analysis", "light_analysis"]

        rows: List[Dict[str, Any]] = []

        for rid in record_ids:
            row: Dict[str, Any] = {"id": rid}
            try:
                for table in tables:
                    try:
                        results = self.get_analysis_results(rid, table)
                    except Exception as e:
                        print(f"Warning: failed to read results for id={rid}, table={table}: {e}")
                        continue

                    # Group by analysis_type across possibly multiple entries
                    by_type: Dict[str, List[pd.DataFrame]] = {}
                    for r in results:
                        a_type = r.get("analysis_type", "unknown")
                        if include_analysis_types and a_type not in include_analysis_types:
                            continue

                        payload = r.get("results")
                        df_payload: Optional[pd.DataFrame] = None

                        # Try to coerce payload into a DataFrame
                        try:
                            if isinstance(payload, list):
                                # list of dicts or primitives
                                df_payload = pd.DataFrame(payload)
                            elif isinstance(payload, dict):
                                df_payload = pd.DataFrame([payload])
                            else:
                                # Could be a string or other: attempt JSON load then DataFrame
                                try:
                                    if isinstance(payload, (str, bytes, bytearray)) and payload:
                                        parsed = json.loads(payload)
                                        if isinstance(parsed, list):
                                            df_payload = pd.DataFrame(parsed)
                                        elif isinstance(parsed, dict):
                                            df_payload = pd.DataFrame([parsed])
                                except Exception:
                                    df_payload = None
                        except Exception:
                            df_payload = None

                        if df_payload is None or df_payload.empty:
                            continue

                        # Keep only numeric columns
                        numeric_df = df_payload.select_dtypes(include=["number"]).copy()
                        if numeric_df.empty:
                            continue

                        by_type.setdefault(a_type, []).append(numeric_df)

                    # Reduce each analysis_type: concat then aggregate
                    for a_type, frames in by_type.items():
                        try:
                            all_vals = pd.concat(frames, ignore_index=True)
                            if all_vals.empty:
                                continue
                            agg_vals = getattr(all_vals, agg)() if hasattr(all_vals, agg) else all_vals.mean()
                            # add columns with prefix
                            for col, val in agg_vals.items():
                                key = f"{table}.{a_type}.{col}_{agg}"
                                # ensure Python primitives for JSON/display friendliness
                                if pd.isna(val):
                                    row[key] = float("nan")
                                else:
                                    row[key] = float(val)
                        except Exception as e:
                            print(f"Warning: aggregation failed for id={rid}, table={table}, type={a_type}: {e}")

            except Exception as e:
                print(f"Warning: aggregation failed for id={rid}: {e}")

            rows.append(row)

        # Assemble final DataFrame and sort columns: id first, then others sorted
        if not rows:
            return pd.DataFrame(columns=["id"])  # empty result

        df_out = pd.DataFrame(rows)
        # Move id to first column
        cols = list(df_out.columns)
        if "id" in cols:
            cols = ["id"] + [c for c in cols if c != "id"]
            df_out = df_out[cols]
        return df_out