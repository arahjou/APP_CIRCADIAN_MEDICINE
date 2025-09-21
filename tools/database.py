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
            
            conn.commit()
    
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
    
    def _save_analysis_results(self, table_name: str, record_id: str, analysis_type: str, results: Any) -> bool:
        """Helper method to save analysis results to specific table"""
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