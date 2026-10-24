"""Activity L5/M10/RA compatibility API backed by tools.nonparametric."""
from tools.nonparametric import compute_daily_L5_M10_RA

__all__ = ["compute_daily_L5_M10_RA_activity"]


def compute_daily_L5_M10_RA_activity(df, time_col="DATE/TIME", value_col="PIMn", anchor_hour=12, **kwargs):
    return compute_daily_L5_M10_RA(df, time_col=time_col, value_col=value_col, anchor_hour=anchor_hour, **kwargs)
