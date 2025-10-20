
# List of tools

  **plotter_activity:**
  
  **plotter_light:**
  
  **analysis_sleep:**
  
  **upload_file**


## Adding possiblity to comparing between two or more time points

## Adding possibility to select free days vs. work days.

## Data import $ cleaning

## Metrics calculation

Totally—here’s a clean, **rewritten list** organized by (1) what each metric measures, (2) which signal it uses (**Activity** = PIM/TAT/ZCM; **Light** = Melanopic EDI), (3) whether it’s **Direct** (from raw) or **Derived**, and (4) **how to extract**. I’ve also added a dedicated **phase agreement/disagreement** metric between light and activity.

---

# A) Direct, per-day metrics from each signal

### 1) **Cosinor (24 h)**

* **What:** Mesor, Amplitude, Acrophase (timing of the peak).
* **Signal:** Activity ✅ | Light ✅
* **Type:** Direct
* **Extract:**

  1. Preprocess (handle non-wear / sensor-off; for light you may use `log10(EDI + c)`).
  2. Fit $y(t)=M + A\cos(\omega t + \phi)$ with $\omega=2\pi/24$.
  3. Report **M**, **A**, **acrophase** $\phi$ → convert to clock hours $[0,24)$.

---

### 2) **L5 (Least Active 5h) / L5 of Light**

* **What:** Lowest-mean 5 h window; onset time as a phase marker.
* **Signal:** Activity ✅ | Light ✅ (lowest-light 5 h)
* **Type:** Direct
* **Extract:** Slide a 5 h window over the 24 h profile; pick window with minimum mean. Save **onset time** (phase) and **mean** (level).

---

### 3) **M10 (Most Active 10h) / M10 of Light**

* **What:** Highest-mean 10 h window; midpoint as a phase marker.
* **Signal:** Activity ✅ | Light ✅ (brightest-light 10 h)
* **Type:** Direct
* **Extract:** Slide a 10 h window; pick maximum mean. Save **midpoint time** (phase) and **mean**.

---

### 4) **RA – Relative Amplitude**

* **What:** Rhythm strength from extremes.
* **Signal:** Activity ✅ | Light ✅
* **Type:** Derived from L5/M10 (same day)
* **Formula:** $\displaystyle RA = \frac{M10 - L5}{M10 + L5}$ using the **means** of those windows.

---

### 5) **IV – Intradaily Variability**

* **What:** Fragmentation within a day (frequent transitions).
* **Signal:** Activity ✅ | Light ✅
* **Type:** Direct
* **Extract (classic):** $\text{IV}=\frac{\sum_{i}(x_{i+1}-x_i)^2/(N-1)}{\sum_i (x_i-\bar x)^2/(N-1)}$ using evenly binned data (e.g., 60-min).

---

### 6) **IS – Interdaily Stability**

* **What:** Alignment with 24 h zeitgeber.
* **Signal:** Activity ✅ | Light ✅
* **Type:** Direct (needs several days)
* **Extract (classic):** Ratio of variance explained by the 24 h mean profile to total variance (often implemented via correlogram or standard IS formula on hourly means across days).

---

### 7) **IA – Intradaily Amplitude**

* **What:** Within-day peak–trough strength.
* **Signal:** Activity ✅ | Light ✅
* **Type:** Direct
* **Extract:** Daily (or multi-day) peak vs trough contrast (e.g., $\max - \min$, or $\frac{\max-\min}{\max+\min}$) on a smoothed/averaged 24 h profile.

---

### 8) **Sleep Onset / Sleep Offset**

* **What:** Timing of sleep period.
* **Signal:** Activity ✅ (from sleep–wake scoring)
* **Type:** Direct
* **Extract:** Apply a validated algorithm (threshold/ML); return onset/offset per main sleep episode.

---

# B) Derived, across-days regularity & misalignment

### 9) **SRI – Sleep Regularity Index**

* **What:** Day-to-day consistency of sleep/wake timing.
* **Signal:** Activity ✅
* **Type:** Derived (needs scored sleep–wake across ≥7 days)
* **Extract:** For each timepoint, compare state (sleep/wake) on day $d$ vs $d\!+\!1$; SRI = % of timepoints matching (scaled 0–100).

---

### 10) **CPD – Composite Phase Deviation**

