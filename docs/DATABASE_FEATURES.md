# Circadian Medicine App - Database Features

This document describes the new database features added to the Circadian Medicine app.

## New Features Added

### 1. Analysis Information Input
After the header image, the app now includes:
- **Analysis ID**: Unique identifier for each analysis run
- **Description**: Brief description of the analysis
- **Date**: Automatically captured current date and time

### 2. Database Storage System
- **Database File**: `Actigraph_record.db` (SQLite database)
- **Automatic Creation**: Database and tables are created automatically if they don't exist
- **Data Structure**: Organized into multiple tables for efficient storage and retrieval

### 3. Database Schema

#### Main Tables:
1. **analysis_records**: Core analysis information
   - `id` (TEXT, PRIMARY KEY): Unique analysis identifier
   - `description` (TEXT): Analysis description
   - `date` (TEXT): Analysis date/time
   - `created_at` (TEXT): Record creation timestamp
   - `file_name` (TEXT): Name of uploaded file
   - `selected_dates` (TEXT): JSON array of selected dates

2. **sleep_analysis**: Sleep-related analysis results
   - `record_id` (TEXT): Foreign key to analysis_records
   - `analysis_type` (TEXT): Type of sleep analysis
   - `results` (TEXT): JSON-formatted results

3. **activity_analysis**: Activity-related analysis results
   - `record_id` (TEXT): Foreign key to analysis_records
   - `analysis_type` (TEXT): Type of activity analysis
   - `results` (TEXT): JSON-formatted results

4. **light_analysis**: Light-related analysis results
   - `record_id` (TEXT): Foreign key to analysis_records
   - `analysis_type` (TEXT): Type of light analysis
   - `results` (TEXT): JSON-formatted results

### 4. Stored Analysis Types

#### Sleep Analyses:
- `sleep_light_exposure`: Light exposure during sleep periods
- `sleep_periods`: Sleep onset, offset, and periods
- `cpd_mid_sleep`: Circadian Phase Dispersion of mid-sleep
- `sri_sleep`: Sleep Regularity Index

#### Activity Analyses:
- `activity_is_iv`: Interdaily Stability and Intradaily Variability
- `activity_l5_m10_ra`: L5, M10, and Relative Amplitude
- `activity_cosinor`: Cosinor fit analysis
- `cpd_activity_acrophase`: CPD of activity acrophase

#### Light Analyses:
- `light_is_iv`: Light IS and IV analysis
- `light_l5_m10_ra`: Light L5, M10, and RA
- `light_cosinor`: Light cosinor fit
- `cpd_light_acrophase`: CPD of light acrophase

### 5. User Interface Enhancements

#### Tab-based Interface:
- **📊 New Analysis**: Run new analyses with data upload and processing
- **📋 View Records**: Browse and manage saved analysis records

#### New Analysis Tab Features:
- Input validation for required fields
- Duplicate ID prevention
- Real-time feedback during analysis
- Success confirmation upon completion

#### View Records Tab Features:
- Expandable record cards with detailed information
- Analysis type listings by category (Sleep, Activity, Light)
- Record deletion functionality
- Empty state guidance for new users

### 6. Data Flow

1. **Input Phase**: User provides ID, description, and uploads data file
2. **Validation Phase**: System checks for required fields and ID uniqueness
3. **Analysis Phase**: All existing analyses are performed on the data
4. **Storage Phase**: Results are automatically saved to database
5. **Confirmation Phase**: User receives success confirmation

### 7. Database Module (`tools/database.py`)

The `ActigraphDB` class provides:
- Database initialization and table creation
- Record management (create, read, delete)
- Analysis result storage and retrieval
- Data validation and error handling
- JSON serialization for complex data types

### 8. Benefits

1. **Record Keeping**: Complete history of all analyses performed
2. **Data Integrity**: Structured storage with relationships between records
3. **Searchability**: Easy retrieval of past analyses by ID
4. **Auditability**: Timestamps and metadata for all records
5. **Scalability**: SQLite database can handle large numbers of records
6. **Portability**: Single database file can be easily backed up or shared

### 9. Usage Instructions

1. **Running New Analysis**:
   - Enter unique Analysis ID and description
   - Upload your data file
   - Select dates to analyze
   - Click "Run Analysis"
   - All results are automatically saved

2. **Viewing Past Records**:
   - Go to "View Records" tab
   - Browse through saved analyses
   - Expand records to see details
   - Delete records if no longer needed

3. **Database Location**:
   - Database file: `Actigraph_record.db` (in app root directory)
   - Automatically created on first use
   - Contains all analysis history

### 10. Technical Notes

- **Database Type**: SQLite (serverless, file-based)
- **Data Format**: JSON for complex analysis results
- **Error Handling**: Comprehensive error catching and user feedback
- **Performance**: Optimized for typical analysis workloads
- **Compatibility**: Works with all existing analysis tools

The database system maintains full compatibility with existing functionality while adding comprehensive record-keeping capabilities to track the history of all circadian medicine analyses performed with the application.