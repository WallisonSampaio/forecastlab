"""Brazilian Portuguese (pt-BR) number formatting and display labels for backend texts.

Internal codes (series types, model names, classifications ...) stay in English in
the data; these helpers only translate them when they are written into messages.
"""

from __future__ import annotations

import math
from typing import Any

NA = "n/d"

APP_TAGLINE = "Planejamento de Demanda com IA e Inteligência de Decisão para S&OP"

SERIES_TYPE = {
    "Stable": "Estável",
    "Trending": "Crescente",
    "Declining": "Em declínio",
    "Seasonal": "Sazonal",
    "Intermittent": "Intermitente",
    "Promo Driven": "Dirigida por promoção",
    "Distribution Driven": "Dirigida por distribuição",
    "Structural Change": "Mudança estrutural",
    "Volatile": "Volátil",
    "Short History": "Histórico curto",
    "Inactive": "Inativa",
}

MODEL = {
    "Naive": "Ingênuo",
    "Seasonal Naive": "Ingênuo sazonal",
    "Moving Average": "Média Móvel",
    "Regression": "Regressão",
}

CLASSIFICATION = {
    "REALISTIC": "Realista",
    "STRETCH": "Desafiadora",
    "AGGRESSIVE": "Agressiva",
    "UNDERESTIMATED": "Subestimada",
}

BIAS_CLASS = {"Under": "Subestimado", "Balanced": "Equilibrado", "Over": "Superestimado"}

CONFIDENCE = {"High": "Alta", "Medium": "Média", "Low": "Baixa"}

SEVERITY = {"critical": "Crítico", "high": "Alto", "medium": "Médio", "low": "Baixo"}

DIMENSION = {
    "company": "Empresa",
    "region": "Região",
    "channel": "Canal",
    "customer": "Cliente",
    "category": "Categoria",
    "brand": "Marca",
    "sku": "SKU",
}

FAMILY = {
    "Baseline": "Linha de base",
    "Exponential Smoothing": "Suavização exponencial",
    "ARIMA": "ARIMA",
    "Intermittent": "Demanda intermitente",
    "Regression": "Regressão",
    "Machine Learning": "Machine Learning",
}

MODEL_DESCRIPTION = {
    "Naive": "Repete o último valor observado.",
    "Seasonal Naive": "Repete o mesmo mês do ano anterior.",
    "Moving Average": "Média dos últimos k meses.",
    "SES": "Suavização exponencial simples (apenas nível).",
    "Holt": "Método de Holt com tendência linear amortecida.",
    "Holt-Winters": "Tendência amortecida aditiva com sazonalidade aditiva ou multiplicativa.",
    "ETS": "ETS automático: melhor combinação de tendência e sazonalidade pelo AICc, depois refinada.",
    "ARIMA": "ARIMA(1,1,1); inclui drift quando a variação média é significativa (|t| > 2).",
    "SARIMA": "Modelo sazonal 'airline' SARIMA(0,1,1)(0,1,1)12 em escala logarítmica.",
    "Croston": "Método de Croston: suavização separada do tamanho da demanda e do intervalo entre pedidos.",
    "SBA": "Aproximação de Syntetos-Boylan (Croston com correção de viés).",
    "TSB": "Teunter-Syntetos-Babai: suaviza a probabilidade de demanda a cada período (trata obsolescência).",
    "Regression": "Regressão Ridge sobre o log da demanda: tendência, sazonalidade mensal, promoção, preço, "
    "distribuição, merchandising, marketing e feriados.",
    "Random Forest": "Random Forest com lag de 12 meses, calendário e variáveis explicativas (alvo em log).",
    "Gradient Boosting": "Gradient Boosting (scikit-learn) com lag de 12 meses, calendário e variáveis explicativas.",
}

OUTCOME = {"Improved": "Melhorou", "Worsened": "Piorou", "Neutral": "Neutro"}
DIRECTION = {"Upward": "Para cima", "Downward": "Para baixo"}
SCENARIO_KIND = {"base": "Base", "conservative": "Conservador", "aggressive": "Agressivo", "custom": "Personalizado"}

