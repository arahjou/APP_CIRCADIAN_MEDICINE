def plotter_light(df_subset):
    import matplotlib.pyplot as plt
    import numpy as np

    df_subset['MELANOPIC EDI_avg'] = df_subset['MELANOPIC EDI'].rolling(window=50).mean()

    # lighting_condition if MELANOPIC EDI
    # 0, less than 1
    # 1, between 1 and 10
    # 2, between 10 and 250
    # 3, greater than 250

    df_subset['lighting_condition'] = np.where(df_subset['MELANOPIC EDI_avg'] < 1, 0,
        np.where(df_subset['MELANOPIC EDI_avg'] < 10, 1,
        np.where(df_subset['MELANOPIC EDI_avg'] < 250, 2, 3)))

    plt.figure(figsize=(12, 6), dpi=200)
    plt.plot(df_subset['DATE/TIME'], df_subset['MELANOPIC EDI'], label='MELANOPIC EDI', color='orange')
    plt.plot(df_subset['DATE/TIME'], df_subset['MELANOPIC EDI_avg'], label='MELANOPIC EDI (50min Rolling Avg)', color='Black')
    plt.fill_between(df_subset['DATE/TIME'], 0, df_subset['MELANOPIC EDI'].max(), where=df_subset['lighting_condition'] == 0, color='blue', alpha=0.3, label='Very Dim (<1)')
    plt.fill_between(df_subset['DATE/TIME'], 1, df_subset['MELANOPIC EDI'].max(), where=df_subset['lighting_condition'] == 1, color='cyan', alpha=0.3, label='Dim (1-10)')
    plt.fill_between(df_subset['DATE/TIME'], 2, df_subset['MELANOPIC EDI'].max(), where=df_subset['lighting_condition'] == 2, color='lime', alpha=0.3, label='Bright (10-250)')
    plt.fill_between(df_subset['DATE/TIME'], 3, df_subset['MELANOPIC EDI'].max(), where=df_subset['lighting_condition'] == 3, color='red', alpha=0.3, label='Very Bright (>250)')
    plt.xlabel('Hour of Day')
    plt.ylabel('Average of \nMelanopic EDI')
    plt.title('Time Series Data')
    plt.legend()
    plt.grid()
    
    # Return the current figure instead of the plt module
    return plt.gcf()