import numpy as np
import pandas as pd
import pytest

from tools.activity_cosinor import fit_cosinor_daily_activity
from tools.light_cosinor import fit_cosinor_daily_activity as fit_light


@pytest.mark.parametrize("phase", [0, 3, 12, 18, 23.5])
@pytest.mark.parametrize("fitter,signal", [(fit_cosinor_daily_activity, "PIMn"), (fit_light, "MELANOPIC EDI")])
def test_known_phase_amplitude_every_day(fitter, signal, phase):
    ts = pd.date_range("2026-01-01", periods=3 * 1440, freq="min", tz="Europe/Berlin")
    hours = np.arange(len(ts)) / 60
    data = pd.DataFrame({"DATE/TIME": ts, signal: 50 + 45 * np.cos(2 * np.pi * (hours - phase) / 24)})
    fit = fitter(data)
    assert len(fit) == 3
    assert np.allclose(fit.amplitude, 45)
    assert np.allclose(fit.mesor, 50)
    assert np.allclose((fit.acrophase_hours - phase + 12) % 24 - 12, 0, atol=1e-8)
    assert np.allclose(fit.r_squared, 1)


def test_flat_signal_has_no_defined_phase():
    df = pd.DataFrame({"DATE/TIME": pd.date_range("2026-01-01", periods=1440, freq="min"), "PIMn": 10})
    out = fit_cosinor_daily_activity(df)
    assert out.acrophase_hours.isna().all()
    assert out.r_squared.isna().all()
