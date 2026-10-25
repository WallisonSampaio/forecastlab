"""Baseline driver assumptions for any forecast window.

Used identically for the backtest test windows and for the real future, so
backtest accuracy is an honest *ex-ante* estimate: the model never sees the
promotions, prices or distribution that actually happened in the window it
is forecasting. Only the deterministic calendar (month, holidays) is known.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def baseline_design(X_hist: pd.DataFrame, calendar: pd.DataFrame) -> pd.DataFrame:
    """Business-as-usual driver assumptions.

    * price          -> median regular (non-promo) price of the last 6 months
    * distribution   -> last observed value
    * marketing      -> median of the last 12 months
    * promotion / merchandising -> usual intensity (share of promoted months in
      the last 12 months), i.e. the expected value when the calendar is unknown.
      Extra commercial events are layered on top as overrides / scenarios.
    """
    Xf = calendar.copy()
    for c in X_hist.columns:
        if c in Xf.columns or c in ("t", "month"):
            continue
        col = X_hist[c].to_numpy(float)
        if c in ("promotion", "merchandising_event"):
            Xf[c] = float(np.mean(col[-12:])) if col.size else 0.0
        elif c == "price":
            recent = X_hist.tail(6)
            if "promotion" in recent:
                regular = recent.loc[recent["promotion"] == 0, "price"]
            else:
                regular = recent["price"]
            Xf[c] = float(regular.median() if regular.size else recent["price"].median())
        elif c == "distribution":
            Xf[c] = float(col[-1]) if col.size else 0.0
        elif c == "marketing_investment":
            Xf[c] = float(np.median(col[-12:])) if col.size else 0.0
        else:
            Xf[c] = float(col[-1]) if col.size else 0.0
    return Xf[list(X_hist.columns)] if set(X_hist.columns) <= set(Xf.columns) else Xf
