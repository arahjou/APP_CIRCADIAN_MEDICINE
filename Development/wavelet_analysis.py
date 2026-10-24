"""
Foundation for continuous wavelet analysis of actigraphy, light and temperature.

Unlike the daily cosinor (one fixed 24 h period per day) the continuous wavelet
transform (CWT) resolves rhythm strength and period *over time*, so it can show
when a circadian rhythm weakens, drifts away from 24 h, or is replaced by
ultradian (1-8 h) structure.

Method: Morlet CWT computed in the frequency domain, following
Torrence & Compo (1998), "A Practical Guide to Wavelet Analysis",
Bull. Amer. Meteor. Soc. 79:61-78. No PyWavelets dependency (scipy.signal.cwt
was removed in SciPy 1.15), only numpy/pandas.

Pipeline
--------
1. prepare_signal      minute data -> evenly spaced series (default 10 min),
                       optional log1p, short-gap interpolation, z-scoring.
2. morlet_cwt          complex coefficients W(period, time), power |W|^2,
                       cone of influence (COI).
3. red_noise_significance
                       AR(1) background spectrum and 95% significance level.
4. band_power          scale-averaged power in circadian / ultradian bands.
5. circadian_ridge     dominant period and instantaneous phase in the
                       circadian band at each time point.
6. daily_wavelet_summary
                       one row per day, the shape the app's other metrics use.

Status: development only, not wired into the app or the stored reports. Gaps
longer than `max_gap_minutes` are left as NaN, and the corresponding
coefficients are masked; edge effects outside the COI must not be interpreted.

Usage
-----
    python Development/wavelet_analysis.py                       # synthetic demo
    python Development/wavelet_analysis.py data/data_set_1.csv PIMn

Next steps before integrating into the app
------------------------------------------
- Validate against PyWavelets / pyActigraphy on shared recordings.
- Decide on minimum recording length (>= 3 x the longest period of interest
  inside the COI; 7+ days for stable 20-28 h estimates).
- Wavelet coherence / phase difference between activity, light and
  temperature (cross-wavelet, Grinsted et al. 2004).
- Add a `wavelet` metric to services/recording_service.py with its own
  eligibility rule, then a scalogram panel on the dashboard.
"""

import numpy as np
import pandas as pd

# Morlet with omega0 = 6: Fourier period = 1.033 * scale (Torrence & Compo, Table 1).
OMEGA0 = 6.0
FOURIER_FACTOR = 4 * np.pi / (OMEGA0 + np.sqrt(2 + OMEGA0 ** 2))
COI_FACTOR = FOURIER_FACTOR / np.sqrt(2)

CIRCADIAN_BAND = (20.0, 28.0)   # hours
ULTRADIAN_BAND = (1.0, 8.0)     # hours


