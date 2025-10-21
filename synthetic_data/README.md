# Synthetic Data for Validation Testing

This folder contains synthetic datasets designed to validate the circadian medicine analysis functions.

## Structure

- `generate_synthetic_data.ipynb` - Main notebook to generate all synthetic datasets
- `validation_tests.ipynb` - Notebook to run validation tests and verify expected metrics
- `expected_metrics.json` - Pre-calculated expected outputs for each dataset
- `period*.txt` - Generated synthetic data files

## Test Scenarios

### Period 1 Datasets:
1. **period1_regular.txt** - Regular sleep/wake pattern (23:00-07:00)
2. **period1_irregular.txt** - Irregular sleep pattern (variable times)
3. **period1_high_light.txt** - Regular pattern with high light exposure
4. **period1_low_light.txt** - Regular pattern with low light exposure

### Period 2 Datasets:
1. **period2_regular.txt** - Regular pattern (similar to period1)
2. **period2_shifted.txt** - Phase-shifted pattern (02:00-10:00) - simulates jet lag
3. **period2_fragmented.txt** - Fragmented sleep pattern
4. **period2_delayed.txt** - Delayed sleep phase (01:00-09:00)

## Data Format

All files follow this format:
```
DATE/TIME;PIMn;MELANOPIC EDI
11/01/2024 11:17:39;99.4;188.72
```

- **DATE/TIME**: Format `MM/DD/YYYY HH:MM:SS`
- **PIMn**: Activity level (0-200, higher = more active)
- **MELANOPIC EDI**: Light exposure (0-2000+ lux)

## Expected Metrics

Each dataset has pre-calculated expected values for:
- Sleep onset, offset, mid-sleep times
- CPD (Circadian Phase Dispersion)
- SRI (Sleep Regularity Index)
- IS/IV (Interdaily Stability/Intradaily Variability)
- L5, M10, RA values
- Cosinor parameters (amplitude, acrophase)

## Usage

1. Run `generate_synthetic_data.ipynb` to create datasets
2. Run `validation_tests.ipynb` to verify all functions work correctly
3. Compare actual outputs with `expected_metrics.json`
