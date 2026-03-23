
def analyze_sleep_periods(data):
    import pandas as pd
    import numpy as np
    
    # Create a copy to avoid SettingWithCopyWarning
    data = data.copy()
    
    # =============================================================================
    # sleep state analysis
    # Calculate the rolling average for PIMn
    # min_periods=1 ensures sleep state is defined from the first sample
    data['PIMn_avg'] = data['PIMn'].rolling(window=100, min_periods=1).mean()

    # Define sleep state based on the average PIMn
    data['Sleep_State'] = data['PIMn_avg'].apply(lambda x: 1 if x < 6 else 0)

    # 1. DATA CLEANING: Fill Short Gaps in Sleep Periods
    data['DATE/TIME'] = pd.to_datetime(data['DATE/TIME'])
    data = data.sort_values("DATE/TIME").reset_index(drop=True)

    # --- Fill short sleep gaps (< 2 hours) ---
    initial_transitions = data['Sleep_State'].diff()
    wake_up_indices = initial_transitions[initial_transitions == -1].index
    sleep_onset_indices = initial_transitions[initial_transitions == 1].index
    for wake_idx in wake_up_indices:
        next_sleep_onsets = sleep_onset_indices[sleep_onset_indices > wake_idx]
        if not next_sleep_onsets.empty:
            next_sleep_idx = next_sleep_onsets[0]
            duration = data.loc[next_sleep_idx, 'DATE/TIME'] - data.loc[wake_idx, 'DATE/TIME']
            if duration < pd.Timedelta(hours=2):
                data.loc[wake_idx:next_sleep_idx-1, 'Sleep_State'] = 1

    # --- Identify the final, cleaned transitions ---
    data['sleep_transition'] = data['Sleep_State'].diff()
    transitions_df = data[data['sleep_transition'].isin([1, -1])].copy()
    transitions_df['Transition_Type'] = np.where(transitions_df['sleep_transition'] == 1,
                                                 'Sleep Onset',
                                                 'Wake-up')

    # =============================================================================
    # 2. ANALYSIS: Pair Onsets and Offsets to Create Sleep Periods
    # =============================================================================
    print("--- Pairing onsets and offsets to define sleep periods... ---")

    # Separate the onsets (sleep) and offsets (wake-up)
    onsets = transitions_df[transitions_df['Transition_Type'] == 'Sleep Onset']
    offsets = transitions_df[transitions_df['Transition_Type'] == 'Wake-up']

    sleep_periods = []

    # Iterate through each sleep onset event
    for index, onset_row in onsets.iterrows():
        onset_time = onset_row['DATE/TIME']
        
        # Find the first wake-up event that occurs *after* this sleep onset
        next_offsets = offsets[offsets['DATE/TIME'] > onset_time]
        
        # If a corresponding wake-up event exists, we have a complete sleep period
        if not next_offsets.empty:
            offset_row = next_offsets.iloc[0]
            offset_time = offset_row['DATE/TIME']
            
            # --- Calculate Mid-Sleep ---
            sleep_duration = offset_time - onset_time
            mid_sleep_time = onset_time + (sleep_duration / 2)
            
            # Store the results for this period
            period_data = {
                'Sleep_onset_DATE': onset_time.date(),
                'Sleep_onset_Time': onset_time.time(),
                'Sleep_offset_DATE': offset_time.date(),
                'Sleep_offset_TIME': offset_time.time(),
                'mid_sleep_DATE': mid_sleep_time.date(),
                'Mid_sleep_Time': mid_sleep_time.time()
            }
            sleep_periods.append(period_data)

    # =============================================================================
    # 3. REPORTING: Display the Final Sleep Period DataFrame
    # =============================================================================
    # Convert the list of dictionaries into a final DataFrame
    summary_df = pd.DataFrame(sleep_periods)

    print("\n✅ Final Sleep Period Summary Report:")
    if summary_df.empty:
        print("No complete sleep periods found.")
    else:
        print(summary_df)
    return summary_df