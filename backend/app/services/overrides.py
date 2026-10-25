"""Commercial overrides (consensus inputs) and the Event Library."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import pandas as pd

from app import db
from app.services import context, datasets

EVENT_LIBRARY = [
    {"type": "Promotion", "direction": "up", "typical_uplift": 0.25, "description": "Price promotion / leaflet"},
    {
        "type": "Merchandising",
        "direction": "up",
        "typical_uplift": 0.12,
        "description": "Displays, end-caps, extra facings",
    },
    {
        "type": "Distribution Gain",
        "direction": "up",
        "typical_uplift": 0.10,
        "description": "New listings / more stores",
    },
    {"type": "Distribution Loss", "direction": "down", "typical_uplift": -0.10, "description": "Lost listings"},
    {"type": "New Store", "direction": "up", "typical_uplift": 0.08, "description": "Customer opens new stores"},
    {"type": "Customer Gain", "direction": "up", "typical_uplift": 0.15, "description": "New customer / contract"},
    {"type": "Customer Loss", "direction": "down", "typical_uplift": -0.15, "description": "Customer reduces or exits"},
    {"type": "Campaign", "direction": "up", "typical_uplift": 0.10, "description": "Media / marketing campaign"},
    {
        "type": "Price Change",
        "direction": "both",
        "typical_uplift": -0.05,
        "description": "List price increase/decrease",
    },
    {"type": "New Product", "direction": "up", "typical_uplift": 0.20, "description": "Launch / line extension"},
    {
        "type": "Delisting",
        "direction": "down",
        "typical_uplift": -1.0,
        "description": "Product removed from assortment",
    },
    {
        "type": "Competitor Action",
        "direction": "both",
        "typical_uplift": -0.08,
        "description": "Competitor promo / launch",
    },
]
EVENT_TYPES = {e["type"] for e in EVENT_LIBRARY}


class OverrideError(ValueError):
    pass


def _validate(payload: dict[str, Any], ctx: context.PlanningContext) -> dict[str, Any]:
    ev = payload.get("event_type")
    if ev not in EVENT_TYPES:
        raise OverrideError(f"event_type must be one of: {', '.join(sorted(EVENT_TYPES))}")
    try:
        uplift = float(payload.get("uplift_pct"))
    except (TypeError, ValueError) as exc:
        raise OverrideError("uplift_pct must be a number (e.g. 0.15 for +15%)") from exc
    if not -1.0 <= uplift <= 5.0:
        raise OverrideError("uplift_pct must be between -100% and +500%")
    date = pd.Timestamp(payload.get("date")).to_period("M").to_timestamp()
    if len(ctx.future_dates) and date not in set(ctx.future_dates):
        raise OverrideError("The override month must be inside the forecast horizon")
    cust = payload.get("customer") or None
    sku = payload.get("sku") or None
    if cust and cust not in set(ctx.series["customer"]):
        raise OverrideError(f"Unknown customer '{cust}'")
    if sku and sku not in set(ctx.series["sku"]):
        raise OverrideError(f"Unknown SKU '{sku}'")
    if cust and sku and not ((ctx.series["customer"] == cust) & (ctx.series["sku"] == sku)).any():
        raise OverrideError(f"{cust} does not carry {sku}")
    return {
        "customer": cust,
        "sku": sku,
        "date": date,
        "event_type": ev,
        "uplift_pct": uplift,
        "comment": (payload.get("comment") or "").strip()[:500],
        "created_by": (payload.get("created_by") or "Demand Planner").strip()[:80],
    }


def list_overrides() -> list[dict[str, Any]]:
    ctx = context.get_context()
    df = ctx.overrides
    if df.empty:
        return []
    out = []
    f = ctx.forecast
    for o in df.itertuples():
        mask = f["date"] == o.date
        if isinstance(o.customer, str) and o.customer:
            mask &= f["series_id"].str.startswith(o.customer + "|")
        if isinstance(o.sku, str) and o.sku:
            mask &= f["series_id"].str.endswith("|" + o.sku)
        base = float(f.loc[mask, "p50"].sum())
        out.append(
            context.clean(
                {
                    **o._asdict(),
                    "affected_series": int(mask.sum()),
                    "base_units": base,
                    "incremental_units": base * float(o.uplift_pct),
                }
            )
        )
    for o in out:
        o.pop("Index", None)
    return out


def create_override(payload: dict[str, Any]) -> dict[str, Any]:
    ctx = context.get_context()
    v = _validate(payload, ctx)
    row = {
        "override_id": f"OVR-{uuid.uuid4().hex[:8].upper()}",
        "dataset_version": datasets.active_version(),
        **v,
        "created_at": datetime.now(),
    }
    db.insert_df("overrides", pd.DataFrame([row]))
    context.bump_overrides()
    return context.clean(row)


def update_override(override_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    ctx = context.get_context()
    v = _validate(payload, ctx)
    exists = db.scalar("SELECT 1 FROM overrides WHERE override_id = ?", [override_id])
    if not exists:
        raise KeyError(override_id)
    db.execute(
        "UPDATE overrides SET customer=?, sku=?, date=?, event_type=?, uplift_pct=?, comment=?, created_by=? "
        "WHERE override_id=?",
        [
            v["customer"],
            v["sku"],
            v["date"],
            v["event_type"],
            v["uplift_pct"],
            v["comment"],
            v["created_by"],
            override_id,
        ],
    )
    context.bump_overrides()
    return context.clean({"override_id": override_id, **v})


def delete_override(override_id: str) -> None:
    if not db.scalar("SELECT 1 FROM overrides WHERE override_id = ?", [override_id]):
        raise KeyError(override_id)
    db.execute("DELETE FROM overrides WHERE override_id = ?", [override_id])
    context.bump_overrides()
