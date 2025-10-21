# Circadian Medicine Analysis Platform - Tools Package

This package contains all the analysis tools for circadian medicine data processing.

## Modules

### Data Processing
- `upload_file.py` - File upload and data preprocessing
- `database.py` - SQLite database management

### Sleep Analysis
- `sleep_light_exposure.py` - Light exposure during sleep
- `sleep_on_off_mid.py` - Sleep onset, offset, midpoint
- `sleep_CPD_ms.py` - Circadian Phase Dispersion for sleep
- `sleep_SRI.py` - Sleep Regularity Index

### Activity Analysis
- `activity_plotter.py` - Activity visualization
- `activity_IS_IV.py` - Interdaily Stability & Intradaily Variability
- `activity_L5_M10_RA.py` - L5, M10, Relative Amplitude
- `activity_cosinor.py` - Cosinor rhythm analysis
- `activity_CPD.py` - Circadian Phase Dispersion for activity

### Light Analysis
- `light_plotter.py` - Light exposure visualization
- `light_IS_IV.py` - IS & IV for light
- `light_L5_M10_RA.py` - L5, M10, RA for light
- `light_cosinor.py` - Cosinor rhythm analysis for light
- `light_CPD.py` - CPD for light exposure

### Reporting & AI
- `report_generator.py` - HTML and JSON report generation
- `llm_conversation.py` - AI-powered analysis using Ollama

## Usage

```python
from tools.sleep_SRI import calculate_sri_from_pimn
from tools.activity_IS_IV import compute_rolling_2day_is_iv_activity
from tools.report_generator import generate_comparison_report

# Use functions in your analysis
sri_results = calculate_sri_from_pimn(data, ...)
```

## Dependencies

All tools require:
- pandas
- numpy
- scipy (for cosinor fitting)
- matplotlib (for plotting)
- ollama (for AI features)
