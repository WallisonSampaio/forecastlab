"""Camada semântica: catálogo governado de métricas e dimensões + um pequeno motor de consulta.

O Analista de IA nunca escreve SQL livre. Ele traduz a pergunta em uma requisição
(métrica, dimensão, filtros, período) que esta camada executa de forma determinística
sobre os dados no DuckDB. Chaves e códigos ficam em inglês; rótulos e descrições em pt-BR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.services.context import PlanningContext, filter_ids

METRICS: dict[str, dict[str, Any]] = {
    "actual": {
        "label": "Real",
        "format": "measure",
        "description": "Vendas históricas (sell-in), em unidades ou receita.",
    },
    "forecast": {
        "label": "Forecast estatístico",
        "format": "measure",
        "description": "Forecast base do modelo Campeão (P50), antes dos ajustes comerciais.",
    },
    "consensus": {
        "label": "Forecast de consenso",
        "format": "measure",
        "description": "Forecast estatístico + ajustes comerciais (demanda incremental).",
    },
    "budget": {"label": "Orçamento", "format": "measure", "description": "Orçamento anual (plano financeiro)."},
    "target": {"label": "Meta", "format": "measure", "description": "Meta comercial de vendas."},
    "wmape": {
        "label": "WMAPE",
        "format": "percent",
        "description": "MAPE ponderado = soma|F-R| / soma|R| no backtest com origem móvel (quanto menor, melhor).",
    },
    "accuracy": {"label": "Acurácia", "format": "percent", "description": "1 - WMAPE (mínimo de 0)."},
    "bias": {
        "label": "Viés",
        "format": "percent",
        "description": "soma(F-R) / soma(R). Positivo = superestimado; negativo = subestimado.",
    },
    "gap_vs_budget": {"label": "Gap vs orçamento", "format": "measure", "description": "Consenso - Orçamento."},
    "gap_vs_target": {"label": "Gap vs meta", "format": "measure", "description": "Consenso - Meta."},
    "uplift": {
        "label": "Incremental (eventos)",
        "format": "measure",
        "description": "Consenso - Estatístico: demanda adicionada pelos eventos comerciais.",
    },
    "fva": {
        "label": "FVA (valor agregado ao forecast)",
        "format": "percent",
        "description": "WMAPE(estatístico) - WMAPE(consenso) nas células com ajuste comercial.",
    },
    "distribution": {
        "label": "Distribuição numérica",
        "format": "number",
        "description": "% das lojas que listam o SKU.",
    },
    "price": {"label": "Preço líquido médio", "format": "currency", "description": "Receita / Unidades."},
    "p10": {"label": "P10", "format": "measure", "description": "Quantil pessimista do forecast."},
    "p90": {"label": "P90", "format": "measure", "description": "Quantil otimista do forecast."},
}

DIMENSIONS: dict[str, dict[str, str]] = {
    "period": {"label": "Mês", "column": "date"},
    "region": {"label": "Região", "column": "region"},
    "channel": {"label": "Canal", "column": "channel"},
    "customer": {"label": "Cliente", "column": "customer"},
    "category": {"label": "Categoria", "column": "category"},
    "brand": {"label": "Marca", "column": "brand"},
    "sku": {"label": "SKU", "column": "sku"},
    "model": {"label": "Modelo", "column": "champion"},
    "scenario": {"label": "Cenário", "column": "scenario"},
}


@dataclass
class SemanticQuery:
    metric: str
    by: str = "sku"
    filters: dict[str, Any] = field(default_factory=dict)
    months: list[str] = field(default_factory=list)
    measure: str = "revenue"
    order: str = "desc"
    limit: int = 10

    def describe(self) -> str:
        where = " AND ".join(f"{k} = '{v}'" for k, v in self.filters.items() if v) or "todos"
        period = f" PERIOD {', '.join(self.months)}" if self.months else ""
        return (
            f"SELECT {self.metric}({self.measure}) BY {self.by} WHERE {where}{period} "
            f"ORDER BY {self.metric} {self.order.upper()} LIMIT {self.limit}"
        )


def run_query(ctx: PlanningContext, q: SemanticQuery) -> pd.DataFrame:
    """Executa uma consulta semântica; retorna as colunas [member, value, volume, ...]."""
    if q.metric not in METRICS:
        raise ValueError(f"Métrica desconhecida: '{q.metric}'")
    if q.by not in DIMENSIONS:
        raise ValueError(f"Dimensão desconhecida: '{q.by}'")
    ids = filter_ids(ctx, q.filters)
    col = DIMENSIONS[q.by]["column"]
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    months = pd.DatetimeIndex([pd.Timestamp(m) for m in q.months]) if q.months else None

    if q.metric in ("wmape", "accuracy", "bias"):
        bt = ctx.backtest[ctx.backtest["series_id"].isin(ids)].merge(s[["series_id", col]], on="series_id")
        if months is not None:
            bt = bt[bt["date"].isin(months)]
        bt = bt.assign(ae=(bt["forecast"] - bt["actual"]).abs(), e=bt["forecast"] - bt["actual"])
        g = bt.groupby(col)
        denom = g["actual"].sum().replace(0, np.nan)
        df = pd.DataFrame({"wmape": g["ae"].sum() / denom, "bias": g["e"].sum() / denom, "volume": g["actual"].sum()})
        df["accuracy"] = (1 - df["wmape"]).clip(lower=0)
        df["value"] = df[q.metric]
        df["series"] = s.groupby(col)["series_id"].count()
    elif q.metric in (
        "forecast",
        "consensus",
        "uplift",
        "p10",
        "p90",
        "gap_vs_budget",
        "gap_vs_target",
        "budget",
        "target",
    ):
        months = months if months is not None else ctx.future_dates
        f = ctx.forecast[ctx.forecast["series_id"].isin(ids) & ctx.forecast["date"].isin(months)]
        f = f.merge(s[["series_id", col]], on="series_id")
        k = f["price"] if q.measure == "revenue" else 1.0
        f = f.assign(
            forecast=f["p50"] * k,
            consensus=f["consensus"] * k,
            uplift=f["incremental"] * k,
            p10=f["p10"] * k,
            p90=f["p90"] * k,
        )
        df = f.groupby(col)[["forecast", "consensus", "uplift", "p10", "p90"]].sum()
        if not ctx.plan.empty:
            bc, tc = (
                ("budget_revenue", "target_revenue") if q.measure == "revenue" else ("budget_units", "target_units")
            )
            p = ctx.plan[ctx.plan["series_id"].isin(ids) & ctx.plan["date"].isin(months)].merge(
                s[["series_id", col]], on="series_id"
            )
            df["budget"] = p.groupby(col)[bc].sum()
            df["target"] = p.groupby(col)[tc].sum()
            df["gap_vs_budget"] = df["consensus"] - df["budget"]
            df["gap_vs_target"] = df["consensus"] - df["target"]
        df["value"] = df[q.metric]
        df["volume"] = df["consensus"]
    elif q.metric in ("actual", "price", "distribution"):
        a = ctx.actuals[ctx.actuals["series_id"].isin(ids)]
        a = a[a["date"].isin(months if months is not None else ctx.ltm_dates)].merge(
            s[["series_id", col]], on="series_id"
        )
        g = a.groupby(col)
        df = pd.DataFrame(
            {"units": g["units"].sum(), "revenue": g["revenue"].sum(), "distribution": g["distribution"].mean()}
        )
        df["price"] = df["revenue"] / df["units"].replace(0, np.nan)
        df["actual"] = df["revenue"] if q.measure == "revenue" else df["units"]
        df["value"] = df[q.metric]
        df["volume"] = df["actual"]
    else:
        raise ValueError(f"A métrica '{q.metric}' não pode ser consultada por dimensão")
    df = df.dropna(subset=["value"])
    df = df.sort_values("value", ascending=q.order == "asc")
    df.index.name = "member"
    return df.reset_index().head(q.limit)


def catalog() -> dict[str, Any]:
    return {"metrics": METRICS, "dimensions": DIMENSIONS}
