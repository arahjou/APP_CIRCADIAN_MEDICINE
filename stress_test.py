"""
Stress test for all analytical tools in the Circadian Medicine App.
Tests scientific correctness, error handling, and edge cases.
"""
import pandas as pd
import numpy as np
import sys
import traceback
sys.path.insert(0, '.')

from datetime import datetime, timedelta
import pytz

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
results = []

def check(name, condition, msg=""):
    status = PASS if condition else FAIL
    results.append((status, name, msg))
    icon = "✅" if condition else "❌"
    print(f"  {icon} {name}: {msg}" if msg else f"  {icon} {name}")

def warn(name, msg):
    results.append((WARN, name, msg))
    print(f"  ⚠️  {name}: {msg}")

# ─────────────────────────────────────────────
# Generate 5 days of 1-minute synthetic data
# ─────────────────────────────────────────────
tz = pytz.timezone('Europe/Berlin')
start = tz.localize(datetime(2024, 1, 11, 11, 0, 0))
n = 5 * 24 * 60  # 7200 samples
times = [start + timedelta(minutes=i) for i in range(n)]
hours_arr = np.array([t.hour + t.minute / 60 for t in times])

np.random.seed(42)
pimn_base = 30 * np.maximum(np.cos(2 * np.pi * (hours_arr - 14) / 24), 0) + 2
pimn = np.abs(np.random.normal(pimn_base, 5)).clip(0)
for i, t in enumerate(times):
    if t.hour >= 23 or t.hour < 7:
        pimn[i] = np.abs(np.random.normal(1, 0.5))

melan_base = 200 * np.maximum(np.cos(2 * np.pi * (hours_arr - 13) / 24), 0) + 1
melan = np.abs(np.random.normal(melan_base, 20)).clip(0)
for i, t in enumerate(times):
    if t.hour >= 22 or t.hour < 7:
        melan[i] = np.abs(np.random.normal(0.5, 0.2))

df = pd.DataFrame({
    'DATE/TIME': times,
    'TEMPERATURE': np.random.normal(26, 0.5, n),
    'PIMn': pimn,
    'TATn': pimn * 0.1,
    'ZCMn': pimn * 0.05,
    'MELANOPIC EDI': melan,
})
df['DATE'] = df['DATE/TIME'].dt.date.astype(str)
df['TIME'] = df['DATE/TIME'].dt.time
df['HOUR'] = (df['DATE/TIME'].dt.hour + df['DATE/TIME'].dt.minute / 60).round(2)
df['Transition'] = df['DATE/TIME'].dt.tz_convert(None).dt.to_period('D').dt.start_time

print("=" * 60)
print("STRESS TEST — Circadian Medicine Analytical Tools")
print("=" * 60)
print(f"\nSynthetic data: {n} rows, {df['DATE'].nunique()} days\n")

# ─────────────────────────────────────────────────────────────
# 1. SLEEP LIGHT EXPOSURE
# ─────────────────────────────────────────────────────────────
print("\n[1] sleep_light_exposure.analyze_sleep_light_exposure")
try:
    from tools.sleep_light_exposure import analyze_sleep_light_exposure
    res = analyze_sleep_light_exposure(df.copy())
    check("Returns dict with metric1/2/3", isinstance(res, dict) and all(k in res for k in ['metric1','metric2','metric3']))
    # metric1: minutes of light during sleep
    m1 = res['metric1']
    if isinstance(m1, list):
        check("metric1 values are non-negative", all(v['minutes'] >= 0 for v in m1))
    else:
        warn("metric1", f"No light during sleep detected: {m1}")
    # metric3 should show non-bright minutes after wakeup
    m3 = res['metric3']
    if isinstance(m3, list):
        check("metric3 values are non-negative", all(v['minutes'] >= 0 for v in m3))
    else:
        warn("metric3", f"metric3: {m3}")
except Exception as e:
    check("No exception", False, traceback.format_exc())

