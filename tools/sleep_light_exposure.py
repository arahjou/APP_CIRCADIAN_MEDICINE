
import numpy as np
import pandas as pd

from tools.sleep_on_off_mid import MAX_WAKE_GAP_MINUTES, sleep_episodes

WINDOW = pd.Timedelta(hours=3)


def analyze_sleep_light_exposure(df_subset):
    """Light exposure around the main nightly sleep episode, per night.

    Episodes come from `sleep_episodes` (short wake bouts merged, longest
    episode per noon-to-noon night). Minutes are classified from raw one-minute
    melanopic EDI; no smoothing, so daytime light is not carried into sleep.

    metric1: minutes >= 1 lux during the main sleep episode
    metric2: minutes >= 10 lux in the 3 hours before main sleep onset
    metric3: minutes < 250 lux in the 3 hours after final wake-up

    Every night with an evaluable window is reported, including zero minutes.
    Windows that extend beyond the recording are omitted for that night.
    """
    df = df_subset.copy()
    df["DATE/TIME"] = pd.to_datetime(df["DATE/TIME"])
    df = df.sort_values("DATE/TIME").reset_index(drop=True)

    if "SLEEP_STATE" in df.columns:
        sleep_state = pd.to_numeric(df["SLEEP_STATE"], errors="coerce").fillna(0).clip(0, 1).astype(int)
        gap = MAX_WAKE_GAP_MINUTES
    else:
        # Fallback to activity-derived state estimation.
        smoothed = df["PIMn"].rolling(window=100, min_periods=1, center=True).mean()
        sleep_state = pd.Series(np.where(smoothed < 6, 1, 0), index=df.index)
        gap = 120
    episodes = sleep_episodes(df["DATE/TIME"], sleep_state, max_wake_gap_minutes=gap)
    episodes = episodes[episodes["is_main_sleep"]] if not episodes.empty else episodes

    ts = df["DATE/TIME"]
    lux = pd.to_numeric(df["MELANOPIC EDI"], errors="coerce")
    first, last = ts.iloc[0], ts.iloc[-1]

    def minutes(start, end, condition):
        # Half-open [start, end): offset is the first wake epoch.
        if start < first or end > last + pd.Timedelta(minutes=1):
            return None
        return int(((ts >= start) & (ts < end) & condition).sum())

    rows = {"metric1": [], "metric2": [], "metric3": []}
    for ep in episodes.itertuples(index=False):
        night = str(ep.night)
        values = {
            "metric1": minutes(ep.onset, ep.offset, lux >= 1),
            "metric2": minutes(ep.onset - WINDOW, ep.onset, lux >= 10),
            "metric3": minutes(ep.offset, ep.offset + WINDOW, lux < 250),
        }
        for key, value in values.items():
            if value is not None:
                rows[key].append({"date": night, "minutes": value})

    empty_messages = {
        "metric1": "No complete main sleep episode available for light-during-sleep.",
        "metric2": "No complete 3-hour pre-sleep window available.",
        "metric3": "No complete 3-hour post-wake window available.",
    }
    return {key: rows[key] if rows[key] else empty_messages[key] for key in rows}