* **What:** Daily misalignment from personal reference **phase**.
* **Signal:** Activity ✅ | Light ✅
* **Type:** Derived (uses any **phase marker**)
* **Phase markers (examples):**

  * **Activity:** mid-sleep; L5 **onset**; M10 **midpoint**; **activity acrophase**.
  * **Light (melanopic EDI):** **light acrophase**; **M10(midpoint) of light**.
* **Extract:**

  1. Compute daily phase $\phi_d$ (hours).
  2. Reference $\phi_{\text{ref}}$: circular mean over baseline/stable days (optionally split work/free).
  3. **Signed:** $\Delta_d=\text{wrap}_{(-12,12]}(\phi_d-\phi_{\text{ref}})$.
  4. **CPD (unsigned):** $|\Delta_d|$ in hours.

---

### 11) **Social Jetlag**

* **What:** Misalignment due to social schedule.
* **Signal:** Activity ✅
* **Type:** Derived
* **Extract:** Mid-sleep on free days minus mid-sleep on workdays (use diaries or labels).

---

# C) Cross-signal coupling (agreement / disagreement)

### 12) **Phase Angle (Light–Activity Agreement)**

* **What:** Alignment (or mismatch) between **light phase** and **activity/sleep phase**.
* **Signal:** Activity ✅ & Light ✅
* **Type:** Derived (cross-signal)
* **Choose phase markers (consistent definition):**

  * e.g., **Light acrophase** (melanopic EDI, cosinor) vs **Activity acrophase** (cosinor), **or**
  * **Light M10 midpoint** vs **Activity M10 midpoint**.
* **Extract:**

  1. Get daily $\phi^{\text{light}}_d$ and $\phi^{\text{act}}_d$.
  2. **Signed angle:** $\Delta^{\text{LA}}_d=\text{wrap}_{(-12,12]}(\phi^{\text{light}}_d-\phi^{\text{act}}_d)$ (hours).

     * Positive ⇒ light **earlier** than activity (phase **advance** cue).
     * Negative ⇒ light **later** than activity (phase **delay** cue).
  3. **Agreement (absolute):** $|\Delta^{\text{LA}}_d|$ — smaller is better alignment.
  4. Optionally summarize by median over 7 days; QC-weight by cosinor amplitude or data coverage.

**Extras (optional):**

* **Circular correlation** between the two phase series across days.
* **Stability of phase angle:** SD or MAD of $\Delta^{\text{LA}}_d$ across days.

---

# D) External or questionnaire-based (not from sensors alone)

### 13) **DLMO – Dim Light Melatonin Onset**

* **What:** Biological circadian phase.
* **Signal:** — (lab sampling)
* **Use:** Compare to sleep or light to compute **phase angle of entrainment** (e.g., DLMO → sleep onset difference).

### 14) **MSF – Mid-Sleep on Free Days**

* **What:** Chronotype proxy.
* **Signal:** — (MCTQ / diary; can be estimated via actigraphy + labels)

---

## Quick “how-to” map (implementation hints)

* **Day boundary:** Use local time (Europe/Berlin); many teams shift day 04:00–04:00 to avoid splitting nocturnal sleep.
* **Preprocessing:** Mark non-wear / sensor-off; for light, cap extremes and consider `log10(EDI + c)`.
* **Circular math:** Always compute means/angles on the unit circle; wrap differences to $(-12,12]$ hours.
* **Windows (L5/M10):** Use rolling means on resampled bins (e.g., 1–5 min), then refine with minute-level search.
* **Quality control:** Flag days with <16 h valid data, poor cosinor fit (e.g., tiny A, low $R^2$), or unstable windows; exclude or down-weight.
* **Reporting:** Provide daily values plus 7-day rolling medians for CPD and Light–Activity Phase Angle.

If you want, I can generate **ready-to-run code** (R or Python) that:

* computes **cosinor** for activity & melanopic EDI,
* extracts **L5/M10**, **RA**, **IV**, **IS**, **IA**,
* calculates **CPD\_activity**, **CPD\_light**, and the **Light–Activity phase angle** (signed and absolute),
* and outputs tidy tables per day.


## Plotting

#### Plotting single items with boundaries for simplification form excellent to very bad

#### Add radar chart to show all results in one figure

---

# Variable Dictionary for Database Storage

