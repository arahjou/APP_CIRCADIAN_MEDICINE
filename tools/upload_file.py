
def upload_file(upload_file):
    import pandas as pd
    if upload_file is not None:
        # Read raw bytes once to auto-detect format
        raw_bytes = upload_file.read()
        upload_file.seek(0)
        try:
            text = raw_bytes.decode('utf-8')
        except UnicodeDecodeError:
            text = raw_bytes.decode('latin-1')

        lines = text.splitlines()

        # Find the header row by locating 'DATE/TIME'
        skiprows = 0
        sep = ','
        for i, line in enumerate(lines[:50]):
            if 'DATE/TIME' in line:
                skiprows = i
                sep = ';' if ';' in line else ','
                break

        upload_file.seek(0)
        df = pd.read_table(upload_file, skiprows=skiprows, header=0, sep=sep)

        # Normalise column names: replace dots with spaces
        # (some exports use 'MELANOPIC.EDI' instead of 'MELANOPIC EDI')
        df.columns = [c.replace('.', ' ') for c in df.columns]

        # Auto-detect date format: DD/MM/YYYY vs YYYY-MM-DD
        sample = str(df['DATE/TIME'].dropna().iloc[0]) if not df['DATE/TIME'].dropna().empty else ''
        date_format = '%d/%m/%Y %H:%M:%S' if '/' in sample else '%Y-%m-%d %H:%M:%S'

        df['DATE/TIME'] = pd.to_datetime(
            df['DATE/TIME'],
            format=date_format,
            errors='coerce',
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