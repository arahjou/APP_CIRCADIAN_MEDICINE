# sleep_algos_corrected.py
from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple
from scipy.ndimage import binary_closing, binary_opening


def _ensure_series(x, name="activity") -> pd.Series:
    if isinstance(x, pd.Series):
        s = x.copy()
    else:
        s = pd.Series(x)
    s.name = name
    return s


def _assert_fixed_freq(index: pd.DatetimeIndex):
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("Index must be a pandas DatetimeIndex.")
    if index.tz is None:
        raise ValueError("Index should be timezone-aware (e.g., Europe/Berlin).")
    if index.freq is None and index.inferred_freq is None:
        raise ValueError("Series must have a fixed epoch (set index.freq or resample/asfreq first).")


def _create_inactivity_mask(data: pd.Series, max_zeros: int, fill_value: int = 1) -> pd.Series:
    """
    Create a mask for sequences of consecutive zeros longer than max_zeros.
    
    Matches pyActigraphy behavior:
    - Returns a Series with fill_value (default 1) everywhere
    - Sequences of zeros LONGER than max_zeros are marked with fill_value (1)
    - This marks the INVALID sequences that should be replaced
    
    Note: In pyActigraphy, mask > 0 means "replace this value"
    """
    # Start with zeros (valid)
    mask = pd.Series(0, index=data.index, dtype=int)
    is_zero = (data == 0).astype(int)
    
    # Find runs of zeros
    i = 0
    n = len(is_zero)
    while i < n:
        if is_zero.iloc[i] == 1:
            j = i
            while j < n and is_zero.iloc[j] == 1:
                j += 1
            run_len = j - i
            # Mark sequences LONGER than max_zeros as invalid (set to fill_value)
            if run_len > max_zeros:
                mask.iloc[i:j] = fill_value
            i = j
        else:
            i += 1
    return mask


def _padded_data(data: pd.Series, value: float, periods: int, frequency: pd.Timedelta) -> pd.Series:
    """Pad data at beginning and end with specified value."""
    date_offset = pd.DateOffset(seconds=frequency.total_seconds())
    
    pad_beginning = pd.Series(
        data=value,
        index=pd.date_range(
            end=data.index[0],
            periods=periods,
            freq=date_offset,
            inclusive='left'
        ),
        dtype=data.dtype
    )
    pad_end = pd.Series(
        data=value,
        index=pd.date_range(
            start=data.index[-1],
            periods=periods,
            freq=date_offset,
            inclusive='right'
        ),
        dtype=data.dtype
    )
    return pd.concat([pad_beginning, data, pad_end])