# Event types / planners written by older (English) versions of the app or of uploaded files.
EVENT_TYPE = {
    "Promotion": "Promoção",
    "Merchandising": "Merchandising",
    "Distribution Gain": "Ganho de distribuição",
    "Distribution Loss": "Perda de distribuição",
    "New Store": "Nova loja",
    "Customer Gain": "Ganho de cliente",
    "Customer Loss": "Perda de cliente",
    "Campaign": "Campanha",
    "Price Change": "Mudança de preço",
    "New Product": "Lançamento",
    "Delisting": "Deslistagem",
    "Competitor Action": "Ação de concorrente",
}
PLANNER = {
    "Key Account Manager": "Key Account (KAM)",
    "Sales Director": "Diretor de Vendas",
    "Trade Marketing": "Trade Marketing",
    "Demand Planner": "Planejador de Demanda",
    "Marketing": "Marketing",
    "Demo seed": "Base de demonstração",  # author of the demo dataset's future overrides
}

MONTHS_SHORT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MONTHS_LONG = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


def _missing(v: Any) -> bool:
    if v is None:
        return True
    try:
        return isinstance(v, float) and not math.isfinite(v)
    except TypeError:
        return False


def _swap(s: str) -> str:
    """'1,234,567.89' (Python) -> '1.234.567,89' (pt-BR)."""
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


def num(v: float | None, digits: int = 0, signed: bool = False) -> str:
    """1234567.8 -> '1.234.568'; num(0.712, 2) -> '0,71'."""
    if _missing(v):
        return NA
    fmt = f"{{:{'+' if signed else ''},.{digits}f}}"
    return _swap(fmt.format(float(v)))


def dec(v: float | None, digits: int = 2, signed: bool = False) -> str:
    """Plain decimal without thousands grouping: 2.1 -> '2,10'."""
    if _missing(v):
        return NA
    fmt = f"{{:{'+' if signed else ''}.{digits}f}}"
    return fmt.format(float(v)).replace(".", ",")


def pct(v: float | None, digits: int = 0, signed: bool = False) -> str:
    """0.148 -> '15%'; pct(0.148, 1) -> '14,8%'; signed -> '+14,8%'."""
    if _missing(v):
        return NA
    fmt = f"{{:{'+' if signed else ''},.{digits}f}}%"
    return _swap(fmt.format(float(v) * 100))


def _compact(a: float) -> str:
    # thresholds use the rounded value so 999_960 reads '1,00 mi' (not '1000,0 mil')
    if round(a / 1e9, 2) >= 1:
        return f"{dec(a / 1e9, 2)} bi"
    if round(a / 1e6, 2) >= 1:
        return f"{dec(a / 1e6, 2)} mi"
    if round(a) >= 1e3:
        return f"{dec(a / 1e3, 1)} mil"
    return num(a)


def money(v: float | None) -> str:
    """1_930_000 -> 'R$ 1,93 mi'; 45_600 -> 'R$ 45,6 mil'; -2e6 -> '-R$ 2,00 mi'."""
    if _missing(v):
        return NA
    v = float(v)
    return ("-" if v < 0 else "") + "R$ " + _compact(abs(v))


def units(v: float | None) -> str:
    """12_345 -> '12.345 unidades'."""
    if _missing(v):
        return NA
    return f"{num(v)} unidades"


def measure(v: float | None, measure_name: str) -> str:
    return money(v) if measure_name == "revenue" else units(v)


def series_type(code: str | None) -> str:
    return SERIES_TYPE.get(str(code), str(code)) if code else NA


def model(name: str | None) -> str:
    return MODEL.get(str(name), str(name)) if name else NA


def label(mapping: dict[str, str], code: Any) -> Any:
    """Display label of an internal code; unknown values (e.g. already Portuguese) pass through."""
    if _missing(code):
        return None
    return mapping.get(str(code), code)


def month_label(d: Any, long: bool = False) -> str:
    """Timestamp/date/ISO string -> 'dez/2026' (or 'dezembro de 2026' when long=True)."""
    if d is None:
        return NA
    import pandas as pd  # local: keeps this module light for the forecasting workers

    ts = pd.Timestamp(d)
    if pd.isna(ts):
        return NA
    return f"{MONTHS_LONG[ts.month - 1]} de {ts.year}" if long else f"{MONTHS_SHORT[ts.month - 1]}/{ts.year}"


def model_catalog(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Model catalog with Portuguese descriptions (names and family codes are kept)."""
    return [{**m, "description": MODEL_DESCRIPTION.get(m.get("name"), m.get("description"))} for m in catalog]