# ─────────────────────────────────────────────────────────────
# 2. SLEEP PERIODS
# ─────────────────────────────────────────────────────────────
print("\n[2] sleep_on_off_mid.analyze_sleep_periods")
sleep_periods = None
try:
    from tools.sleep_on_off_mid import analyze_sleep_periods
    sleep_periods = analyze_sleep_periods(df.copy())
    check("Returns DataFrame", isinstance(sleep_periods, pd.DataFrame))
    check("Has required columns", all(c in sleep_periods.columns for c in ['mid_sleep_DATE','Mid_sleep_Time']))
    check("Not empty (sleep detected)", len(sleep_periods) > 0, f"{len(sleep_periods)} periods found")
    if not sleep_periods.empty:
        durations_valid = True
        for _, row in sleep_periods.iterrows():
            onset = pd.Timestamp(str(row['Sleep_onset_DATE']) + ' ' + str(row['Sleep_onset_Time']))
            offset = pd.Timestamp(str(row['Sleep_offset_DATE']) + ' ' + str(row['Sleep_offset_TIME']))
            dur = (offset - onset).total_seconds() / 3600
            if dur < 0 or dur > 24:
                durations_valid = False
        check("Sleep durations in range 0-24h", durations_valid)
        # Verify mid-sleep falls between onset and offset
        for _, row in sleep_periods.iterrows():
            onset_dt = pd.Timestamp(str(row['Sleep_onset_DATE']) + ' ' + str(row['Sleep_onset_Time']))
            offset_dt = pd.Timestamp(str(row['Sleep_offset_DATE']) + ' ' + str(row['Sleep_offset_TIME']))
            mid_dt = pd.Timestamp(str(row['mid_sleep_DATE']) + ' ' + str(row['Mid_sleep_Time']))
        check("Mid-sleep is between onset and offset", onset_dt <= mid_dt <= offset_dt)
except Exception as e:
    check("No exception", False, traceback.format_exc())

# ─────────────────────────────────────────────────────────────
# 3. Sleep CPD
# ─────────────────────────────────────────────────────────────
print("\n[3] sleep_CPD_ms — CPD of mid-sleep")
cpd_mid = None
try:
    from tools.sleep_CPD_ms import build_centered_midpoint_hours, calculate_single_person_cpd
    if sleep_periods is not None and not sleep_periods.empty:
        mid_data = build_centered_midpoint_hours(sleep_periods)
        check("midpoint_hours_centered in (-12, 12]", mid_data['midpoint_hours_centered'].between(-12, 12, inclusive='both').all())
        cpd_mid = calculate_single_person_cpd(mid_data, date_col='mid_sleep_DATE', midpoint_col='midpoint_hours_centered')
        check("cpd_hours all non-negative (where not NaN)", (cpd_mid['cpd_hours'].dropna() >= 0).all())
        check("mean_midpoint_hours scalar in (-12,12]", -12 <= cpd_mid['mean_midpoint_hours'].iloc[0] <= 12)
        # First row CPD should be NaN (no previous night)
        check("First row cpd_hours is NaN (no prior night)", pd.isna(cpd_mid['cpd_hours'].iloc[0]))
    else:
        warn("sleep_CPD_ms", "Skipped - no sleep periods detected")
    # empty DataFrame edge case — should now return empty df, not raise
    try:
        empty_sp = pd.DataFrame(columns=sleep_periods.columns if sleep_periods is not None else ['mid_sleep_DATE','Mid_sleep_Time'])
        mid_empty = build_centered_midpoint_hours(empty_sp)
        check("Empty sleep periods → empty midpoint df (no crash)", mid_empty.empty)
    except Exception as e_empty:
        check("Empty sleep periods → no crash", False, str(e_empty))
except Exception as e:
    check("No exception", False, traceback.format_exc())

# ─────────────────────────────────────────────────────────────
# 4. Sleep SRI
# ─────────────────────────────────────────────────────────────
print("\n[4] sleep_SRI.calculate_sri_from_pimn")
try:
    from tools.sleep_SRI import calculate_sri_from_pimn
    sri = calculate_sri_from_pimn(df.copy(), timestamp_col='DATE/TIME', pimn_col='PIMn', window_days=2, slide_interval=1)
    check("Returns DataFrame", isinstance(sri, pd.DataFrame))
    check("Has SRI column", 'SRI' in sri.columns)
    if not sri.empty:
        check("SRI values in [-100, 100]", sri['SRI'].dropna().between(-100, 100).all(), f"range: {sri['SRI'].min():.1f}–{sri['SRI'].max():.1f}")
        check("valid_epochs_pct in [0,100]", sri['valid_epochs_pct'].dropna().between(0.0, 100.0).all())
        check("No all-NaN SRI rows", not sri['SRI'].isna().all())
    else:
        warn("SRI", "Empty result returned")
except Exception as e:
    check("No exception", False, traceback.format_exc())

