# Synthetic Data Validation - Quick Start Guide

## Overview
This system generates synthetic actigraph data with known characteristics to validate all circadian medicine analysis functions before publication.

## 📁 Files Created

### Notebooks
1. **generate_synthetic_data.ipynb** - Generates all synthetic datasets
2. **validation_tests.ipynb** - Runs validation tests

### Outputs (Generated)
- `period1_regular.txt` - Regular sleep pattern (baseline)
- `period1_irregular.txt` - Irregular sleep times
- `period1_high_light.txt` - High light exposure
- `period1_low_light.txt` - Low light exposure
- `period2_regular.txt` - Regular pattern (week 2)
- `period2_shifted.txt` - Phase-shifted (jet lag)
- `period2_fragmented.txt` - Fragmented sleep
- `period2_delayed.txt` - Delayed sleep phase
- `expected_metrics.json` - Pre-calculated expected values
- `validation_report.json` - Test results

## 🚀 Quick Start

### Step 1: Generate Synthetic Data
```bash
# Open the generation notebook
jupyter notebook generate_synthetic_data.ipynb

# Or in VS Code, just open and run all cells
```

**What it does:**
- Creates 8 different synthetic datasets (7 days each, 1-minute intervals)
- Each dataset represents a different circadian scenario
- Calculates expected metrics for validation
- Exports data in the correct format for your app

**Expected output:**
- 8 .txt files with synthetic data
- expected_metrics.json
- synthetic_data_preview.png (visualization)

### Step 2: Run Validation Tests
```bash
# Open the validation notebook
jupyter notebook validation_tests.ipynb

# Or in VS Code, just open and run all cells
```

**What it does:**
- Loads each synthetic dataset
- Runs through ALL analysis functions
- Compares actual results with expected values
- Reports pass/fail for each metric
- Generates validation_report.json

**Success criteria:**
- All tests should pass
- Functions correctly identify sleep patterns
- Metrics match expected ranges

### Step 3: Test in Main App
1. Start your Streamlit app
2. Upload synthetic datasets using the app interface
3. Compare different periods:
   - period1_regular vs period2_regular (control)
   - period1_regular vs period2_shifted (phase shift)
   - period1_regular vs period1_irregular (regularity)
   - period1_high_light vs period1_low_light (light impact)

## 📊 Test Scenarios Explained

### Period 1 (Baseline Week)

**period1_regular**
- Sleep: 23:00 - 07:00 (8 hours)
- Pattern: Highly regular
- Light: Medium daytime exposure (~500 lux)
- **Use for:** Baseline comparison

**period1_irregular**
- Sleep times vary each day (22:00, 01:00, 23:00, 03:00, etc.)
- Pattern: Highly irregular
- **Use for:** Testing CPD and SRI calculations
- **Expected:** High CPD, Low SRI

**period1_high_light**
- Sleep: 23:00 - 07:00
- Light: High daytime exposure (~1500 lux)
- **Use for:** Light exposure impact analysis

**period1_low_light**
- Sleep: 23:00 - 07:00
- Light: Low daytime exposure (~150 lux)
- **Use for:** Comparing with high_light

### Period 2 (Intervention/Changed Week)

**period2_regular**
- Sleep: 23:00 - 07:00 (same as period1_regular)
- **Use for:** Control comparison (should show no significant changes)

**period2_shifted**
- Sleep: 02:00 - 10:00 (3-hour phase delay)
- **Use for:** Jet lag simulation
- **Expected:** CPD should detect 3-hour shift

**period2_fragmented**
- Sleep: 23:00 - 07:00 with awakenings at 01:00 and 04:00
- **Use for:** Sleep quality analysis
- **Expected:** High IV (intradaily variability)

**period2_delayed**
- Sleep: 01:00 - 09:00 (2-hour delay)
- **Use for:** Delayed sleep phase disorder simulation

## ✅ Validation Checklist

Before publication, verify:

- [ ] All 8 datasets generated successfully
- [ ] All validation tests pass (or failures explained)
- [ ] Datasets load correctly in main app
- [ ] Sleep onset/offset detected accurately
- [ ] CPD calculations correct for regular vs irregular
- [ ] SRI shows expected high/low values
- [ ] IS/IV metrics in expected ranges
- [ ] L5/M10/RA calculated correctly
- [ ] Cosinor fits converge
- [ ] Phase shifts detected in comparisons
- [ ] Light exposure metrics accurate
- [ ] AI analysis runs on synthetic comparisons
- [ ] No errors in any analysis pipeline

## 📈 Expected Metrics Summary

### Regular Patterns (period1_regular, period2_regular)
- CPD: < 1.5 hours (low variability)
- SRI: > 80% (high regularity)
- IS: > 0.6 (high interdaily stability)
- RA: 0.8 - 0.95 (strong rhythm)

### Irregular Pattern (period1_irregular)
- CPD: > 1.5 hours (high variability)
- SRI: < 70% (low regularity)
- IS: < 0.6 (low interdaily stability)

### Fragmented Pattern (period2_fragmented)
- IV: > 1.0 (high intradaily variability)
- Multiple detected awakenings

### Shifted Patterns (period2_shifted, period2_delayed)
- Acrophase shift matches sleep time shift
- CPD detects phase difference when compared to regular

## 🔧 Troubleshooting

**Issue:** Datasets not generated
- **Solution:** Run all cells in generate_synthetic_data.ipynb

**Issue:** Validation tests fail
- **Solution:** Check error messages, verify data format, ensure all tools are imported

**Issue:** App can't load synthetic data
- **Solution:** Verify file format matches real data (semicolon-separated, correct headers)

**Issue:** Metrics don't match expected values
- **Solution:** Review expected_metrics.json, adjust tolerances if needed, verify calculation logic

## 📝 Notes for Publication

Include in your publication:
1. "All analysis functions validated using synthetic datasets with known characteristics"
2. Reference the validation report results
3. Mention test scenarios covered
4. Report validation success rate

## 🎯 Next Steps After Validation

1. Document any edge cases discovered
2. Update README with validation results
3. Include synthetic_data/ in repository
4. Add validation to CI/CD pipeline (optional)
5. Ready for publication! 🎉
