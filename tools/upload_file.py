"""Compatibility helpers for the normalized recording importer."""
from tools.recording import ImportOptions, import_recording


def upload_file(upload_file, *, timezone="Europe/Berlin", date_order="dayfirst", column_map=None):
    if upload_file is None:
        return None
    return import_recording(upload_file, ImportOptions(
        timezone=timezone, date_order=date_order, column_map=column_map or {},
    )).data


def get_available_dates(df):
    if df is not None and "DATE" in df.columns:
        return sorted(df["DATE"].dropna().unique().tolist())
    return []


def filter_data_by_dates(df, selected_dates):
    if df is not None and selected_dates:
        return df[df["DATE"].isin(selected_dates)].copy()
    return df