# ─────────────────────────────────────────────────────────────
# 5. Activity IS/IV
# ─────────────────────────────────────────────────────────────
print("\n[5] activity_IS_IV.compute_rolling_2day_is_iv_activity")
try:
    from tools.activity_IS_IV import compute_rolling_2day_is_iv_activity
    isiv = compute_rolling_2day_is_iv_activity(df.copy(), time_col='DATE/TIME', value_col='PIMn')
    check("Returns DataFrame", isinstance(isiv, pd.DataFrame))
    check("Has IS_2day and IV_2day", all(c in isiv.columns for c in ['IS_2day','IV_2day']))
    check("n_rows == n_days - 1", len(isiv) == df['DATE'].nunique() - 1, f"got {len(isiv)} rows")
    if not isiv.empty:
        check("IS in [0, 1] (where not NaN)", isiv['IS_2day'].dropna().between(0.0, 1.0).all(),
              f"IS range: {isiv['IS_2day'].min():.3f}–{isiv['IS_2day'].max():.3f}")
        check("IV >= 0 (where not NaN)", (isiv['IV_2day'].dropna() >= 0).all(),
              f"IV range: {isiv['IV_2day'].min():.3f}–{isiv['IV_2day'].max():.3f}")
        check("No all-NaN IS rows", not isiv['IS_2day'].isna().all())
except Exception as e:
    check("No exception", False, traceback.format_exc())

# ─────────────────────────────────────────────────────────────
# 6. Activity L5/M10/RA
# ─────────────────────────────────────────────────────────────
print("\n[6] activity_L5_M10_RA.compute_daily_L5_M10_RA_activity")
try:
    from tools.activity_L5_M10_RA import compute_daily_L5_M10_RA_activity
    l5m10 = compute_daily_L5_M10_RA_activity(df.copy(), time_col='DATE/TIME', value_col='PIMn')
    check("Returns DataFrame", isinstance(l5m10, pd.DataFrame))
    check("Has required columns", all(c in l5m10.columns for c in ['date','M10_mean','L5_mean','RA']))
    if not l5m10.empty:
        valid_ra = l5m10['RA'].dropna()
        check("RA in [0, 1] (where not NaN)", valid_ra.between(0.0, 1.0).all(),
              f"RA range: {valid_ra.min():.3f}–{valid_ra.max():.3f}")
        check("M10 > L5 (activity: high during day)", (l5m10['M10_mean'].dropna() >= l5m10['L5_mean'].dropna()).all())
        check("No all-NaN rows in M10", not l5m10['M10_mean'].isna().all())
except Exception as e:
    check("No exception", False, traceback.format_exc())

# ─────────────────────────────────────────────────────────────
# 7. Activity Cosinor
# ─────────────────────────────────────────────────────────────
print("\n[7] activity_cosinor.fit_cosinor_daily_activity")
cosinor_act = None
try:
    from tools.activity_cosinor import fit_cosinor_daily_activity
    cosinor_act = fit_cosinor_daily_activity(df.copy(), datetime_col='DATE/TIME', value_col='PIMn')
    check("Returns DataFrame", isinstance(cosinor_act, pd.DataFrame))
    check("Has required columns", all(c in cosinor_act.columns for c in ['date','mesor','amplitude','acrophase_hours','r_squared']))
    if not cosinor_act.empty:
        check("acrophase_hours in [0, 24)", cosinor_act['acrophase_hours'].dropna().between(0.0, 24.0, inclusive='left').all(),
              f"range: {cosinor_act['acrophase_hours'].min():.1f}–{cosinor_act['acrophase_hours'].max():.1f}")
        check("amplitude >= 0", (cosinor_act['amplitude'].dropna() >= 0).all())
        check("r_squared in [0, 1]", cosinor_act['r_squared'].dropna().between(0.0, 1.0).all(),
              f"R²: {cosinor_act['r_squared'].min():.3f}–{cosinor_act['r_squared'].max():.3f}")
        # Acrophase for activity should be ~afternoon (12-20h)
        mean_acroph = cosinor_act['acrophase_hours'].mean()
        check("Activity acrophase in afternoon (10-20h)", 10 <= mean_acroph <= 20,
              f"mean acrophase = {mean_acroph:.1f}h")
except Exception as e:
    check("No exception", False, traceback.format_exc())

# ─────────────────────────────────────────────────────────────
# 8. Activity CPD (acrophase)
# ─────────────────────────────────────────────────────────────
print("\n[8] activity_CPD.calculate_cpd_activity")
try:
    from tools.activity_CPD import calculate_cpd_activity
    if cosinor_act is not None and not cosinor_act.empty:
        cpd_act = calculate_cpd_activity(cosinor_act, ms_col='acrophase_hours', date_col='date')
        check("Returns DataFrame", isinstance(cpd_act, pd.DataFrame))
        check("Has cpd_hours column", 'cpd_hours' in cpd_act.columns)
        check("cpd_hours non-negative (where not NaN)", (cpd_act['cpd_hours'].dropna() >= 0).all())
        check("First row cpd_hours is NaN (no prior day)", pd.isna(cpd_act['cpd_hours'].iloc[0]))
    else:
        warn("activity_CPD", "Skipped — cosinor returned empty")
