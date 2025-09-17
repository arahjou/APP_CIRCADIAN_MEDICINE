
def upload_file(upload_file):
    import pandas as pd
    if upload_file is not None:
        df = pd.read_table(upload_file, skiprows=30, header=0, sep=';')
        df['DATE/TIME'] = pd.to_datetime(
            df['DATE/TIME'],
            format='%d/%m/%Y %H:%M:%S',
            errors='coerce' ,   # optional, helps catch mismatches
            utc=False
        ).dt.tz_localize('Europe/Berlin', nonexistent='shift_forward', ambiguous='NaT')

        df['DATE'] = df['DATE/TIME'].dt.date
        df['TIME'] = df['DATE/TIME'].dt.time
        df['HOUR'] = df['DATE/TIME'].dt.hour + df['DATE/TIME'].dt.minute / 60 + df['DATE/TIME'].dt.second / 3600
        # show just to 2 decimal time
        df['HOUR'] = df['HOUR'].round(2)

        # Or if DATE is string, convert column
        df['DATE'] = df['DATE'].astype(str)
        
        # Return the full dataset instead of filtering by specific dates
        df_processed = df[['DATE/TIME', 'TEMPERATURE', 'PIMn', 'TATn', 'ZCMn', 
                       'MELANOPIC EDI', 'DATE', 'TIME', 'HOUR']].copy()

        # Convert to timezone-naive before creating Period to avoid warning
        df_processed['Transition'] = df_processed['DATE/TIME'].dt.tz_convert(None).dt.to_period('D').dt.start_time
        return df_processed
    else:
        return None

def get_available_dates(df):
    """Get unique dates available in the dataframe"""
    if df is not None and 'DATE' in df.columns:
        return sorted(df['DATE'].unique().tolist())
    return []

def filter_data_by_dates(df, selected_dates):
    """Filter dataframe by selected dates"""
    if df is not None and selected_dates:
        return df[df['DATE'].isin(selected_dates)]
    return df