This dictionary maps all variables computed in the application to their source functions and metrics for future database storage implementation.

## Core Data Variables
| Variable Name | Source Function | Data Type | Description | Signal Type |
|---------------|----------------|-----------|-------------|-------------|
| `df` | File uploader | DataFrame | Raw uploaded data file | Input |
| `data` | `upload_file()` | DataFrame | Processed uploaded data | Input |
| `available_dates` | `get_available_dates()` | List[str] | List of available dates in data | Metadata |
| `selected_dates` | User selection | List[str] | User-selected dates for analysis | Metadata |
| `filtered_data` | `filter_data_by_dates()` | DataFrame | Data filtered by selected dates | Input |

## Visualization Variables
| Variable Name | Source Function | Data Type | Description | Signal Type |
|---------------|----------------|-----------|-------------|-------------|
| `fig_activity` | `activity_plotter()` | matplotlib.Figure | Activity plot visualization | Activity |
| `fig_light` | `light_plotter()` | matplotlib.Figure | Light exposure plot visualization | Light |

## Sleep and Light Exposure Metrics
| Variable Name | Source Function | Data Type | Description | Metric Type |
|---------------|----------------|-----------|-------------|-------------|
| `sleep_light_exposure_results` | `analyze_sleep_light_exposure()` | Dict | Sleep-light exposure analysis results | Sleep/Light |
| `sleep_light_exposure_results['metric1']` | `analyze_sleep_light_exposure()` | DataFrame/str | Minutes of light exposure (>1 lux) during sleep | Sleep/Light |
| `sleep_light_exposure_results['metric2']` | `analyze_sleep_light_exposure()` | DataFrame/str | Minutes of bright light (>10 lux) 3h before sleep | Sleep/Light |
| `sleep_light_exposure_results['metric3']` | `analyze_sleep_light_exposure()` | DataFrame/str | Minutes of non-bright light (<250 lux) 3h after wake | Sleep/Light |

## Sleep Analysis Variables
| Variable Name | Source Function | Data Type | Description | Metric Type |
|---------------|----------------|-----------|-------------|-------------|
| `sleep_periods_results` | `analyze_sleep_periods()` | DataFrame/str | Sleep onset, offset, and period analysis | Sleep |
| `mid_sleep_data` | `build_centered_midpoint_hours()` | DataFrame | Processed mid-sleep data with centered hours | Sleep |
| `cpd_mid_sleep_results` | `calculate_single_person_cpd()` | DataFrame | Circadian Phase Dispersion of mid-sleep | CPD |
| `sri_sleep_results` | `calculate_sri_from_pimn()` | DataFrame | Sleep Regularity Index analysis | SRI |

## Activity Analysis Variables
| Variable Name | Source Function | Data Type | Description | Metric Type |
|---------------|----------------|-----------|-------------|-------------|
| `activity_is_iv_results` | `compute_rolling_2day_is_iv_activity()` | DataFrame | Interdaily Stability (IS) and Intradaily Variability (IV) | IS/IV |
| `activity_l5_m10_ra_results` | `compute_daily_L5_M10_RA_activity()` | DataFrame | L5, M10, and Relative Amplitude analysis | L5/M10/RA |
| `activity_cosinor_results` | `fit_cosinor_daily_activity()` | DataFrame | Daily cosinor fit analysis for activity | Cosinor |
| `cpd_activity_acrophase_results` | `calculate_cpd_activity()` | DataFrame | Composite Phase Deviation of activity acrophase | CPD |

## Light Analysis Variables
| Variable Name | Source Function | Data Type | Description | Metric Type |
|---------------|----------------|-----------|-------------|-------------|
| `light_is_iv_results` | `compute_rolling_2day_is_iv_light()` | DataFrame | Interdaily Stability (IS) and Intradaily Variability (IV) for light | IS/IV |
| `light_l5_m10_ra_results` | `compute_daily_L5_M10_RA_light()` | DataFrame | L5, M10, and Relative Amplitude analysis for light | L5/M10/RA |
| `light_cosinor_results` | `fit_cosinor_daily_light()` | DataFrame | Daily cosinor fit analysis for light exposure | Cosinor |
| `cpd_light_acrophase_results` | `calculate_cpd_light()` | DataFrame | Composite Phase Deviation of light acrophase | CPD |

## Database Storage Schema Suggestion

