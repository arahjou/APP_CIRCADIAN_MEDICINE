import pandas as pd
import numpy as np

def analyze_sleep_periods(df, 
                          pim_col='PIMn', 
                          datetime_col='DATE/TIME', 
                          rolling_window=100, 
                          sleep_threshold=6, 
                          gap_fill_hours=2):
    """
    Analyzes time-series data to identify sleep periods, onsets, offsets, and mid-sleep times.

    The process involves:
    1. Defining sleep state based on a rolling average of a physiological indicator.
    2. Cleaning the data by filling short "awake" gaps within sleep periods.
    3. Pairing sleep onsets with wake-up offsets to define complete sleep periods.
    4. Calculating the midpoint and duration of each sleep period.

    Args:
        df (pd.DataFrame): The input DataFrame containing the time-series data.
        pim_col (str): The name of the column containing the physiological indicator of movement.
        datetime_col (str): The name of the column containing datetime information.
        rolling_window (int): The window size for the rolling average calculation.
        sleep_threshold (float): The threshold below which the rolling average indicates sleep.
        gap_fill_hours (int): The maximum duration (in hours) of an "awake" period 
                              to be filled if it's surrounded by sleep.

    Returns:
        pd.DataFrame: A summary DataFrame with columns for onset, offset, mid-sleep,
                      and duration for each identified sleep period. Returns an empty
                      DataFrame if no complete sleep periods are found.
    """
    # --- 0. PREPARATION ---
    # Work on a copy to avoid modifying the original DataFrame
    data = df.copy()

    # Ensure datetime column is in the correct format and sort the data
    if not pd.api.types.is_datetime64_any_dtype(data[datetime_col]):
        data[datetime_col] = pd.to_datetime(data[datetime_col])
    data = data.sort_values(datetime_col).reset_index(drop=True)

    # --- 1. DEFINE SLEEP STATE & CLEAN GAPS ---
    # Calculate the rolling average for the physiological indicator
    data['PIMn_avg'] = data[pim_col].rolling(window=rolling_window, min_periods=1).mean()

    # Define sleep state (1 for sleep, 0 for awake) based on the threshold
    data['Sleep_State'] = np.where(data['PIMn_avg'] < sleep_threshold, 1, 0)

    # Fill short gaps (brief awakenings) in sleep periods
    initial_transitions = data['Sleep_State'].diff()
    wake_up_indices = initial_transitions[initial_transitions == -1].index
    sleep_onset_indices = initial_transitions[initial_transitions == 1].index

    for wake_idx in wake_up_indices:
        # Find the next sleep onset after this wake-up
        next_sleep_onsets = sleep_onset_indices[sleep_onset_indices > wake_idx]
        if not next_sleep_onsets.empty:
            next_sleep_idx = next_sleep_onsets[0]
            
            # Check the duration of the "awake" gap
            duration = data.loc[next_sleep_idx, datetime_col] - data.loc[wake_idx, datetime_col]
            
            # If the gap is short, fill it by marking it as sleep
            if duration < pd.Timedelta(hours=gap_fill_hours):
                data.loc[wake_idx:next_sleep_idx-1, 'Sleep_State'] = 1

    # --- 2. IDENTIFY AND PAIR TRANSITIONS ---
    # Identify the final, cleaned transitions into and out of sleep
    data['sleep_transition'] = data['Sleep_State'].diff()
    transitions_df = data[data['sleep_transition'].isin([1, -1])].copy()
    
    # Separate the onsets (start of sleep) and offsets (end of sleep)
    onsets = transitions_df[transitions_df['sleep_transition'] == 1]
    offsets = transitions_df[transitions_df['sleep_transition'] == -1]

    sleep_periods = []
    # Iterate through each sleep onset to find its corresponding offset
    for _, onset_row in onsets.iterrows():
        onset_time = onset_row[datetime_col]
        
        # Find the first wake-up event that occurs *after* this sleep onset
        next_offsets = offsets[offsets[datetime_col] > onset_time]
        
        if not next_offsets.empty:
            offset_row = next_offsets.iloc[0]
            offset_time = offset_row[datetime_col]
            
            # --- 3. CALCULATE MID-SLEEP AND STORE RESULTS ---
            sleep_duration = offset_time - onset_time
            mid_sleep_time = onset_time + (sleep_duration / 2)
            
            period_data = {
                'Sleep_Onset': onset_time,
                'Sleep_Offset': offset_time,
                'Mid_Sleep': mid_sleep_time,
                'Duration': sleep_duration
            }
            sleep_periods.append(period_data)

    # Convert the list of dictionaries into the final summary DataFrame
    summary_df = pd.DataFrame(sleep_periods)

    return summary_df