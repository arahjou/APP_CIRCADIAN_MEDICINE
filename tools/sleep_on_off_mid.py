
import pandas as pd

# Wake bouts shorter than this inside a sleep episode are treated as
# wake-after-sleep-onset, not as the end of the night.
MAX_WAKE_GAP_MINUTES = 60
# Nights are dated noon-to-noon by the date on which they start.
NIGHT_ANCHOR_HOUR = 12


def sleep_episodes(timestamps: pd.Series, sleep_state: pd.Series,
                   max_wake_gap_minutes: float = MAX_WAKE_GAP_MINUTES) -> pd.DataFrame:
    """Pair onsets/offsets into bouts, then merge bouts split by short wake gaps.

    Returns one row per episode with onset, offset, sleep_minutes, n_bouts,
    night (noon-anchored date) and is_main_sleep (longest episode of the night).
    Bouts still open at the start or end of the recording are dropped.
    """
    ts = pd.to_datetime(timestamps).reset_index(drop=True)
    state = pd.Series(sleep_state).reset_index(drop=True)
    change = state.diff()
    onsets = ts[change == 1].tolist()
    offsets = ts[change == -1].tolist()
    bouts = []
    for onset in onsets:
        following = [t for t in offsets if t > onset]
        if following:
            bouts.append([onset, following[0], (following[0] - onset).total_seconds() / 60])

    episodes: list[list] = []
    for onset, offset, minutes in bouts:
        if episodes and (onset - episodes[-1][1]) < pd.Timedelta(minutes=max_wake_gap_minutes):
            episodes[-1][1] = offset
            episodes[-1][2] += minutes
            episodes[-1][3] += 1
        else:
            episodes.append([onset, offset, minutes, 1])

    out = pd.DataFrame(episodes, columns=["onset", "offset", "sleep_minutes", "n_bouts"])
    if out.empty:
        return out.assign(night=pd.Series(dtype=object), is_main_sleep=pd.Series(dtype=bool))
    onset_local = pd.DatetimeIndex(out["onset"])
    out["night"] = (onset_local - pd.Timedelta(hours=NIGHT_ANCHOR_HOUR)).date
    span = (out["offset"] - out["onset"]).dt.total_seconds()
    # idxmax keeps the first episode on exact ties.
    out["is_main_sleep"] = out.index.isin(span.groupby(out["night"]).idxmax())
    return out


def analyze_sleep_periods(data, max_wake_gap_minutes: float = MAX_WAKE_GAP_MINUTES):
    # Create a copy to avoid SettingWithCopyWarning
    data = data.copy()

    # =============================================================================
    # sleep state analysis
    # Prefer manually edited sleep state from the editor when available.
    if 'SLEEP_STATE' in data.columns:
        used_fallback_sleep_state = False
        data['Sleep_State'] = pd.to_numeric(data['SLEEP_STATE'], errors='coerce').fillna(0).clip(0, 1).astype(int)
    else:
        used_fallback_sleep_state = True
        # Fallback: estimate sleep state from activity counts.
        data['PIMn_avg'] = data['PIMn'].rolling(window=100, min_periods=1, center=True).mean()
        data['Sleep_State'] = data['PIMn_avg'].apply(lambda x: 1 if x < 6 else 0)

    data['DATE/TIME'] = pd.to_datetime(data['DATE/TIME'])
    data = data.sort_values("DATE/TIME").reset_index(drop=True)

    # Fallback labels are noisier; bridge wake gaps up to 2 hours as before.
    gap = 120 if used_fallback_sleep_state else max_wake_gap_minutes
    episodes = sleep_episodes(data['DATE/TIME'], data['Sleep_State'], max_wake_gap_minutes=gap)

    sleep_periods = []
    for row in episodes.itertuples(index=False):
        sleep_duration = row.offset - row.onset
        mid_sleep_time = row.onset + (sleep_duration / 2)
        sleep_periods.append({
            'Sleep_onset_DATE': row.onset.date(),
            'Sleep_onset_Time': row.onset.time(),
            'Sleep_offset_DATE': row.offset.date(),
            'Sleep_offset_TIME': row.offset.time(),
            'mid_sleep_DATE': mid_sleep_time.date(),
            'Mid_sleep_Time': mid_sleep_time.time(),
            'duration_minutes': sleep_duration.total_seconds() / 60,
            'sleep_minutes': float(row.sleep_minutes),
            'n_bouts': int(row.n_bouts),
            'night': row.night,
            'is_main_sleep': bool(row.is_main_sleep),
        })
    return pd.DataFrame(sleep_periods)


def main_sleep_only(periods: pd.DataFrame) -> pd.DataFrame:
    """Rows flagged as the main nightly episode; legacy payloads without the flag pass through."""
    if periods is None or periods.empty or "is_main_sleep" not in periods.columns:
        return periods
    return periods[periods["is_main_sleep"].astype(bool)].reset_index(drop=True)
