"""Light IS/IV compatibility API backed by tools.nonparametric."""
from tools.nonparametric import compute_rolling_2day_is_iv

__all__ = ["compute_rolling_2day_is_iv_light"]


def compute_rolling_2day_is_iv_light(df, time_col="DATE/TIME", value_col="MELANOPIC EDI", anchor_hour=12, **kwargs):
    return compute_rolling_2day_is_iv(df, time_col=time_col, value_col=value_col, anchor_hour=anchor_hour, **kwargs)
