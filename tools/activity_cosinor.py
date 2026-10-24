"""Activity cosinor compatibility API backed by fixed-period linear regression."""
from tools.cosinor import cosinor_function, fit_daily_cosinor

__all__ = ["cosinor_function", "fit_cosinor_daily_activity"]


def fit_cosinor_daily_activity(df, datetime_col="DATE/TIME", value_col="PIMn"):
    return fit_daily_cosinor(df, datetime_col=datetime_col, value_col=value_col)