@dataclass
class RawTS:
    """Minimal container for actigraphy-like time series."""
    activity: pd.Series           # counts per epoch (regular, tz-aware)
    light: Optional[pd.Series] = None

    def __post_init__(self):
        self.activity = _ensure_series(self.activity, "activity")
        _assert_fixed_freq(self.activity.index)
        if self.light is not None:
            self.light = self.light.reindex(self.activity.index)

    @property
    def epoch(self) -> pd.Timedelta:
        f = self.activity.index.freq or pd.tseries.frequencies.to_offset(self.activity.index.inferred_freq)
        return pd.Timedelta(f)

    # ---------- 1) Cole–Kripke (with optional Webster rescoring) ----------
    def cole_kripke(
        self,
        settings: str = "auto",
        threshold: float = 1.0,
        rescoring: bool = True,
    ) -> pd.Series:
        """
        Cole–Kripke algorithm for sleep-wake identification.
        
        Parameters
        ----------
        settings : str
            Data reduction settings. Options:
            - "auto": automatically select best setting for data frequency
            - "mean": mean activity per minute (requires <= 60s data)
            - "60s": direct 60-second epoch processing (for 60s data)
            - "10sec_max_overlap": maximum 10-second overlapping epoch per minute
            - "10sec_max_non_overlap": maximum 10-second nonoverlapping epoch per minute  
            - "30sec_max_non_overlap": maximum 30-second nonoverlapping epoch per minute
        threshold : float
            Threshold for sleep/wake scoring. Default is 1.0.
        rescoring : bool
            Whether to apply Webster's rescoring rules. Default is True.
            
        Returns
        -------
        pd.Series
            1=sleep, 0=wake for each epoch (1-minute resolution)
        """
        available_settings = [
            "auto",
            "mean",
            "60s",
            "10sec_max_overlap",
            "10sec_max_non_overlap",
            "30sec_max_non_overlap"
        ]
        
        if settings not in available_settings:
            raise ValueError(
                f"CK settings '{settings}' not available. "
                f"Options: {available_settings}"
            )
        
        data = self.activity.astype(float).fillna(0.0)
        freq = self.epoch
        
        # Auto-select appropriate settings based on data frequency
        if settings == "auto":
            if freq <= pd.Timedelta('5s'):
                settings = "10sec_max_overlap"
            elif freq <= pd.Timedelta('10s'):
                settings = "10sec_max_non_overlap"
            elif freq <= pd.Timedelta('30s'):
                settings = "30sec_max_non_overlap"
            elif freq <= pd.Timedelta('60s'):
                settings = "60s"  # Use direct 60s processing
            else:
                raise ValueError(
                    f"Sampling frequency {freq} too coarse for Cole-Kripke. "
                    "Need <= 60 seconds."
                )
        
        if settings == "mean":
            if freq > pd.Timedelta('60s'):
                raise ValueError(
                    f"Sampling frequency {freq} too coarse for 'mean' settings. "
                    "Need <= 60 seconds."
                )
            # Resample to 60 sec, compute mean (scale factor 30 for 2-sec base)
            rs_f = 30
            data_mean = data.resample('60s').sum() / rs_f
            scale = 0.001
            window = np.array([106, 54, 58, 76, 230, 74, 67, 0, 0], dtype=float)
        
        elif settings == "60s":
            # Direct processing for 60-second epoch data
            # Uses the "mean" weights but without the scaling factor division
            if freq > pd.Timedelta('60s'):
                raise ValueError(
                    f"Sampling frequency {freq} too coarse for '60s' settings. "
                    "Need <= 60 seconds."
                )
            # If data is already at 60s, use directly; otherwise resample
            if freq == pd.Timedelta('60s') or freq == pd.Timedelta('1min'):
                data_mean = data
            else:
                data_mean = data.resample('60s').mean()
            # Use mean settings weights, adjusted scale for direct activity counts
            scale = 0.001
            window = np.array([106, 54, 58, 76, 230, 74, 67, 0, 0], dtype=float)
            
        elif settings == "10sec_max_overlap":
            if freq > pd.Timedelta('5s'):
                raise ValueError(
                    f"Sampling frequency {freq} too coarse for '10sec_max_overlap'. "
                    "Need <= 5 seconds."
                )
            data_5s = data.resample('5s').sum()
            data_10s = data_5s.rolling('10s').sum()
            data_mean = data_10s.resample('60s').max()
            scale = 0.00001
            window = np.array([50, 30, 300, 400, 1400, 500, 350, 0, 0], dtype=float)
            
        elif settings == "10sec_max_non_overlap":
            if freq > pd.Timedelta('10s'):
                raise ValueError(
                    f"Sampling frequency {freq} too coarse for '10sec_max_non_overlap'. "
                    "Need <= 10 seconds."
                )
            data_10s = data.resample('10s').sum()
            data_mean = data_10s.resample('60s').max()
            scale = 0.00001
            window = np.array([550, 378, 413, 699, 1736, 287, 300, 0, 0], dtype=float)
            
        elif settings == "30sec_max_non_overlap":
            if freq > pd.Timedelta('30s'):
                raise ValueError(
                    f"Sampling frequency {freq} too coarse for '30sec_max_non_overlap'. "
                    "Need <= 30 seconds."
                )
            data_30s = data.resample('30s').sum()
            data_mean = data_30s.resample('60s').max()
            scale = 0.0001
            window = np.array([50, 30, 14, 28, 12, 8, 50, 0, 0], dtype=float)
        
        # Apply Cole-Kripke convolution
        def _window_convolution(x, scale, window):
            return scale * np.dot(x, window)
        
        ck = data_mean.rolling(
            window.size, center=True
        ).apply(_window_convolution, args=(scale, window), raw=True)
        
        sleep = (ck < threshold).astype(int)
        sleep = pd.Series(sleep, index=data_mean.index, name="ck_sleep")
        
        if rescoring:
            sleep = self._webster_rescoring(sleep)
        
        return sleep

    @staticmethod
    def _webster_rescoring(labels: pd.Series) -> pd.Series:
        """
        Apply Webster's rescoring rules to sleep/wake labels.
        
        Rules (assuming 1-minute epochs):
        1. After >=4 min wake, next 1 min sleep → wake
        2. After >=10 min wake, next 3 min sleep → wake
        3. After >=15 min wake, next 4 min sleep → wake
        4. Sleep <=6 min surrounded by >=10 min wake on each side → wake
        5. Sleep <=10 min surrounded by >=20 min wake on each side → wake
        """
        x = labels.to_numpy().astype(int).copy()
        n = len(x)
        
        # Calculate epochs per minute based on index
        idx = labels.index
        if len(idx) > 1:
            epoch_sec = (idx[1] - idx[0]).total_seconds()
        else:
            epoch_sec = 60.0
        
        def m_to_ep(minutes):
            return max(1, int(round((minutes * 60.0) / epoch_sec)))
        
        def count_wake_before(i, min_count):
            """Count consecutive wake (0) epochs before position i."""
            count = 0
            j = i - 1
            while j >= 0 and x[j] == 0:
                count += 1
                j -= 1
            return count >= min_count
        
        # Rules 1-3: After wake run, rescore initial sleep to wake
        rules = [(4, 1), (10, 3), (15, 4)]
        for wake_min, sleep_min in rules:
            wake_ep = m_to_ep(wake_min)
            sleep_ep = m_to_ep(sleep_min)
            i = 0
            while i < n:
                if x[i] == 1 and count_wake_before(i, wake_ep):
                    # Rescore up to sleep_ep epochs of sleep to wake
                    end = min(n, i + sleep_ep)
                    j = i
                    while j < end and x[j] == 1:
                        x[j] = 0
                        j += 1
                    i = j
                else:
                    i += 1
        
        # Rule 4: Sleep <=6 min surrounded by >=10 min wake → wake
        # Rule 5: Sleep <=10 min surrounded by >=20 min wake → wake
        isolation_rules = [(6, 10), (10, 20)]
        for max_sleep_min, surround_wake_min in isolation_rules:
            max_sleep_ep = m_to_ep(max_sleep_min)
            surround_ep = m_to_ep(surround_wake_min)
            i = 0
            while i < n:
                if x[i] == 1:
                    # Find end of sleep run
                    j = i
                    while j < n and x[j] == 1:
                        j += 1
                    run_len = j - i
                    
                    if run_len <= max_sleep_ep:
                        # Check wake before
                        wake_before = 0
                        k = i - 1
                        while k >= 0 and x[k] == 0:
                            wake_before += 1
                            k -= 1
                        
                        # Check wake after
                        wake_after = 0
                        k = j
                        while k < n and x[k] == 0:
                            wake_after += 1
                            k += 1
                        
                        if wake_before >= surround_ep and wake_after >= surround_ep:
                            x[i:j] = 0
                    i = j
                else:
                    i += 1
        
        return pd.Series(x, index=labels.index, name=labels.name)

    # ---------- 2) Sadeh ----------
    def sadeh(
        self,
        offset: float = 7.601,
        weights: Iterable[float] = (-0.065, -1.08, -0.056, -0.703),
        threshold: float = 0.0,
    ) -> pd.Series:
        """
        Sadeh algorithm for sleep-wake identification.
        
        PS = offset + w[0]*mean_W5 + w[1]*NAT + w[2]*sd_Last6 + w[3]*logAct
        Sleep if PS >= threshold.
        
        Parameters
        ----------
        offset : float
            Offset value. Default is 7.601.
        weights : Iterable[float]
            Weights for [mean_W5, NAT, sd_Last6, logAct]. 
            Default is (-0.065, -1.08, -0.056, -0.703).
        threshold : float
            Threshold for sleep classification. Default is 0.0.
            
        Returns
        -------
        pd.Series
            1=sleep, 0=wake
        """
        data = self.activity.astype(float).fillna(0.0)
        
        w = np.array(list(weights), dtype=float)
        if len(w) != 4:
            raise ValueError("Sadeh 'weights' must have 4 values.")
        
        # 11-epoch centered rolling window for mean_W5 and NAT
        r = data.rolling(11, center=True)
        
        # mean_W5: mean of 11-epoch window (5 before + current + 5 after)
        mean_W5 = r.mean()
        
        # NAT: count of epochs with activity in [50, 100) within 11-epoch window
        def count_nat(x):
            return np.sum((x >= 50) & (x < 100))
        NAT = r.apply(count_nat, raw=True)
        
        # sd_Last6: std of current + 5 previous epochs (6 total)
        sd_Last6 = data.rolling(6).std()  # ddof=1 by default
        
        # logAct: log(1 + activity) of NEXT epoch (shift -1)
        logAct = data.shift(-1).apply(lambda x: np.log(1 + x) if pd.notna(x) else np.nan)
        
        # Calculate PS score
        PS = offset + w[0]*mean_W5 + w[1]*NAT + w[2]*sd_Last6 + w[3]*logAct
        
        labels = (PS >= threshold).astype(int)
        return pd.Series(labels, index=data.index, name="sadeh_sleep")

    # ---------- 3) Oakley ----------
    def oakley(
        self,
        threshold: float | str = 40,
        auto_pct: Optional[float] = None,
    ) -> pd.Series:
        """
        Oakley algorithm for sleep-wake identification.
        
        Automatically selects weights based on sampling frequency.
        
        Parameters
        ----------
        threshold : float or str
            Threshold for sleep/wake scoring. Use 'automatic' for 
            automatic threshold calculation. Default is 40.
        auto_pct : float, optional
            If provided and threshold='automatic', uses this percentile
            of nonzero activity counts as the threshold instead of the
            Actiware mobile-time formula. Range 0-1. Default is None
            (use Actiware formula).
            
        Returns
        -------
        pd.Series
            1=sleep, 0=wake
        """
        data = self.activity.astype(float).fillna(0.0)
        freq = self.epoch
        
        # Select weights based on sampling frequency
        if freq == pd.Timedelta('15s'):
            window = np.array([
                0.04, 0.04, 0.04, 0.04,  # W_{-8} to W_{-5}
                0.20, 0.20, 0.20, 0.20,  # W_{-4} to W_{-1}
                4.00,                     # W_{0}
                0.20, 0.20, 0.20, 0.20,  # W_{+1} to W_{+4}
                0.04, 0.04, 0.04, 0.04   # W_{+5} to W_{+8}
            ], dtype=float)
        elif freq == pd.Timedelta('30s'):
            window = np.array([
                0.04, 0.04,  # W_{-4}, W_{-3}
                0.20, 0.20,  # W_{-2}, W_{-1}
                2.00,        # W_{0}
                0.20, 0.20,  # W_{+1}, W_{+2}
                0.04, 0.04   # W_{+3}, W_{+4}
            ], dtype=float)
        elif freq == pd.Timedelta('60s') or freq == pd.Timedelta('1min'):
            window = np.array([
                0.04,  # W_{-2}
                0.20,  # W_{-1}
                1.00,  # W_{0}
                0.20,  # W_{+1}
                0.04   # W_{+2}
            ], dtype=float)
        elif freq == pd.Timedelta('120s') or freq == pd.Timedelta('2min'):
            window = np.array([
                0.125,  # W_{-1}
                0.50,   # W_{0}
                0.125   # W_{+1}
            ], dtype=float)
        else:
            raise ValueError(
                f"Oakley algorithm not defined for sampling frequency {freq}. "
                f"Accepted: 15s, 30s, 60s, 120s"
            )
        
        # Calculate threshold
        if threshold == 'automatic':
            if auto_pct is not None:
                # Use percentile-based threshold
                nz = data[data > 0]
                if len(nz) > 0:
                    threshold = np.percentile(nz, auto_pct * 100)
                else:
                    threshold = 0.0
            else:
                # Use Actiware mobile-time formula
                threshold = self._actiware_automatic_threshold(data)
        elif not np.isscalar(threshold):
            raise ValueError("`threshold` should be a scalar or 'automatic'.")
        
        # Apply weighted sum
        def _window_convolution(x, window):
            return np.dot(x, window)
        
        oakley = data.rolling(
            window.size, center=True
        ).apply(_window_convolution, args=(window,), raw=True)
        
        labels = (oakley <= threshold).astype(int)
        return pd.Series(labels, index=data.index, name="oakley_sleep")
    
    def _actiware_automatic_threshold(self, data: pd.Series, scale_factor: float = 0.88888) -> float:
        """
        Calculate automatic wake threshold (Actiware method).
        
        1. Sum all activity counts
        2. Count epochs scored as MOBILE (activity >= epoch_length/15sec)
        3. Compute MOBILE_TIME = mobile_epochs * epoch_length (in minutes)
        4. Auto threshold = (sum_counts / mobile_time) * 0.88888
        """
        freq = self.epoch
        
        # Sum of activity counts
        counts_sum = data.sum()
        
        # Mobile threshold: activity >= number of 15-sec intervals in epoch
        mobile_thr = int(freq / pd.Timedelta('15s'))
        
        # Count mobile epochs
        counts_mobile = (data.values >= mobile_thr).astype(int).sum()
        
        # Mobile time in minutes
        mobile_time = counts_mobile * (freq / pd.Timedelta('1min'))
        
        if mobile_time == 0:
            return 0.0
        
        # Automatic threshold
        automatic_thr = (counts_sum / mobile_time) * scale_factor
        
        return automatic_thr

    # ---------- 4) Crespo ----------
    def crespo(
        self,
        zeta: int = 15,
        zeta_r: int = 30,
        zeta_a: int = 2,
        t: float = 0.33,
        alpha: str = '8h',
        beta: str = '1h',
        estimate_zeta: bool = False,
        seq_length_max: int = 100,
        verbose: bool = False,
        # Aliases for backward compatibility with simplified interface
        zeta_min_zero_min: Optional[int] = None,
        rest_merge_gap_min: Optional[int] = None,
        min_rest_block_min: Optional[int] = None,
    ) -> pd.Series:
        """
        Crespo algorithm for activity-rest identification.
        
        Algorithm for automatic identification of activity-rest periods based
        on actigraphy, developed by Crespo et al.
        
        Parameters
        ----------
        zeta : int
            Maximum consecutive zeros considered valid. Default is 15.
        zeta_r : int
            Maximum consecutive zeros during rest periods. Default is 30.
        zeta_a : int
            Maximum consecutive zeros during active periods. Default is 2.
        t : float
            Percentile for replacing invalid zeros. Default is 0.33.
        alpha : str
            Average sleep duration (for window size). Default is '8h'.
        beta : str
            Padding/morphological filter size. Default is '1h'.
        estimate_zeta : bool
            Whether to estimate zeta from data. Default is False.
        seq_length_max : int
            Max sequence length for zeta estimation. Default is 100.
        verbose : bool
            Print estimated zeta values. Default is False.
        zeta_min_zero_min : int, optional
            Alias for zeta (in minutes). If provided, overrides zeta.
        rest_merge_gap_min : int, optional
            Not used in full Crespo, kept for API compatibility.
        min_rest_block_min : int, optional
            Minimum rest block duration in minutes. Maps to beta.
            
        Returns
        -------
        pd.Series
            1=activity, 0=rest (matching pyActigraphy convention)
        """
        # Handle parameter aliases
        if zeta_min_zero_min is not None:
            zeta = zeta_min_zero_min
        if min_rest_block_min is not None:
            beta = f'{min_rest_block_min}min'
        
        data = self.activity.astype(float).fillna(0.0)
        freq = self.epoch
        
        # ===== Stage 1: Pre-processing =====
        # This stage produces an initial estimate of the rest-activity periods
        
        # 1.1 Signal conditioning based on empirical probability model
        if estimate_zeta:
            zeta = self._estimate_zeta(data, seq_length_max)
            if verbose:
                print(f"CRESPO: estimated zeta = {zeta}")
        
        # Create mask for sequences of > zeta consecutive zeros
        # mask > 0 means "invalid sequence to be replaced"
        mask_zeta = _create_inactivity_mask(data, zeta, fill_value=1)
        
        # Get t-percentile value
        s_t = data.quantile(t)
        
        # Replace invalid zeros (where mask > 0) with percentile value
        x = data.copy()
        x[mask_zeta > 0] = s_t
        
        # Median filter window length L_w
        L_w = int(pd.Timedelta(alpha) / freq) + 1
        L_w_over_2 = int((L_w - 1) / 2)
        
        # Pad signal with max value
        s_t_max = data.max()
        x_p = _padded_data(data, s_t_max, L_w_over_2, freq)
        
        # 1.2 Rank-order processing and decision logic
        # Apply median filter
        x_f = x_p.rolling(L_w, center=True, min_periods=L_w_over_2).median()
        
        # Threshold at alpha/24h percentile
        p_threshold = x_f.quantile(pd.Timedelta(alpha) / pd.Timedelta('24h'))
        y_1 = pd.Series(np.where(x_f > p_threshold, 1, 0), index=x_f.index)
        
        # 1.3 Morphological filtering
        L_p = int(pd.Timedelta(beta) / freq) + 1
        M_f = np.ones(L_p)
        
        # Apply morphological closing then opening
        y_1_close = binary_closing(y_1.values, M_f).astype(int)
        y_1_open = binary_opening(y_1_close, M_f).astype(int)
        y_e = pd.Series(y_1_open, index=y_1.index)
        
        # ===== Stage 2: Processing =====
        # Uses estimates from previous stage
        
        # 2.1 Model-based data validation
        if estimate_zeta:
            rest_data = data[y_e < 1]
            active_data = data[y_e > 0]
            if len(rest_data) > 0:
                zeta_r = self._estimate_zeta(rest_data, seq_length_max)
            if len(active_data) > 0:
                zeta_a = self._estimate_zeta(active_data, seq_length_max)
            if verbose:
                print(f"CRESPO: estimated zeta_rest = {zeta_r}")
                print(f"CRESPO: estimated zeta_active = {zeta_a}")
        
        # Create masks for rest and active periods separately
        # Filter data by y_e to get rest periods (y_e < 1) and active periods (y_e > 0)
        rest_periods = data[y_e < 1]
        active_periods = data[y_e > 0]
        
        mask_rest = _create_inactivity_mask(rest_periods, zeta_r, fill_value=1)
        mask_actv = _create_inactivity_mask(active_periods, zeta_a, fill_value=1)
        
        # Combine masks
        mask = pd.concat([mask_actv, mask_rest], verify_integrity=True).sort_index()
        
        # 2.2 Adaptive rank-order processing
        # Replace masked values (invalid) with NaN
        x_nan = data.copy()
        x_nan[mask > 0] = np.nan
        
        # Pad for adaptive filtering
        x_sp = _padded_data(x_nan, s_t_max, L_p - 1, freq)
        
        # Apply adaptive median filter
        x_fa = x_sp.rolling(L_w, center=True, min_periods=L_p - 1).median()
        
        # Handle edge bias - compute expanding median for edges
        # The original pyActigraphy code has a bug with expanding(center=True)
        # We use a corrected version
        if L_w_over_2 > 0 and len(x_sp) >= L_w:
            # For start: cumulative median
            median_start = x_sp.iloc[0:L_w].expanding().median()
            x_fa.iloc[0:L_w_over_2] = median_start.iloc[0:L_w_over_2]
            
            # For end: reverse cumulative median
            if len(x_sp) > L_w:
                end_slice = x_sp.iloc[-L_w:]
                median_end = end_slice.iloc[::-1].expanding().median().iloc[::-1]
                x_fa.iloc[-L_w_over_2:] = median_end.iloc[-L_w_over_2:]
        
        # Restore original time range
        x_fa = x_fa[data.index[0]:data.index[-1]]
        
        # Final thresholding
        p_threshold = x_fa.quantile(pd.Timedelta(alpha) / pd.Timedelta('24h'))
        y_2 = pd.Series(np.where(x_fa > p_threshold, 1, 0), index=x_fa.index)
        
        # 2.3 Final morphological filtering
        struct_size = 2 * (L_p - 1) + 1
        y_2_close = binary_closing(y_2.values, structure=np.ones(struct_size)).astype(int)
        y_2_open = binary_opening(y_2_close, structure=np.ones(struct_size)).astype(int)
        
        crespo = pd.Series(y_2_open, index=y_2.index, name="crespo_activity")
        
        # Manual post-processing (match pyActigraphy)
        crespo.iloc[0] = 1
        crespo.iloc[-1] = 1
        
        return crespo
    
    def _estimate_zeta(self, data: pd.Series, seq_length_max: int, n_bootstrap: int = 100, level: float = 0.05) -> int:
        """Estimate zeta parameter from ratio of zero sequences."""
        ratios_list: list[float] = []
        for seq_len in range(1, seq_length_max + 1):
            rolling_sum = data.rolling(seq_len).sum()
            np.random.seed(0)
            sample = np.random.choice(
                rolling_sum.dropna().values,
                size=min(n_bootstrap * len(rolling_sum), len(rolling_sum.dropna())),
                replace=True
            )
            ratio = 1 - np.count_nonzero(sample) / len(sample) if len(sample) > 0 else 0
            ratios_list.append(ratio)
        
        ratios = np.array(ratios_list)
        zeta_est = int(np.argmax(ratios < level))
        return max(1, zeta_est)

    # ---------- 5) MASDA / MASDA ----------
    def roenneberg(
        self,
        trend_period: str = '24h',
        min_trend_period: str = '12h',
        threshold: float = 0.15,
        min_seed_period: str = '30min',
        max_test_period: str = '12h',
        rsfreq: Optional[str] = None,
        # Aliases for backward compatibility
        threshold_frac: Optional[float] = None,
        min_seed_min: Optional[int] = None,
        merge_gap_min: Optional[int] = None,
        analysis_epoch_min: Optional[int] = None,
    ) -> pd.Series:
        """
        MASDA algorithm for sleep detection.
        
        Parameters
        ----------
        trend_period : str
            Rolling window for trend calculation. Default is '24h'.
        min_trend_period : str
            Minimum periods for trend calculation. Default is '12h'.
        threshold : float
            Fraction of trend for sleep threshold. Default is 0.15.
        min_seed_period : str
            Minimum duration for sleep seeds. Default is '30min'.
        max_test_period : str
            Maximum test period for correlation. Default is '12h'.
        rsfreq : str, optional
            Resampling frequency. Default is None (use native).
        threshold_frac : float, optional
            Alias for threshold. If provided, overrides threshold.
        min_seed_min : int, optional
            Minimum seed period in minutes. If provided, overrides min_seed_period.
        merge_gap_min : int, optional
            Gap in minutes for merging sleep periods. If provided, influences
            the merge gap calculation.
        analysis_epoch_min : int, optional
            Analysis epoch in minutes. If provided, sets rsfreq.
            
        Returns
        -------
        pd.Series
            1=sleep, 0=wake
        """
        # Handle parameter aliases
        if threshold_frac is not None:
            threshold = threshold_frac
        if min_seed_min is not None:
            min_seed_period = f'{min_seed_min}min'
        if analysis_epoch_min is not None:
            rsfreq = f'{analysis_epoch_min}min'
        
        data = self.activity.astype(float).fillna(0.0)
        
        if rsfreq is not None:
            rsdata = data.resample(rsfreq).mean()
            rsdata = rsdata.asfreq(rsfreq)
        else:
            rsdata = data
        
        freq = rsdata.index.freq or pd.tseries.frequencies.to_offset(rsdata.index.inferred_freq)
        freq_td = pd.Timedelta(freq)
        
        # Calculate trend (24h centered moving average)
        trend_epochs = int(pd.Timedelta(trend_period) / freq_td)
        min_periods = int(pd.Timedelta(min_trend_period) / freq_td)
        
        trend = rsdata.rolling(
            trend_epochs, 
            center=True, 
            min_periods=min_periods
        ).mean()
        
        # Initial putative sleep: activity < threshold * trend
        putative_sleep = (rsdata < (threshold * trend)).astype(int)
        putative_sleep = putative_sleep.fillna(0).astype(int)
        
        # Filter by minimum seed period
        min_seed_epochs = int(pd.Timedelta(min_seed_period) / freq_td)
        
        # Process sleep runs
        x = putative_sleep.to_numpy().copy()
        n = len(x)
        i = 0
        while i < n:
            if x[i] == 1:
                j = i
                while j < n and x[j] == 1:
                    j += 1
                run_len = j - i
                if run_len < min_seed_epochs:
                    x[i:j] = 0
                i = j
            else:
                i += 1
        
        # Merge close sleep periods (within max_test_period / 4 as heuristic)
        merge_gap = int(pd.Timedelta(max_test_period) / freq_td / 4)
        i = 0
        while i < n:
            if x[i] == 1:
                j = i
                while j < n and x[j] == 1:
                    j += 1
                # Look for next sleep within merge_gap
                k = j
                while k < n and x[k] == 0 and (k - j) <= merge_gap:
                    k += 1
                if k < n and x[k] == 1 and (k - j) <= merge_gap:
                    x[j:k] = 1
                    i = k
                else:
                    i = j
            else:
                i += 1
        
        sleep = pd.Series(x, index=rsdata.index, name="roenneberg_sleep")
        
        # Resample back to native frequency if needed
        if rsfreq is not None:
            sleep = sleep.reindex(data.index, method='pad').fillna(0).astype(int)
        
        return sleep

    # ---------- Convenience methods for onset/offset times ----------
    def crespo_aot(self, **kwargs) -> Tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
        """Get activity onset/offset times from Crespo algorithm."""
        crespo = self.crespo(**kwargs)
        diff = crespo.diff(1)
        AonT = crespo[diff == 1].index
        AoffT = crespo[diff == -1].index
        return (AonT, AoffT)
    
    def roenneberg_aot(self, **kwargs) -> Tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
        """Get activity onset/offset times from MASDA algorithm."""
        rbg = self.roenneberg(**kwargs)
        diff = rbg.diff(1)
        AonT = rbg[diff == -1].index  # Wake to sleep transition
        AoffT = rbg[diff == 1].index   # Sleep to wake transition
        return (AonT, AoffT)


