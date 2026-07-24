from __future__ import annotations

import numpy as np
import pandas as pd


def phasor(Timestamp, MelanopicEDI, PIMna, TEMPERATURE):
    """
    Calculate daily 24-hour phasor metrics for personal light exposure,
    activity, and skin temperature.

    Parameters
    ----------
    Timestamp : array-like
        Date and time of each measurement. Timestamps should represent the
        participant's local clock time.
    MelanopicEDI : array-like
        Melanopic equivalent daylight illuminance.
    PIMna : array-like
        Activity measurement, such as normalized PIM activity.
    TEMPERATURE : array-like
        Skin-temperature measurement.

    Returns
    -------
    result : dict
        result["daily"]:
            DataFrame with one row per day containing phase, amplitude,
            rhythm strength, coverage, and pairwise phase angles.

        result["summary"]:
            One-row DataFrame summarizing the complete supplied interval.
            This can be used to compare Week 1 and Week 2 elsewhere.

    Notes
    -----
    1. Light and activity are log-transformed using log1p because these
       variables are usually strongly right-skewed.

    2. Temperature is analysed without transformation.

    3. Phase represents the acrophase, meaning the estimated clock time
       of the maximum of the fitted 24-hour harmonic.

    4. Pairwise phase angles are wrapped to the interval [-12, +12) hours.

    5. Positive activity-minus-light means the activity acrophase occurs
       later than the light acrophase.

    6. A small phase difference is not automatically "better." For example,
       distal skin temperature and activity may naturally be approximately
       antiphase. Stability and change from the expected phase relationship
       are often more meaningful than closeness to zero.
    """

    # Require at least 70% of a nominal 1-minute day.
    expected_epochs_per_day = 1440
    minimum_valid_epochs = int(0.70 * expected_epochs_per_day)

    df = pd.DataFrame(
        {
            "Timestamp": pd.to_datetime(Timestamp, errors="coerce"),
            "MelanopicEDI": pd.to_numeric(MelanopicEDI, errors="coerce"),
            "PIMna": pd.to_numeric(PIMna, errors="coerce"),
            "TEMPERATURE": pd.to_numeric(TEMPERATURE, errors="coerce"),
        }
    )

    # Remove rows without a valid timestamp.
    df = df.dropna(subset=["Timestamp"]).copy()

    if df.empty:
        raise ValueError("No valid timestamps were supplied.")

    # Combine duplicate one-minute timestamps using the mean.
    df = (
        df.groupby("Timestamp", as_index=False)
        .agg(
            MelanopicEDI=("MelanopicEDI", "mean"),
            PIMna=("PIMna", "mean"),
            TEMPERATURE=("TEMPERATURE", "mean"),
        )
        .sort_values("Timestamp")
    )

    # Calendar day based on local clock time.
    df["date"] = df["Timestamp"].dt.date

    # Decimal clock time: 13:30 becomes 13.5 hours.
    df["clock_hour"] = (
        df["Timestamp"].dt.hour
        + df["Timestamp"].dt.minute / 60
        + df["Timestamp"].dt.second / 3600
    )

    def wrap_phase_difference(hours):
        """
        Wrap a phase difference to [-12, +12) hours.

        Examples
        --------
        23 hours becomes -1 hour.
        13 hours becomes -11 hours.
        """
        if pd.isna(hours):
            return np.nan

        return ((hours + 12) % 24) - 12

    def fit_daily_phasor(clock_hour, signal, transform=None):
        """
        Fit a fixed-period 24-hour cosinor:

        y(t) = mesor
             + beta_cos * cos(2*pi*t/24)
             + beta_sin * sin(2*pi*t/24)

        This can also be written as:

        y(t) = mesor + amplitude * cos(2*pi*(t - phase)/24)

        Therefore:

        amplitude = sqrt(beta_cos^2 + beta_sin^2)

        phase = atan2(beta_sin, beta_cos) * 24 / (2*pi)
        """

        x = np.asarray(clock_hour, dtype=float)
        y = np.asarray(signal, dtype=float)

        valid = np.isfinite(x) & np.isfinite(y)
        x = x[valid]
        y = y[valid]

        n_valid = len(y)

        if n_valid < minimum_valid_epochs:
            return {
                "n": n_valid,
                "coverage": n_valid / expected_epochs_per_day,
                "mesor": np.nan,
                "beta_cos": np.nan,
                "beta_sin": np.nan,
                "amplitude": np.nan,
                "phase_h": np.nan,
                "r2": np.nan,
            }

        if transform == "log1p":
            # Negative light or activity values are not physically meaningful.
            y = np.log1p(np.clip(y, a_min=0, a_max=None))

        omega_t = 2 * np.pi * x / 24

        design_matrix = np.column_stack(
            [
                np.ones_like(x),
                np.cos(omega_t),
                np.sin(omega_t),
            ]
        )

        coefficients, _, _, _ = np.linalg.lstsq(
            design_matrix,
            y,
            rcond=None,
        )

        mesor, beta_cos, beta_sin = coefficients

        amplitude = np.hypot(beta_cos, beta_sin)

        # Clock time at which the fitted harmonic reaches its maximum.
        phase_radians = np.arctan2(beta_sin, beta_cos)
        phase_h = (phase_radians % (2 * np.pi)) * 24 / (2 * np.pi)

        predicted = design_matrix @ coefficients

        residual_sum_squares = np.sum((y - predicted) ** 2)
        total_sum_squares = np.sum((y - np.mean(y)) ** 2)

        if total_sum_squares > 0:
            r2 = 1 - residual_sum_squares / total_sum_squares
        else:
            r2 = np.nan

        return {
            "n": n_valid,
            "coverage": n_valid / expected_epochs_per_day,
            "mesor": mesor,
            "beta_cos": beta_cos,
            "beta_sin": beta_sin,
            "amplitude": amplitude,
            "phase_h": phase_h,
            "r2": r2,
        }

    daily_rows = []

    for date, day in df.groupby("date", sort=True):

        light = fit_daily_phasor(
            clock_hour=day["clock_hour"],
            signal=day["MelanopicEDI"],
            transform="log1p",
        )

        activity = fit_daily_phasor(
            clock_hour=day["clock_hour"],
            signal=day["PIMna"],
            transform="log1p",
        )

        temperature = fit_daily_phasor(
            clock_hour=day["clock_hour"],
            signal=day["TEMPERATURE"],
            transform=None,
        )

        activity_minus_light = wrap_phase_difference(
            activity["phase_h"] - light["phase_h"]
        )

        temperature_minus_light = wrap_phase_difference(
            temperature["phase_h"] - light["phase_h"]
        )

        activity_minus_temperature = wrap_phase_difference(
            activity["phase_h"] - temperature["phase_h"]
        )

        daily_rows.append(
            {
                "date": pd.Timestamp(date),

                # Light phasor
                "light_n": light["n"],
                "light_coverage": light["coverage"],
                "light_mesor_log": light["mesor"],
                "light_beta_cos": light["beta_cos"],
                "light_beta_sin": light["beta_sin"],
                "light_amplitude_log": light["amplitude"],
                "light_phase_h": light["phase_h"],
                "light_r2": light["r2"],

                # Activity phasor
                "activity_n": activity["n"],
                "activity_coverage": activity["coverage"],
                "activity_mesor_log": activity["mesor"],
                "activity_beta_cos": activity["beta_cos"],
                "activity_beta_sin": activity["beta_sin"],
                "activity_amplitude_log": activity["amplitude"],
                "activity_phase_h": activity["phase_h"],
                "activity_r2": activity["r2"],

                # Temperature phasor
                "temperature_n": temperature["n"],
                "temperature_coverage": temperature["coverage"],
                "temperature_mesor": temperature["mesor"],
                "temperature_beta_cos": temperature["beta_cos"],
                "temperature_beta_sin": temperature["beta_sin"],
                "temperature_amplitude": temperature["amplitude"],
                "temperature_phase_h": temperature["phase_h"],
                "temperature_r2": temperature["r2"],

                # Daily phase-angle relationships
                "activity_minus_light_h": activity_minus_light,
                "temperature_minus_light_h": temperature_minus_light,
                "activity_minus_temperature_h": activity_minus_temperature,
            }
        )

    daily = pd.DataFrame(daily_rows)

    def circular_summary(values, signed=False):
        """
        Calculate circular mean phase and phase stability.

        Resultant length ranges from 0 to 1:
            1 = exactly the same phase every day
            0 = phases distributed across the complete 24-hour cycle

        Circular SD is returned in hours.
        """

        values = pd.to_numeric(
            pd.Series(values),
            errors="coerce",
        ).dropna().to_numpy(dtype=float)

        if len(values) == 0:
            return {
                "mean": np.nan,
                "resultant_length": np.nan,
                "circular_sd_h": np.nan,
                "n": 0,
            }

        angles = values * 2 * np.pi / 24

        mean_cos = np.mean(np.cos(angles))
        mean_sin = np.mean(np.sin(angles))

        resultant_length = np.hypot(mean_cos, mean_sin)

        mean_angle = np.arctan2(mean_sin, mean_cos) % (2 * np.pi)
        mean_hour = mean_angle * 24 / (2 * np.pi)

        if signed:
            mean_hour = wrap_phase_difference(mean_hour)

        # Protect against log(0) and small floating-point values above 1.
        r_for_sd = np.clip(resultant_length, 1e-12, 1.0)

        circular_sd_h = (
            np.sqrt(-2 * np.log(r_for_sd))
            * 24
            / (2 * np.pi)
        )

        return {
            "mean": mean_hour,
            "resultant_length": resultant_length,
            "circular_sd_h": circular_sd_h,
            "n": len(values),
        }

    light_phase = circular_summary(daily["light_phase_h"])
    activity_phase = circular_summary(daily["activity_phase_h"])
    temperature_phase = circular_summary(daily["temperature_phase_h"])

    activity_light = circular_summary(
        daily["activity_minus_light_h"],
        signed=True,
    )

    temperature_light = circular_summary(
        daily["temperature_minus_light_h"],
        signed=True,
    )

    activity_temperature = circular_summary(
        daily["activity_minus_temperature_h"],
        signed=True,
    )

    summary = pd.DataFrame(
        [
            {
                "start_date": daily["date"].min(),
                "end_date": daily["date"].max(),
                "n_calendar_days": len(daily),

                # Average phase and phase stability
                "light_mean_phase_h": light_phase["mean"],
                "light_phase_resultant_length": light_phase[
                    "resultant_length"
                ],
                "light_phase_circular_sd_h": light_phase["circular_sd_h"],
                "light_valid_days": light_phase["n"],

                "activity_mean_phase_h": activity_phase["mean"],
                "activity_phase_resultant_length": activity_phase[
                    "resultant_length"
                ],
                "activity_phase_circular_sd_h": activity_phase[
                    "circular_sd_h"
                ],
                "activity_valid_days": activity_phase["n"],

                "temperature_mean_phase_h": temperature_phase["mean"],
                "temperature_phase_resultant_length": temperature_phase[
                    "resultant_length"
                ],
                "temperature_phase_circular_sd_h": temperature_phase[
                    "circular_sd_h"
                ],
                "temperature_valid_days": temperature_phase["n"],

                # Mean rhythm amplitude and goodness of fit
                "light_mean_amplitude_log": daily[
                    "light_amplitude_log"
                ].mean(),
                "light_mean_r2": daily["light_r2"].mean(),

                "activity_mean_amplitude_log": daily[
                    "activity_amplitude_log"
                ].mean(),
                "activity_mean_r2": daily["activity_r2"].mean(),

                "temperature_mean_amplitude": daily[
                    "temperature_amplitude"
                ].mean(),
                "temperature_mean_r2": daily["temperature_r2"].mean(),

                # Average phase-angle relationships
                "activity_minus_light_mean_h": activity_light["mean"],
                "activity_minus_light_resultant_length": activity_light[
                    "resultant_length"
                ],
                "activity_minus_light_circular_sd_h": activity_light[
                    "circular_sd_h"
                ],

                "temperature_minus_light_mean_h": temperature_light["mean"],
                "temperature_minus_light_resultant_length": temperature_light[
                    "resultant_length"
                ],
                "temperature_minus_light_circular_sd_h": temperature_light[
                    "circular_sd_h"
                ],

                "activity_minus_temperature_mean_h":
                    activity_temperature["mean"],
                "activity_minus_temperature_resultant_length":
                    activity_temperature["resultant_length"],
                "activity_minus_temperature_circular_sd_h":
                    activity_temperature["circular_sd_h"],
            }
        ]
    )

    return {
        "daily": daily,
        "summary": summary,
    }