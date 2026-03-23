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
            
            # Migrate existing databases — add anamnesis column if it doesn't exist yet
            try:
                cursor.execute("ALTER TABLE analysis_records ADD COLUMN anamnesis TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists

            conn.commit()
    
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