# Sample Data

This directory contains example actigraphy data files for testing the application.

## Available Files

- `IMU.CSV` - Inertial Measurement Unit data
- `PULSE.CSV` - Pulse/heart rate data
- `SPECT.CSV` - Spectral data
- `TEMP.CSV` - Temperature data
- `Test01_wrist.txt` - Sample wrist actigraphy data

## Data Format

The application expects CSV files with the following columns:

### Required Columns
- `DATE/TIME` - Timestamp in format: MM/DD/YYYY HH:MM:SS
- `PIMn` - Physical activity measurement (Proportional Integrating Measure)
- `MELANOPIC EDI` - Melanopic Equivalent Daylight Illuminance (lux)
- `WHITE LIGHT (LUX)` - White light illuminance
- `SLEEP/WAKE` - Binary sleep state (0 = wake, 1 = sleep)

### Optional Columns
- Additional sensor data as needed

## Example Format

```csv
DATE/TIME,PIMn,MELANOPIC EDI,WHITE LIGHT (LUX),SLEEP/WAKE
01/15/2025 08:00:00,45.2,250.3,300.1,0
01/15/2025 08:01:00,52.1,245.8,295.4,0
01/15/2025 08:02:00,38.9,255.1,305.2,0
```

## Data Privacy

⚠️ **IMPORTANT**: Do not commit actual patient data to this repository. 
The `.gitignore` file is configured to exclude CSV files from version control.

## Using Sample Data

1. Upload files through the Streamlit interface
2. Select date range for analysis
3. The app will automatically detect and parse the data

## Generating Test Data

You can generate synthetic test data for development using:

```python
import pandas as pd
import numpy as np

# Generate 24 hours of synthetic data
dates = pd.date_range('2025-01-15', periods=1440, freq='min')
data = pd.DataFrame({
    'DATE/TIME': dates,
    'PIMn': np.random.uniform(0, 100, 1440),
    'MELANOPIC EDI': np.random.uniform(0, 500, 1440),
    'WHITE LIGHT (LUX)': np.random.uniform(0, 600, 1440),
    'SLEEP/WAKE': [0 if 6 <= x.hour < 22 else 1 for x in dates]
})
data.to_csv('test_data.csv', index=False)
```

## Data Requirements

- Minimum duration: 2 days (for most metrics)
- Recommended duration: 7-14 days
- Sampling rate: 1 minute intervals (preferred)
- Time zone: Local time (will be converted to Europe/Berlin by default)

## Troubleshooting

### "No dates found in data"
- Check date format matches: MM/DD/YYYY HH:MM:SS
- Ensure DATE/TIME column exists

### "Insufficient data for analysis"
- Most metrics require at least 2 days of data
- Some metrics (SRI) need 2+ consecutive days

### "Column not found"
- Verify all required columns are present
- Check for correct column names (case-sensitive)
