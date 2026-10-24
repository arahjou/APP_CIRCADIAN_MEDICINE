"""Light L5/M10/RA compatibility API backed by tools.nonparametric."""
from tools.nonparametric import compute_daily_L5_M10_RA

__all__ = ["compute_daily_L5_M10_RA_light"]


def compute_daily_L5_M10_RA_light(df, time_col="DATE/TIME", value_col="MELANOPIC EDI", anchor_hour=12, **kwargs):
    return compute_daily_L5_M10_RA(df, time_col=time_col, value_col=value_col, anchor_hour=anchor_hour, **kwargs)
