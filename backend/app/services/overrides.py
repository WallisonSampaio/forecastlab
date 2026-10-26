"""Commercial overrides (consensus inputs) and the Event Library."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import pandas as pd

from app import db
from app.services import context, datasets
from app.services.ptbr import EVENT_TYPE, PLANNER

EVENT_LIBRARY = [
    {
        "type": "Promoção",
        "direction": "up",
        "typical_uplift": 0.25,
        "description": "Promoção de preço / encarte",
    },
    {
        "type": "Merchandising",
        "direction": "up",
        "typical_uplift": 0.12,
        "description": "Displays, pontas de gôndola e frentes extras",
    },
    {
        "type": "Ganho de distribuição",
        "direction": "up",
        "typical_uplift": 0.10,
        "description": "Novas listagens / mais lojas atendidas",
    },
    {
        "type": "Perda de distribuição",
        "direction": "down",
        "typical_uplift": -0.10,
        "description": "Perda de listagens",
    },
    {
        "type": "Nova loja",
        "direction": "up",
        "typical_uplift": 0.08,
        "description": "Cliente abre novas lojas",
    },
    {
        "type": "Ganho de cliente",
        "direction": "up",
        "typical_uplift": 0.15,
        "description": "Novo cliente / novo contrato",
    },
    {
        "type": "Perda de cliente",
        "direction": "down",
        "typical_uplift": -0.15,
        "description": "Cliente reduz compras ou encerra a parceria",
    },
    {
        "type": "Campanha",
        "direction": "up",
        "typical_uplift": 0.10,
        "description": "Campanha de mídia / marketing",
    },
    {
        "type": "Mudança de preço",
        "direction": "both",
        "typical_uplift": -0.05,
        "description": "Aumento ou redução do preço de tabela",
    },
    {
        "type": "Lançamento",
        "direction": "up",
        "typical_uplift": 0.20,
        "description": "Lançamento de produto / extensão de linha",
    },
    {
        "type": "Deslistagem",
        "direction": "down",
        "typical_uplift": -1.0,
        "description": "Produto retirado do sortimento",
    },
    {
        "type": "Ação de concorrente",
        "direction": "both",
        "typical_uplift": -0.08,
        "description": "Promoção ou lançamento da concorrência",
    },
]
EVENT_TYPES = {e["type"] for e in EVENT_LIBRARY}

# Event types / planners written by older (English) versions -> current Portuguese value. Overrides
# saved with a legacy value keep displaying as they are and are normalised the next time they are edited.
LEGACY_EVENT_TYPES = EVENT_TYPE
LEGACY_PLANNERS = PLANNER
DEFAULT_PLANNER = "Planejador de Demanda"


class OverrideError(ValueError):
    pass


def _validate(payload: dict[str, Any], ctx: context.PlanningContext) -> dict[str, Any]:
    ev = payload.get("event_type")
    ev = LEGACY_EVENT_TYPES.get(ev, ev)
    if ev not in EVENT_TYPES:
        types = ", ".join(e["type"] for e in EVENT_LIBRARY)
        raise OverrideError(f"Tipo de evento inválido. Use um destes: {types}")
    try:
        uplift = float(payload.get("uplift_pct"))
    except (TypeError, ValueError) as exc:
        raise OverrideError("O ajuste deve ser um número (ex.: 0,15 para +15%)") from exc
    if not -1.0 <= uplift <= 5.0:
        raise OverrideError("O ajuste deve ficar entre -100% e +500%")
    try:
        date = pd.Timestamp(payload.get("date")).to_period("M").to_timestamp()
    except (TypeError, ValueError, AttributeError) as exc:
        raise OverrideError("Mês do ajuste inválido (use o formato AAAA-MM-DD)") from exc
    if len(ctx.future_dates) and date not in set(ctx.future_dates):
        raise OverrideError("O mês do ajuste precisa estar dentro do horizonte do forecast")
    cust = payload.get("customer") or None
    sku = payload.get("sku") or None
    if cust and cust not in set(ctx.series["customer"]):
        raise OverrideError(f"Cliente desconhecido: '{cust}'")
    if sku and sku not in set(ctx.series["sku"]):
        raise OverrideError(f"SKU desconhecido: '{sku}'")
    if cust and sku and not ((ctx.series["customer"] == cust) & (ctx.series["sku"] == sku)).any():
        raise OverrideError(f"O cliente {cust} não trabalha o SKU {sku}")
    planner = (payload.get("created_by") or DEFAULT_PLANNER).strip()[:80]
    return {
        "customer": cust,
        "sku": sku,
        "date": date,
        "event_type": ev,
        "uplift_pct": uplift,
        "comment": (payload.get("comment") or "").strip()[:500],
        "created_by": LEGACY_PLANNERS.get(planner, planner),
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
        # legacy English values (older databases) are shown with the current Portuguese label
        if isinstance(o.get("event_type"), str):
            o["event_type"] = LEGACY_EVENT_TYPES.get(o["event_type"], o["event_type"])
        if isinstance(o.get("created_by"), str):
            o["created_by"] = LEGACY_PLANNERS.get(o["created_by"], o["created_by"])
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
