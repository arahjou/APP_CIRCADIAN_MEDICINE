def activity_plotter(df_subset):
    import matplotlib.pyplot as plt
    import pandas as pd

    # Work on a copy to avoid mutating the caller's DataFrame
    df_subset = df_subset.copy()

    # Calculate the rolling average for PIMn (min_periods=1 avoids NaN at start)
    df_subset['PIMn_avg'] = df_subset['PIMn'].rolling(window=100, min_periods=1).mean()

    # Use externally provided sleep labels when available (Roenneberg/editor output).
    # Fallback to heuristic only if SLEEP_STATE is missing.
    if 'SLEEP_STATE' in df_subset.columns:
        df_subset['Sleep_State'] = pd.to_numeric(df_subset['SLEEP_STATE'], errors='coerce').fillna(0).clip(0, 1).astype(int)
    else:
        df_subset['Sleep_State'] = df_subset['PIMn_avg'].apply(lambda x: 1 if x < 6 else 0)

    plt.figure(figsize=(12, 6), dpi=200)
    plt.plot(df_subset['DATE/TIME'], df_subset['PIMn'], label='PIMn', color = "black")
    plt.plot(df_subset['DATE/TIME'], df_subset['PIMn_avg'], label='PIMn Avg', color = "red")
    plt.fill_between(df_subset['DATE/TIME'], 0, df_subset['PIMn'].max(), where=df_subset['Sleep_State'] == 1, color='blue', alpha=0.3, label='Sleep State')
    plt.fill_between(df_subset['DATE/TIME'], 0, df_subset['PIMn'].max(), where=df_subset['Sleep_State'] == 0, color='orange', alpha=0.3, label='Awake State')
    plt.axhline(y=6, color='purple', linestyle='--')

    # Add vertical lines at midnight for each day
    unique_dates = pd.to_datetime(df_subset['DATE']).dt.date.unique()
    for i, date in enumerate(sorted(unique_dates)):
        # Add a line for each day except the first one
        if i > 0:
            plt.axvline(x=pd.to_datetime(date), color='red', linestyle='--', label='Midnight' if i == 1 else "")


    plt.xlabel('Date and Time')
    plt.ylabel('Values')
    plt.title('Time Series Data with Sleep State')
    plt.legend()
    plt.grid()
    
    # Return the current figure instead of the plt module
    return plt.gcf()