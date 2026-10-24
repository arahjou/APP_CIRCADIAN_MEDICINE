"""Activity IS/IV compatibility API backed by tools.nonparametric."""
from tools.nonparametric import compute_rolling_2day_is_iv

__all__ = ["compute_rolling_2day_is_iv_activity"]


def compute_rolling_2day_is_iv_activity(df, time_col="DATE/TIME", value_col="PIMn", anchor_hour=12, **kwargs):
    return compute_rolling_2day_is_iv(df, time_col=time_col, value_col=value_col, anchor_hour=anchor_hour, **kwargs)
