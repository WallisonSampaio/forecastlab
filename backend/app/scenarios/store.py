"""Scenario persistence (create, duplicate, edit, compare, delete) and presets."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import pandas as pd

from app import db
from app.services.context import PlanningContext, clean

from .engine import ScenarioParams, simulate_rows, summarize


def _peak_months(ctx: PlanningContext, n: int) -> list[str]:
    """Months with the highest base demand in the horizon (where promos pay off most)."""
    if not ctx.has_run:
        return []
    m = ctx.forecast.groupby("date")["p50"].sum().sort_values(ascending=False)
    return [d.strftime("%Y-%m-01") for d in sorted(m.index[:n])]


def preset_params(ctx: PlanningContext) -> dict[str, dict[str, Any]]:
    return {
        "Base": {
            "description": "Statistical forecast plus approved commercial overrides (consensus).",
            "kind": "base",
            "params": ScenarioParams().as_dict(),
        },
        "Conservative": {
            "description": "Price pass-through, slight distribution loss, lower marketing and a softer market.",
            "kind": "conservative",
            "params": ScenarioParams(
                price_change_pct=0.02,
                distribution_change_pct=-0.03,
                marketing_change_pct=-0.10,
                customer_growth_pct=-0.02,
                market_growth_pct=-0.015,
            ).as_dict(),
        },
        "Aggressive": {
            "description": "Commercial expansion: +6% distribution, promotions in the 2 peak months, merchandising, "
            "+15% marketing and a sharper price.",
            "kind": "aggressive",
            "params": ScenarioParams(
                price_change_pct=-0.02,
                distribution_change_pct=0.06,
                promo_months=_peak_months(ctx, 2),
                merch_months=_peak_months(ctx, 1),
                marketing_change_pct=0.15,
                customer_growth_pct=0.02,
                market_growth_pct=0.01,
            ).as_dict(),
        },
    }


def ensure_presets(ctx: PlanningContext) -> None:
    existing = set(db.query_df("SELECT name FROM scenarios")["name"])
    now = datetime.now()
    for name, p in preset_params(ctx).items():
        if name in existing:
            continue
        db.insert_df(
            "scenarios",
            pd.DataFrame(
                [
                    {
                        "scenario_id": f"SCN-{name.upper()}",
                        "name": name,
                        "kind": p["kind"],
                        "description": p["description"],
                        "params_json": json.dumps(p["params"]),
                        "is_system": name == "Base",
                        "created_at": now,
                        "updated_at": now,
                    }
                ]
            ),
        )


def refresh_presets(ctx: PlanningContext) -> None:
    """Re-anchor preset promo months to the current horizon (after a new run)."""
    for name, p in preset_params(ctx).items():
        db.execute(
            "UPDATE scenarios SET params_json = ? WHERE scenario_id = ?",
            [json.dumps(p["params"]), f"SCN-{name.upper()}"],
        )


def list_scenarios() -> list[dict[str, Any]]:
    df = db.query_df("SELECT * FROM scenarios ORDER BY is_system DESC, created_at")
    order = {"base": 0, "conservative": 1, "aggressive": 2}
    rows = []
    for r in df.to_dict("records"):
        r["params"] = json.loads(r.pop("params_json") or "{}")
        rows.append(clean(r))
    return sorted(rows, key=lambda r: (order.get(r["kind"], 9), r["created_at"] or ""))


def get_scenario(scenario_id: str) -> dict[str, Any]:
    df = db.query_df("SELECT * FROM scenarios WHERE scenario_id = ?", [scenario_id])
    if df.empty:
        raise KeyError(scenario_id)
    r = df.iloc[0].to_dict()
    r["params"] = json.loads(r.pop("params_json") or "{}")
    return clean(r)


def create_scenario(name: str, description: str, params: dict[str, Any], kind: str = "custom") -> dict[str, Any]:
    p = ScenarioParams.from_dict(params)
    sid = f"SCN-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now()
    db.insert_df(
        "scenarios",
        pd.DataFrame(
            [
                {
                    "scenario_id": sid,
                    "name": (name or "Custom scenario").strip()[:80],
                    "kind": kind,
                    "description": (description or "").strip()[:400],
                    "params_json": json.dumps(p.as_dict()),
                    "is_system": False,
                    "created_at": now,
                    "updated_at": now,
                }
            ]
        ),
    )
    return get_scenario(sid)


def update_scenario(
    scenario_id: str, name: str | None, description: str | None, params: dict[str, Any] | None
) -> dict[str, Any]:
    cur = get_scenario(scenario_id)
    if cur["is_system"] and params is not None and ScenarioParams.from_dict(params).as_dict() != cur["params"]:
        raise PermissionError("The Base scenario is the statistical/consensus reference and cannot be edited.")
    p = ScenarioParams.from_dict(params if params is not None else cur["params"])
    db.execute(
        "UPDATE scenarios SET name=?, description=?, params_json=?, updated_at=? WHERE scenario_id=?",
        [
            (name or cur["name"]).strip()[:80],
            (description if description is not None else cur["description"]),
            json.dumps(p.as_dict()),
            datetime.now(),
            scenario_id,
        ],
    )
    return get_scenario(scenario_id)


def duplicate_scenario(scenario_id: str) -> dict[str, Any]:
    cur = get_scenario(scenario_id)
    return create_scenario(f"{cur['name']} (copy)", cur.get("description") or "", cur["params"])


def delete_scenario(scenario_id: str) -> None:
    cur = get_scenario(scenario_id)
    if cur["is_system"]:
        raise PermissionError("The Base scenario cannot be deleted.")
    db.execute("DELETE FROM scenarios WHERE scenario_id = ?", [scenario_id])


def compare(
    ctx: PlanningContext, scenario_ids: list[str] | None, filters: dict[str, Any] | None, measure: str = "revenue"
) -> dict[str, Any]:
    scenarios = list_scenarios()
    if scenario_ids:
        scenarios = [s for s in scenarios if s["scenario_id"] in scenario_ids]
    results = []
    base_total = None
    for s in scenarios:
        summary = summarize(ctx, simulate_rows(ctx, ScenarioParams.from_dict(s["params"])), filters)
        t = summary["totals"]
        if s["kind"] == "base":
            base_total = t
        results.append({"scenario": s, "totals": t, "monthly": summary["monthly"], "drivers": summary["drivers"]})
    rows = []
    for r in results:
        t = r["totals"]
        b = base_total or t
        rows.append(
            clean(
                {
                    "scenario_id": r["scenario"]["scenario_id"],
                    "name": r["scenario"]["name"],
                    "kind": r["scenario"]["kind"],
                    "units": t.get("units"),
                    "revenue": t.get("revenue"),
                    "vs_base_units": (t["units"] / b["units"] - 1) if b.get("units") else None,
                    "vs_base_revenue": (t["revenue"] / b["revenue"] - 1) if b.get("revenue") else None,
                    "vs_budget_units": t.get("vs_budget_units"),
                    "vs_budget_revenue": t.get("vs_budget_revenue"),
                    "vs_target_units": t.get("vs_target_units"),
                    "vs_target_revenue": t.get("vs_target_revenue"),
                    "budget_units": t.get("budget_units"),
                    "budget_revenue": t.get("budget_revenue"),
                    "target_units": t.get("target_units"),
                    "target_revenue": t.get("target_revenue"),
                }
            )
        )
    return {
        "rows": rows,
        "series": [
            {
                "scenario_id": r["scenario"]["scenario_id"],
                "name": r["scenario"]["name"],
                "monthly": r["monthly"],
                "drivers": r["drivers"],
            }
            for r in results
        ],
        "measure": measure,
    }
