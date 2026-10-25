"""Hierarchical forecasting: reconciliation strategies.

The MVP forecasts at the lowest level (Customer x SKU) and reconciles
**bottom-up** (every level is the exact sum of its children, so numbers are
coherent across the hierarchy by construction).

A strategy interface is in place for Top-Down (historical proportions),
Middle-Out and MinT (trace minimisation) so they can be added without
touching the API or frontend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

HIERARCHY = ["company", "region", "channel", "customer", "category", "brand", "sku"]


class Reconciler(ABC):
    name: str

    @abstractmethod
    def reconcile(self, base: pd.DataFrame, history: pd.DataFrame, level: str) -> pd.DataFrame:
        """Return reconciled forecasts aggregated at ``level``.

        base:    series-level forecasts with hierarchy columns + 'date' + 'value'
        history: series-level actuals with hierarchy columns + 'date' + 'value'
        """


class BottomUp(Reconciler):
    name = "bottom_up"

    def reconcile(self, base: pd.DataFrame, history: pd.DataFrame, level: str) -> pd.DataFrame:
        return base.groupby([level, "date"], as_index=False)["value"].sum()


class TopDownHistoricalProportions(Reconciler):
    """Total forecast split by each member's share of the last 12 months."""

    name = "top_down"

    def reconcile(self, base: pd.DataFrame, history: pd.DataFrame, level: str) -> pd.DataFrame:
        total = base.groupby("date", as_index=False)["value"].sum()
        last = history["date"].max()
        recent = history[history["date"] > last - pd.DateOffset(months=12)]
        share = recent.groupby(level)["value"].sum()
        share = share / share.sum() if share.sum() else share
        rows = [
            {level: member, "date": d, "value": v * s}
            for member, s in share.items()
            for d, v in zip(total["date"], total["value"], strict=True)
        ]
        return pd.DataFrame(rows)


class MinT(Reconciler):  # pragma: no cover - roadmap
    name = "mint"

    def reconcile(self, base: pd.DataFrame, history: pd.DataFrame, level: str) -> pd.DataFrame:
        raise NotImplementedError("MinT reconciliation is on the roadmap (requires forecasts at every level).")


RECONCILERS: dict[str, Reconciler] = {r.name: r for r in (BottomUp(), TopDownHistoricalProportions())}