except Exception as e:
    check("No exception", False, traceback.format_exc())

# ─────────────────────────────────────────────────────────────
# 9. Light IS/IV
# ─────────────────────────────────────────────────────────────
print("\n[9] light_IS_IV.compute_rolling_2day_is_iv_light")
try:
    from tools.light_IS_IV import compute_rolling_2day_is_iv_light
    light_isiv = compute_rolling_2day_is_iv_light(df.copy(), time_col='DATE/TIME', value_col='MELANOPIC EDI')
    check("Returns DataFrame", isinstance(light_isiv, pd.DataFrame))
    check("n_rows == n_days - 1", len(light_isiv) == df['DATE'].nunique() - 1)
    if not light_isiv.empty:
        check("Light IS in [0, 1]", light_isiv['IS_2day'].dropna().between(0.0, 1.0).all(),
              f"IS: {light_isiv['IS_2day'].min():.3f}–{light_isiv['IS_2day'].max():.3f}")
        check("Light IV >= 0", (light_isiv['IV_2day'].dropna() >= 0).all())
except Exception as e:
    check("No exception", False, traceback.format_exc())

# ─────────────────────────────────────────────────────────────
# 10. Light L5/M10/RA
# ─────────────────────────────────────────────────────────────
print("\n[10] light_L5_M10_RA.compute_daily_L5_M10_RA_light")
try:
    from tools.light_L5_M10_RA import compute_daily_L5_M10_RA_light
    light_l5m10 = compute_daily_L5_M10_RA_light(df.copy(), time_col='DATE/TIME', value_col='MELANOPIC EDI')
    check("Returns DataFrame", isinstance(light_l5m10, pd.DataFrame))
    if not light_l5m10.empty:
        valid_ra = light_l5m10['RA'].dropna()
        check("Light RA in [0, 1]", valid_ra.between(0.0, 1.0).all(),
              f"RA: {valid_ra.min():.3f}–{valid_ra.max():.3f}")
        check("Light M10 > L5 (high by midday)", (light_l5m10['M10_mean'].dropna() >= light_l5m10['L5_mean'].dropna()).all())
except Exception as e:
    check("No exception", False, traceback.format_exc())

# ─────────────────────────────────────────────────────────────
# 11. Light Cosinor
# ─────────────────────────────────────────────────────────────
print("\n[11] light_cosinor.fit_cosinor_daily_activity (light)")
cosinor_light = None
try:
    from tools.light_cosinor import fit_cosinor_daily_activity as fit_cosinor_light
    cosinor_light = fit_cosinor_light(df.copy(), datetime_col='DATE/TIME', value_col='MELANOPIC EDI')
    check("Returns DataFrame", isinstance(cosinor_light, pd.DataFrame))
    if not cosinor_light.empty:
        check("Light acrophase_hours in [0,24)", cosinor_light['acrophase_hours'].dropna().between(0, 24, inclusive='left').all(),
              f"range: {cosinor_light['acrophase_hours'].min():.1f}–{cosinor_light['acrophase_hours'].max():.1f}")
        check("Light amplitude >= 0", (cosinor_light['amplitude'].dropna() >= 0).all())
        mean_light_acroph = cosinor_light['acrophase_hours'].mean()
        check("Light acrophase near midday (9-17h)", 9 <= mean_light_acroph <= 17,
              f"mean acrophase = {mean_light_acroph:.1f}h")
except Exception as e:
    check("No exception", False, traceback.format_exc())

# ─────────────────────────────────────────────────────────────
# 12. Light CPD
# ─────────────────────────────────────────────────────────────
print("\n[12] light_CPD.calculate_cpd_light")
try:
    from tools.light_CPD import calculate_cpd_light
    if cosinor_light is not None and not cosinor_light.empty:
        cpd_light = calculate_cpd_light(cosinor_light, ms_col='acrophase_hours', date_col='date')
        check("Returns DataFrame", isinstance(cpd_light, pd.DataFrame))
        check("cpd_hours non-negative", (cpd_light['cpd_hours'].dropna() >= 0).all())
        check("First row cpd_hours is NaN", pd.isna(cpd_light['cpd_hours'].iloc[0]))
    else:
        warn("light_CPD", "Skipped — light cosinor empty")
except Exception as e:
    check("No exception", False, traceback.format_exc())