### Primary Tables Structure:
```sql
-- Main analysis session table
CREATE TABLE analysis_sessions (
    session_id SERIAL PRIMARY KEY,
    upload_filename VARCHAR(255),
    selected_dates TEXT[], -- Array of selected dates
    analysis_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sleep and light exposure metrics
CREATE TABLE sleep_light_metrics (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES analysis_sessions(session_id),
    date DATE,
    light_during_sleep_minutes FLOAT, -- metric1
    bright_light_before_sleep_minutes FLOAT, -- metric2
    dim_light_after_wake_minutes FLOAT -- metric3
);

-- Sleep periods and timing
CREATE TABLE sleep_periods (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES analysis_sessions(session_id),
    date DATE,
    sleep_onset TIME,
    sleep_offset TIME,
    mid_sleep_time TIME,
    sleep_duration_hours FLOAT
);

-- CPD mid-sleep results
CREATE TABLE cpd_mid_sleep (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES analysis_sessions(session_id),
    date DATE,
    cpd_hours FLOAT,
    mean_midpoint_hours FLOAT,
    median_midpoint_hours FLOAT
);

-- SRI results
CREATE TABLE sri_results (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES analysis_sessions(session_id),
    date DATE,
    sri_value FLOAT,
    window_days INTEGER
);

-- Activity IS/IV metrics
CREATE TABLE activity_is_iv (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES analysis_sessions(session_id),
    date DATE,
    interdaily_stability FLOAT, -- IS
    intradaily_variability FLOAT -- IV
);

-- Activity L5/M10/RA metrics
CREATE TABLE activity_l5_m10_ra (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES analysis_sessions(session_id),
    date DATE,
    l5_onset_time TIME,
    l5_value FLOAT,
    m10_midpoint_time TIME,
    m10_value FLOAT,
    relative_amplitude FLOAT -- RA
);

-- Activity cosinor results
CREATE TABLE activity_cosinor (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES analysis_sessions(session_id),
    date DATE,
    mesor FLOAT,
    amplitude FLOAT,
    acrophase_hours FLOAT,
    r_squared FLOAT
);

-- CPD activity acrophase
CREATE TABLE cpd_activity_acrophase (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES analysis_sessions(session_id),
    date DATE,
    cpd_hours FLOAT,
    deviation_from_mean_hours FLOAT,
    deviation_from_prev_hours FLOAT
);

-- Light IS/IV metrics
CREATE TABLE light_is_iv (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES analysis_sessions(session_id),
    date DATE,
    interdaily_stability FLOAT, -- IS
    intradaily_variability FLOAT -- IV
);

-- Light L5/M10/RA metrics
CREATE TABLE light_l5_m10_ra (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES analysis_sessions(session_id),
    date DATE,
    l5_onset_time TIME,
    l5_value FLOAT,
    m10_midpoint_time TIME,
    m10_value FLOAT,
    relative_amplitude FLOAT -- RA
);

-- Light cosinor results
CREATE TABLE light_cosinor (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES analysis_sessions(session_id),
    date DATE,
    mesor FLOAT,
    amplitude FLOAT,
    acrophase_hours FLOAT,
    r_squared FLOAT
);

-- CPD light acrophase
CREATE TABLE cpd_light_acrophase (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES analysis_sessions(session_id),
    date DATE,
    cpd_hours FLOAT,
    deviation_from_mean_hours FLOAT,
    deviation_from_prev_hours FLOAT
);
```

### Variable-to-Database Mapping:
- `sleep_light_exposure_results` → `sleep_light_metrics` table
- `sleep_periods_results` → `sleep_periods` table  
- `cpd_mid_sleep_results` → `cpd_mid_sleep` table
- `sri_sleep_results` → `sri_results` table
- `activity_is_iv_results` → `activity_is_iv` table
- `activity_l5_m10_ra_results` → `activity_l5_m10_ra` table
- `activity_cosinor_results` → `activity_cosinor` table
- `cpd_activity_acrophase_results` → `cpd_activity_acrophase` table
- `light_is_iv_results` → `light_is_iv` table
- `light_l5_m10_ra_results` → `light_l5_m10_ra` table
- `light_cosinor_results` → `light_cosinor` table
- `cpd_light_acrophase_results` → `cpd_light_acrophase` table