def prepare_signal(
    df: pd.DataFrame,
    value_col: str,
    time_col: str = "DATE/TIME",
    resample_minutes: int = 10,
    log_transform: bool = False,
    max_gap_minutes: int = 60,
    standardize: bool = True,
) -> pd.Series:
    """Return an evenly sampled series ready for the CWT.

    Light and activity are strongly right-skewed; `log_transform=True`
    applies log1p (as in Development/harmonic_phase.py). Gaps up to
    `max_gap_minutes` are linearly interpolated, longer gaps stay NaN.
    """
    data = df[[time_col, value_col]].copy()
    data[time_col] = pd.to_datetime(data[time_col])
    series = pd.to_numeric(data.set_index(time_col)[value_col], errors="coerce").sort_index()
    series = series.resample(f"{resample_minutes}min").mean()
    # Label each bin at its centre so phase estimates are not shifted by half a bin.
    series.index = series.index + pd.Timedelta(minutes=resample_minutes / 2)
    if log_transform:
        series = np.log1p(series.clip(lower=0))
    limit = max(int(max_gap_minutes // resample_minutes), 0)
    series = series.interpolate(limit=limit, limit_area="inside") if limit else series
    if standardize:
        sd = series.std()
        series = (series - series.mean()) / sd if sd and np.isfinite(sd) else series - series.mean()
    return series


def period_grid(min_hours: float = 1.0, max_hours: float = 48.0, voices_per_octave: int = 12) -> np.ndarray:
    """Log-spaced periods (hours); 12 voices per octave resolves ~6% period changes."""
    n_octaves = np.log2(max_hours / min_hours)
    return min_hours * 2 ** (np.arange(int(n_octaves * voices_per_octave) + 1) / voices_per_octave)


def morlet_cwt(series: pd.Series, periods_hours: np.ndarray | None = None) -> dict:
    """Continuous Morlet wavelet transform of an evenly sampled series.

    Returns a dict with:
        coefficients  complex array (n_periods, n_times)
        power         |W|^2 / variance-normalised, NaN where input was NaN
        periods       Fourier periods in hours
        coi           cone of influence in hours for each time point
        times         DatetimeIndex of the input
        dt_hours      sampling interval
    """
    if periods_hours is None:
        periods_hours = period_grid()
    times = series.index
    dt_hours = (times[1] - times[0]).total_seconds() / 3600
    x = series.to_numpy(dtype=float)
    missing = np.isnan(x)
    # Missing samples are set to the mean (0 after standardisation) for the FFT
    # and their coefficients masked afterwards.
    x = np.where(missing, np.nanmean(x) if (~missing).any() else 0.0, x)
    x = x - x.mean()
    n = len(x)
    # Zero-pad to the next power of two to limit wrap-around.
    n_pad = int(2 ** np.ceil(np.log2(n)))
    x_hat = np.fft.fft(x, n_pad)
    omega = 2 * np.pi * np.fft.fftfreq(n_pad, d=dt_hours)

    scales = np.asarray(periods_hours) / FOURIER_FACTOR
    coefficients = np.empty((len(scales), n), dtype=complex)
    for i, scale in enumerate(scales):
        # Normalised Morlet daughter in Fourier space (Torrence & Compo eq. 6).
        norm = np.sqrt(2 * np.pi * scale / dt_hours) * np.pi ** -0.25
        daughter = norm * np.exp(-0.5 * (scale * omega - OMEGA0) ** 2) * (omega > 0)
        coefficients[i] = np.fft.ifft(x_hat * daughter)[:n]

    variance = x.var() if x.var() > 0 else 1.0
    power = np.abs(coefficients) ** 2 / variance
    power[:, missing] = np.nan

    edge = np.minimum(np.arange(n), np.arange(n)[::-1]) * dt_hours
    coi = COI_FACTOR * np.maximum(edge, dt_hours * 1e-3)
    return {"coefficients": coefficients, "power": power, "periods": np.asarray(periods_hours),
            "coi": coi, "times": times, "dt_hours": dt_hours}


def red_noise_significance(series: pd.Series, cwt: dict, confidence: float = 0.95) -> np.ndarray:
    """95% significance threshold per period against an AR(1) background.

    Returns an array (n_periods,) of normalised power levels. Power above
    this level is unlikely under red noise with the series' lag-1
    autocorrelation (Torrence & Compo eq. 16-18, chi-square with 2 dof).
    """
    from scipy.stats import chi2

    x = series.dropna().to_numpy(dtype=float)
    x = x - x.mean()
    alpha = float(np.corrcoef(x[:-1], x[1:])[0, 1]) if len(x) > 2 else 0.0
    alpha = min(max(alpha, 0.0), 0.99)
    freq = cwt["dt_hours"] / cwt["periods"]  # cycles per sample
    background = (1 - alpha ** 2) / (1 + alpha ** 2 - 2 * alpha * np.cos(2 * np.pi * freq))
    return background * chi2.ppf(confidence, 2) / 2


def valid_mask(cwt: dict) -> np.ndarray:
    """True where a coefficient is inside the COI and its sample was observed."""
    inside = cwt["periods"][:, None] <= cwt["coi"][None, :]
    return inside & np.isfinite(cwt["power"])


def band_power(cwt: dict, band: tuple[float, float]) -> pd.Series:
    """Scale-averaged power in a period band, NaN outside the COI.

    Uses the variance-preserving average over log-spaced scales
    (Torrence & Compo eq. 24, up to a constant factor).
    """
    periods = cwt["periods"]
    rows = (periods >= band[0]) & (periods <= band[1])
    if not rows.any():
        raise ValueError(f"No periods inside band {band}")
    power = np.where(valid_mask(cwt), cwt["power"], np.nan)[rows]
    scales = periods[rows] / FOURIER_FACTOR
    empty = np.isnan(power).all(axis=0)
    averaged = np.full(power.shape[1], np.nan)
    averaged[~empty] = np.nanmean(power[:, ~empty] / scales[:, None], axis=0)
    return pd.Series(averaged, index=cwt["times"], name=f"power_{band[0]:g}_{band[1]:g}h")


def circadian_ridge(cwt: dict, band: tuple[float, float] = CIRCADIAN_BAND) -> pd.DataFrame:
    """Dominant period, its power, and instantaneous phase at each time point.

    phase_hours is the clock time at which the band-limited oscillation would
    peak, comparable to a cosinor acrophase. Times outside the COI are NaN.
    """
    periods = cwt["periods"]
    rows = np.flatnonzero((periods >= band[0]) & (periods <= band[1]))
    power = np.where(valid_mask(cwt), cwt["power"], np.nan)[rows]
    usable = ~np.isnan(power).all(axis=0)
    best = np.zeros(power.shape[1], dtype=int)
    best[usable] = np.nanargmax(power[:, usable], axis=0)
    idx = rows[best]
    cols = np.arange(power.shape[1])
    coeff = cwt["coefficients"][idx, cols]
    period = periods[idx]
    times = cwt["times"]
    clock = (times.hour + times.minute / 60 + times.second / 3600).to_numpy(dtype=float)
    # angle(W) = 0 at the oscillation's peak; convert the offset to clock time.
    phase = (clock - np.angle(coeff) / (2 * np.pi) * period) % 24
    out = pd.DataFrame({"period_hours": period, "power": power[best, cols], "phase_hours": phase}, index=times)
    out[~usable] = np.nan
    return out


def daily_wavelet_summary(
    series: pd.Series,
    cwt: dict | None = None,
    band: tuple[float, float] = CIRCADIAN_BAND,
    ultradian: tuple[float, float] = ULTRADIAN_BAND,
    min_coverage: float = 0.5,
) -> pd.DataFrame:
    """One row per calendar day of circadian period, phase and band strength.

    circadian_ratio = circadian / (circadian + ultradian) band power: near 1
    for a clean daily rhythm, falling as ultradian fragmentation grows.
    Days where less than `min_coverage` of samples are usable are omitted.
    """
    cwt = cwt or morlet_cwt(series)
    ridge = circadian_ridge(cwt, band)
    circ = band_power(cwt, band)
    ultra = band_power(cwt, ultradian)
    significance = red_noise_significance(series, cwt)
    level = np.interp(ridge["period_hours"], cwt["periods"], significance)
    frame = ridge.assign(circadian_power=circ, ultradian_power=ultra,
                         significant=ridge["power"] > level)
    rows = []
    for day, group in frame.groupby(frame.index.date):
        usable = group["period_hours"].notna()
        if usable.mean() < min_coverage:
            continue
        g = group[usable]
        angles = g["phase_hours"].to_numpy() * 2 * np.pi / 24
        resultant = np.hypot(np.sin(angles).mean(), np.cos(angles).mean())
        rows.append({
            "date": day,
            "period_hours": float(g["period_hours"].median()),
            "phase_hours": float(np.arctan2(np.sin(angles).mean(), np.cos(angles).mean()) % (2 * np.pi) * 24 / (2 * np.pi)),
            "phase_stability": float(resultant),
            "circadian_power": float(g["circadian_power"].mean()),
            "ultradian_power": float(g["ultradian_power"].mean()),
            "circadian_ratio": float(g["circadian_power"].mean() / (g["circadian_power"].mean() + g["ultradian_power"].mean())),
            "significant_fraction": float(g["significant"].mean()),
            "coverage": float(usable.mean()),
        })
    return pd.DataFrame(rows)


def plot_scalogram(cwt: dict, significance: np.ndarray | None = None, title: str = "", ax=None):
    """Scalogram with COI shading and optional significance contour (matplotlib)."""
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(12, 4))
    times, periods = cwt["times"], cwt["periods"]
    x = mdates.date2num(times.tz_localize(None) if times.tz is not None else times)
    mesh = ax.pcolormesh(x, periods, np.log2(cwt["power"] + 1e-12), shading="auto", cmap="viridis")
    if significance is not None:
        ax.contour(x, periods, cwt["power"] / significance[:, None], levels=[1], colors="white", linewidths=0.8)
    ax.fill_between(x, cwt["coi"], periods.max(), color="white", alpha=0.45, hatch="//")
    for p in (12, 24):
        ax.axhline(p, color="white", ls="--", lw=0.6)
    ax.set_yscale("log", base=2)
    ax.set_ylim(periods.min(), periods.max())
    ax.set_yticks([1, 2, 4, 8, 12, 24, 48])
    ax.set_yticklabels(["1", "2", "4", "8", "12", "24", "48"])
    ax.invert_yaxis()
    ax.xaxis_date()
    ax.set_ylabel("Period (h)")
    ax.set_title(title)
    plt.colorbar(mesh, ax=ax, label="log2 power")
    return ax


def synthetic_recording(days: int = 10, seed: int = 0) -> pd.DataFrame:
    """Activity with a 24 h rhythm that lengthens to 25 h halfway and gains a 4 h ultradian component."""
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2025-01-06", periods=days * 1440, freq="min", tz="Europe/Berlin")
    t = np.arange(len(ts)) / 60
    half = t[-1] / 2
    phase = np.where(t < half, 2 * np.pi * t / 24, 2 * np.pi * half / 24 + 2 * np.pi * (t - half) / 25)
    activity = 50 + 40 * np.cos(phase - np.pi) + np.where(t >= half, 15 * np.cos(2 * np.pi * t / 4), 0)
    activity = np.clip(activity + rng.normal(0, 15, len(t)), 0, None)
    return pd.DataFrame({"DATE/TIME": ts, "PIMn": activity})


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tools.recording import ImportOptions, import_recording

        with open(sys.argv[1], "rb") as handle:
            frame = import_recording(handle, ImportOptions()).data
        column = sys.argv[2] if len(sys.argv) > 2 else "PIMn"
    else:
        frame, column = synthetic_recording(), "PIMn"

    signal = prepare_signal(frame, column, log_transform=column != "TEMPERATURE")
    transform = morlet_cwt(signal)
    print(daily_wavelet_summary(signal, transform).round(3).to_string(index=False))
    try:
        import matplotlib.pyplot as plt

        plot_scalogram(transform, red_noise_significance(signal, transform), title=f"{column} wavelet power")
        plt.tight_layout()
        plt.savefig("wavelet_scalogram.png", dpi=120)
        print("Saved wavelet_scalogram.png")
    except ImportError:
        pass