# ─────────────────────────────────────────────────────────────
# 13. Plotters (no crash, return Figure)
# ─────────────────────────────────────────────────────────────
print("\n[13] activity_plotter / light_plotter")
try:
    import matplotlib
    matplotlib.use('Agg')
    from tools.activity_plotter import activity_plotter
    from tools.light_plotter import light_plotter
    df_plot = df.copy()
    fig_act = activity_plotter(df_plot)
    import matplotlib.pyplot as plt
    check("activity_plotter returns Figure", hasattr(fig_act, 'savefig'))
    plt.close('all')
    df_plot2 = df.copy()
    fig_light = light_plotter(df_plot2)
    check("light_plotter returns Figure", hasattr(fig_light, 'savefig'))
    plt.close('all')
except Exception as e:
    check("No exception", False, traceback.format_exc())

# ─────────────────────────────────────────────────────────────
# 14. Database operations
# ─────────────────────────────────────────────────────────────
print("\n[14] database.ActigraphDB")
import os, tempfile
try:
    from tools.database import ActigraphDB
    tmp_db = tempfile.mktemp(suffix='.db')
    db = ActigraphDB(db_path=tmp_db)
    ok = db.save_analysis_record('test001', 'Test', '2024-01-11', 'file.txt', ['2024-01-11'])
    check("save_analysis_record returns True", ok)
    check("duplicate ID returns False", not db.save_analysis_record('test001', 'Dup', '2024-01-11'))
    check("record_exists True", db.record_exists('test001'))
    check("record_exists False for unknown", not db.record_exists('doesnotexist'))
    rec = db.get_record_by_id('test001')
    check("get_record_by_id returns dict", isinstance(rec, dict))
    # Save and retrieve DataFrame  
    ok2 = db.save_sleep_analysis('test001', 'sleep_periods', pd.DataFrame([{'a':1,'b':2}]))
    check("save_sleep_analysis returns True", ok2)
    df_back = db.get_analysis_results_as_dataframe('test001', 'sleep_analysis', 'sleep_periods')
    check("Roundtrip DataFrame not None", df_back is not None and not df_back.empty)
    # Delete
    ok3 = db.delete_record('test001')
    check("delete_record returns True", ok3)
    check("record gone after delete", not db.record_exists('test001'))
    os.unlink(tmp_db)
except Exception as e:
    check("No exception", False, traceback.format_exc())

# ─────────────────────────────────────────────────────────────
# 15. Edge cases — empty/short input
# ─────────────────────────────────────────────────────────────
print("\n[15] Edge cases — minimal / empty input")
try:
    from tools.activity_IS_IV import compute_rolling_2day_is_iv_activity
    from tools.activity_L5_M10_RA import compute_daily_L5_M10_RA_activity
    from tools.sleep_SRI import calculate_sri_from_pimn

    empty_df = df.iloc[:0].copy()
    isiv_empty = compute_rolling_2day_is_iv_activity(empty_df)
    check("IS/IV empty input → empty DataFrame", isiv_empty.empty)

    l5m10_empty = compute_daily_L5_M10_RA_activity(empty_df)
    check("L5/M10 empty input → empty DataFrame", l5m10_empty.empty)

    sri_empty = calculate_sri_from_pimn(empty_df.iloc[:5].copy(), 'DATE/TIME', 'PIMn', window_days=2)
    check("SRI 1-day input → empty DataFrame (< window)", sri_empty.empty)

    # Single-day data: with anchor_hour=12 a calendar day spans parts of 2 anchored days
    # so IS/IV may return 1 row — this is expected scientific behavior
    one_day = df[df['DATE'] == df['DATE'].unique()[0]].copy()
    isiv_one = compute_rolling_2day_is_iv_activity(one_day)
    check("IS/IV 1-calendar-day → at most 1 pair of anchored days", len(isiv_one) <= 1,
          f"got {len(isiv_one)} rows (expected 0 or 1)")
except Exception as e:
    check("No exception in edge cases", False, traceback.format_exc())

# ─────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)
warned = sum(1 for r in results if r[0] == WARN)
print(f"SUMMARY: {passed} passed  |  {failed} failed  |  {warned} warnings")
print("=" * 60)
if failed > 0:
    print("\nFAILED TESTS:")
    for r in results:
        if r[0] == FAIL:
            print(f"  ❌ {r[1]}: {r[2]}")
if warned > 0:
    print("\nWARNINGS:")
    for r in results:
        if r[0] == WARN:
            print(f"  ⚠️  {r[1]}: {r[2]}")
sys.exit(0 if failed == 0 else 1)