# ------------------------ Convenience: build RawTS from DataFrame ------------------------
def build_raw_from_df(
    df: pd.DataFrame,
    epoch: str = "60s",
    tz: str = "UTC",
    timestamp_col: str = "timestamp",
    activity_col: str = "activity",
    light_col: Optional[str] = None
) -> RawTS:
    """
    Build RawTS from a DataFrame with flexible column names.
    
    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame
    epoch : str
        Resampling frequency (e.g., '60s', '1min')
    tz : str
        Timezone string (e.g., 'UTC', 'Europe/Berlin')
    timestamp_col : str
        Name of timestamp column
    activity_col : str
        Name of activity column to use
    light_col : Optional[str]
        Name of light column (if available)
        
    Returns
    -------
    RawTS
        RawTS object with activity (and optionally light) data
    """
    d = df.copy()
    
    if timestamp_col not in d.columns:
        raise ValueError(f"Timestamp column '{timestamp_col}' not found in DataFrame")
    if activity_col not in d.columns:
        raise ValueError(f"Activity column '{activity_col}' not found in DataFrame")
    
    d[timestamp_col] = pd.to_datetime(d[timestamp_col])
    
    # Handle timezone
    if d[timestamp_col].dt.tz is None:
        d[timestamp_col] = d[timestamp_col].dt.tz_localize(tz)
    else:
        d[timestamp_col] = d[timestamp_col].dt.tz_convert(tz)
    
    d = d.sort_values(timestamp_col).set_index(timestamp_col)
    
    activity_series = d[activity_col]
    
    # Regularize to fixed cadence if needed
    if d.index.freq is None:
        activity_series = activity_series.resample(epoch).mean()
        activity_series = activity_series.asfreq(epoch)
    
    # Handle light column if provided
    light_series = None
    if light_col and light_col in d.columns:
        light_series = d[light_col].reindex(activity_series.index)
    
    return RawTS(activity=activity_series, light=light_series)