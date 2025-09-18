
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
