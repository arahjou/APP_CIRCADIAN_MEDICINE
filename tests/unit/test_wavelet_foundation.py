import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_path = Path(__file__).resolve().parents[2] / "Development" / "wavelet_analysis.py"
_spec = importlib.util.spec_from_file_location("wavelet_analysis", _path)
wavelet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wavelet)


@pytest.mark.parametrize("peak_hour", [4.0, 15.0, 22.5])
def test_recovers_period_and_phase_of_pure_rhythm(peak_hour):
    ts = pd.date_range("2025-01-06", periods=8 * 1440, freq="min", tz="Europe/Berlin")
    hours = np.arange(len(ts)) / 60
    frame = pd.DataFrame({"DATE/TIME": ts, "PIMn": 50 + 40 * np.cos(2 * np.pi * (hours - peak_hour) / 24)})
    signal = wavelet.prepare_signal(frame, "PIMn")
    daily = wavelet.daily_wavelet_summary(signal)
    daily = daily[daily.coverage == 1]  # days fully inside the cone of influence
    assert not daily.empty
    assert np.allclose(daily.period_hours, 24, atol=0.5)
    assert np.allclose((daily.phase_hours - peak_hour + 12) % 24 - 12, 0, atol=0.25)
    assert (daily.circadian_ratio > 0.95).all()


def test_long_gaps_are_masked():
    frame = wavelet.synthetic_recording(days=6)
    frame.loc[3000:3400, "PIMn"] = np.nan
    signal = wavelet.prepare_signal(frame, "PIMn")
    cwt = wavelet.morlet_cwt(signal)
    assert np.isnan(cwt["power"][:, signal.isna().to_numpy()]).all()
