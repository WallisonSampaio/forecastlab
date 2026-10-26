"""Deterministic natural-language helpers (PT-BR / EN): number formatting and code labels.

Portuguese is the product language: every helper defaults to ``lang="pt"`` style output
when asked for Portuguese ("R$ 9,83 mi", "14,8%", "dezembro/2026"). Internal codes
(series types, model names, classifications ...) stay in English in the data and are
translated here only when written into an answer.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from typing import Any

import pandas as pd

NA = {"pt": "n/d", "en": "n/a"}

MONTHS_EN = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
MONTHS_PT = [
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
MONTHS_PT_SHORT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# ----------------------------------------------------------------------------- code -> label
SERIES_TYPE_PT = {
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
    "New Product": "Lançamento",
    "New Product (Launch)": "Lançamento",
}
MODEL_PT = {
    "Naive": "Ingênuo",
    "Seasonal Naive": "Ingênuo sazonal",
    "Moving Average": "Média Móvel",
    "Regression": "Regressão",
}
CLASS_LABEL = {
    "REALISTIC": ("REALISTIC", "REALISTA"),
    "STRETCH": ("STRETCH", "DESAFIADORA"),
    "AGGRESSIVE": ("AGGRESSIVE", "AGRESSIVA"),
    "UNDERESTIMATED": ("UNDERESTIMATED", "SUBESTIMADA"),
}
BIAS_CLASS_PT = {"Under": "Subestimado", "Balanced": "Equilibrado", "Over": "Superestimado"}
CONFIDENCE_PT = {"High": "Alta", "Medium": "Média", "Low": "Baixa"}
SEVERITY_LABEL = {
    "critical": ("critical", "crítico"),
    "high": ("high", "alto"),
    "medium": ("medium", "médio"),
    "low": ("low", "baixo"),
}
LEVER_LABEL = {
    "price": ("price", "preço"),
    "distribution": ("distribution", "distribuição"),
    "marketing": ("marketing", "marketing"),
    "promotion": ("promotion", "promoção"),
    "merchandising": ("merchandising", "merchandising"),
    "customer_growth": ("customer growth", "crescimento de clientes"),
    "market_growth": ("market growth", "crescimento de mercado"),
    "Distribution": ("Distribution", "Distribuição"),
    "Price": ("Price", "Preço"),
    "Marketing": ("Marketing", "Marketing"),
    "Promotions": ("Promotions", "Promoções"),
}
# Event types / planners are Portuguese in the data; older English datasets are translated.
EVENT_PT = {
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
PLANNER_PT = {
    "Key Account Manager": "Key Account (KAM)",
    "Sales Director": "Diretor de Vendas",
    "Trade Marketing": "Trade Marketing",
    "Demand Planner": "Planejador de Demanda",
    "Marketing": "Marketing",
}
OUTCOME_PT = {"Improved": "Melhorou", "Worsened": "Piorou", "Neutral": "Neutro"}

DIM_SINGULAR = {
    "pt": {
        "sku": "SKU",
        "customer": "cliente",
        "region": "região",
        "channel": "canal",
        "category": "categoria",
        "brand": "marca",
        "planner": "planejador",
        "event_type": "tipo de evento",
        "model": "modelo",
    },
    "en": {
        "sku": "SKU",
        "customer": "customer",
        "region": "region",
        "channel": "channel",
        "category": "category",
        "brand": "brand",
        "planner": "planner",
        "event_type": "event type",
        "model": "model",
    },
}
DIM_PLURAL = {
    "pt": {
        "sku": "SKUs",
        "customer": "clientes",
        "region": "regiões",
        "channel": "canais",
        "category": "categorias",
        "brand": "marcas",
        "planner": "planejadores",
        "event_type": "tipos de evento",
    },
    "en": {
        "sku": "SKUs",
        "customer": "customers",
        "region": "regions",
        "channel": "channels",
        "category": "categories",
        "brand": "brands",
        "planner": "planners",
        "event_type": "event types",
    },
}
FEMININE_DIMS = {"region", "category", "brand"}


def t(lang: str, en: str, pt: str) -> str:
    return en if lang == "en" else pt


def _missing(v: Any) -> bool:
    if v is None:
        return True
    try:
        return not math.isfinite(float(v))
    except (TypeError, ValueError):
        return True


def _swap(s: str) -> str:
    """'1,234,567.89' (Python) -> '1.234.567,89' (pt-BR)."""
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


# ----------------------------------------------------------------------------- numbers
def num(v: float | None, lang: str = "pt", digits: int = 0, signed: bool = False) -> str:
    """Grouped number: pt '1.234.568' / en '1,234,568'."""
    if _missing(v):
        return NA.get(lang, "n/d")
    s = f"{float(v):{'+' if signed else ''},.{digits}f}"
    return s if lang == "en" else _swap(s)


def dec(v: float | None, lang: str = "pt", digits: int = 2, signed: bool = False) -> str:
    """Plain decimal (elasticities, indices): pt '-1,20' / en '-1.20'."""
    if _missing(v):
        return NA.get(lang, "n/d")
    s = f"{float(v):{'+' if signed else ''}.{digits}f}"
    return s if lang == "en" else s.replace(".", ",")


def money(v: float | None, lang: str = "pt") -> str:
    """pt 'R$ 9,83 mi' / 'R$ 45,6 mil' / 'R$ 1,20 bi'; en 'R$ 9.83M'."""
    if _missing(v):
        return NA.get(lang, "n/d")
    v = float(v)
    sign = "-" if v < 0 else ""
    a = abs(v)
    if lang == "en":
        if a >= 1e9:
            s = f"{a / 1e9:.2f}B"
        elif a >= 1e6:
            s = f"{a / 1e6:.2f}M"
        elif a >= 1e3:
            s = f"{a / 1e3:.1f}K"
        else:
            s = f"{a:.0f}"
    elif a >= 1e9:
        s = f"{dec(a / 1e9, 'pt', 2)} bi"
    elif a >= 1e6:
        s = f"{dec(a / 1e6, 'pt', 2)} mi"
    elif a >= 1e3:
        s = f"{dec(a / 1e3, 'pt', 1)} mil"
    else:
        s = num(a, "pt")
    return f"{sign}R$ {s}"


def units(v: float | None, lang: str = "pt") -> str:
    """pt '12,3 mil unidades' / '950 unidades'; en '12.3K units'."""
    if _missing(v):
        return NA.get(lang, "n/d")
    v = float(v)
    sign = "-" if v < 0 else ""
    a = abs(v)
    if lang == "en":
        s = f"{a / 1e6:.2f}M" if a >= 1e6 else f"{a / 1e3:.1f}K" if a >= 1e3 else f"{a:.0f}"
        return f"{sign}{s} units"
    if a >= 1e6:
        s = f"{dec(a / 1e6, 'pt', 2)} mi"
    elif a >= 1e3:
        s = f"{dec(a / 1e3, 'pt', 1)} mil"
    else:
        s = num(a, "pt")
    return f"{sign}{s} unidades"


def measure(v: float | None, m: str, lang: str = "pt") -> str:
    return money(v, lang) if m == "revenue" else units(v, lang)


def pct(v: float | None, lang: str = "pt", signed: bool = False, digits: int = 1) -> str:
    """0.148 -> pt '14,8%' / en '14.8%'; signed -> '+14,8%'."""
    if _missing(v):
        return NA.get(lang, "n/d")
    s = f"{float(v) * 100:{'+' if signed else ''}.{digits}f}%"
    return s if lang == "en" else s.replace(".", ",")


def pp(v: float | None, lang: str = "pt", digits: int = 1) -> str:
    """Percentage-point difference: 0.021 -> '+2,1 p.p.' / '+2.1 pp'."""
    if _missing(v):
        return NA.get(lang, "n/d")
    s = f"{float(v) * 100:+.{digits}f}"
    return f"{s} pp" if lang == "en" else f"{s.replace('.', ',')} p.p."


def ordinal(n: int, lang: str = "pt") -> str:
    if lang != "en":
        return f"{n}º"
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# ----------------------------------------------------------------------------- dates
def _ts(d: Any) -> pd.Timestamp:
    return pd.Timestamp(d)


def month_name(date: Any, lang: str = "pt") -> str:
    """'2026-12-01' -> pt 'dezembro/2026' / en 'December 2026'."""
    d = _ts(date)
    return f"{MONTHS_EN[d.month - 1]} {d.year}" if lang == "en" else f"{MONTHS_PT[d.month - 1]}/{d.year}"


def month_short(date: Any, lang: str = "pt") -> str:
    """'2026-12-01' -> pt 'dez/26' / en 'Dec 26'."""
    d = _ts(date)
    return (
        f"{MONTHS_EN[d.month - 1][:3]} {d.year % 100:02d}"
        if lang == "en"
        else (f"{MONTHS_PT_SHORT[d.month - 1]}/{d.year % 100:02d}")
    )


def month_only(date: Any, lang: str = "pt") -> str:
    d = _ts(date)
    return MONTHS_EN[d.month - 1] if lang == "en" else MONTHS_PT[d.month - 1]


def period_text(months: Sequence[Any] | None, lang: str = "pt") -> str:
    """Human label for a set of months: one month, a calendar quarter / year, or a range."""
    if not months:
        return t(lang, "the next 12 months", "os próximos 12 meses")
    ds = sorted({_ts(m) for m in months})
    if len(ds) == 1:
        return month_name(ds[0], lang)
    consecutive = all((b.year - a.year) * 12 + b.month - a.month == 1 for a, b in itertools.pairwise(ds))
    first, last = ds[0], ds[-1]
    if consecutive and len(ds) == 3 and first.month in (1, 4, 7, 10) and first.year == last.year:
        q = (first.month - 1) // 3 + 1
        return t(lang, f"Q{q} {first.year}", f"{q}º trimestre de {first.year}")
    if consecutive and len(ds) == 12 and first.month == 1:
        return t(lang, f"the year {first.year}", f"o ano de {first.year}")
    if consecutive:
        return t(
            lang,
            f"{month_name(first, 'en')} to {month_name(last, 'en')}",
            f"{month_name(first, 'pt')} a {month_name(last, 'pt')}",
        )
    return ", ".join(month_name(d, lang) for d in ds)


def _period_kind(months: Sequence[Any] | None) -> tuple[str, list[pd.Timestamp]]:
    if not months:
        return "horizon", []
    ds = sorted({_ts(m) for m in months})
    if len(ds) == 1:
        return "month", ds
    consecutive = all((b.year - a.year) * 12 + b.month - a.month == 1 for a, b in itertools.pairwise(ds))
    first, last = ds[0], ds[-1]
    if consecutive and len(ds) == 3 and first.month in (1, 4, 7, 10) and first.year == last.year:
        return "quarter", ds
    if consecutive and len(ds) == 12 and first.month == 1:
        return "year", ds
    return ("range" if consecutive else "list"), ds


def period_prep(months: Sequence[Any] | None, lang: str = "pt", prep: str = "em") -> str:
    """Period with a grammatical preposition / article (pt-BR contractions).

    prep "em":   'em dezembro/2026' · 'no 1º trimestre de 2027' · 'em 2026' · 'nos próximos 12 meses'
    prep "de":   'de dezembro/2026' · 'do 1º trimestre de 2027' · 'de 2026' · 'dos próximos 12 meses'
    prep "para": 'para dezembro/2026' · 'para o 1º trimestre de 2027' · 'para 2026' · 'para os próximos 12 meses'
    prep "":     bare label for titles: 'dezembro/2026' · '1º trimestre de 2027' · '2026' · 'próximos 12 meses'
    """
    kind, ds = _period_kind(months)
    if lang == "en":
        if kind == "horizon":
            core = "the next 12 months" if prep else "next 12 months"
        elif kind == "year":
            core = str(ds[0].year)
        elif kind == "range":
            core = f"{month_name(ds[0], 'en')} to {month_name(ds[-1], 'en')}"
            if prep:
                return f"from {core}"
        else:
            core = period_text(ds, "en")
        word = {"em": "in", "de": "for", "para": "for"}.get(prep, "")
        return f"{word} {core}".strip()
    if kind == "horizon":
        return {"em": "nos ", "de": "dos ", "para": "para os "}.get(prep, "") + "próximos 12 meses"
    if kind == "quarter":
        core = period_text(ds, "pt")
        return {"em": f"no {core}", "de": f"do {core}", "para": f"para o {core}"}.get(prep, core)
    if kind == "year":
        core = str(ds[0].year)
    elif kind == "range":
        core = f"{month_name(ds[0], 'pt')} a {month_name(ds[-1], 'pt')}"
        if prep in ("em", "de"):
            return f"de {core}"
        if prep == "para":
            return f"para o período de {core}"
        return core
    else:
        core = period_text(ds, "pt")
    return f"{prep} {core}".strip()


# ----------------------------------------------------------------------------- labels
def class_label(cls: str, lang: str = "pt") -> str:
    en, pt_ = CLASS_LABEL.get(cls, (cls, cls))
    return en if lang == "en" else pt_


def series_type(code: Any, lang: str = "pt") -> str:
    s = str(code) if code is not None else NA.get(lang, "n/d")
    return s if lang == "en" else SERIES_TYPE_PT.get(s, s)


def model_name(name: Any, lang: str = "pt") -> str:
    s = str(name) if name is not None else NA.get(lang, "n/d")
    return s if lang == "en" else MODEL_PT.get(s, s)


def bias_class(code: Any, lang: str = "pt") -> str:
    s = str(code)
    return s if lang == "en" else BIAS_CLASS_PT.get(s, s)


def confidence(code: Any, lang: str = "pt") -> str:
    s = str(code)
    return s if lang == "en" else CONFIDENCE_PT.get(s, s)


def severity(code: str, lang: str = "pt") -> str:
    en, pt_ = SEVERITY_LABEL.get(code, (code, code))
    return en if lang == "en" else pt_


def lever(code: str, lang: str = "pt") -> str:
    en, pt_ = LEVER_LABEL.get(code, (code.replace("_", " "), code.replace("_", " ")))
    return en if lang == "en" else pt_


def event_type(v: Any, lang: str = "pt") -> str:
    s = str(v)
    return s if lang == "en" else EVENT_PT.get(s, s)


def planner(v: Any, lang: str = "pt") -> str:
    s = str(v)
    return s if lang == "en" else PLANNER_PT.get(s, s)


def group_value(dim: str, v: Any, lang: str = "pt") -> str:
    if dim == "planner":
        return planner(v, lang)
    if dim == "event_type":
        return event_type(v, lang)
    return str(v)


def dim_label(dim: str, lang: str = "pt", plural: bool = False) -> str:
    table = (DIM_PLURAL if plural else DIM_SINGULAR)["en" if lang == "en" else "pt"]
    return table.get(dim, dim)


def dim_title(dim: str, lang: str = "pt") -> str:
    s = dim_label(dim, lang)
    return s[:1].upper() + s[1:]


def none_of(dim: str, lang: str = "pt") -> str:
    """'Nenhum cliente' / 'Nenhuma região' / 'No customer'."""
    if lang == "en":
        return f"No {dim_label(dim, 'en')}"
    return f"{'Nenhuma' if dim in FEMININE_DIMS else 'Nenhum'} {dim_label(dim, 'pt')}"


def article_pl(dim: str, lang: str = "pt") -> str:
    """Plural definite article: 'Os' clientes / 'As' regiões / 'The'."""
    if lang == "en":
        return "The"
    return "As" if dim in FEMININE_DIMS else "Os"


def agree(word_m: str, dim: str, lang: str = "pt") -> str:
    """Gender agreement for a masculine plural adjective: 'listados' -> 'listadas' (regiões)."""
    if lang == "en" or dim not in FEMININE_DIMS:
        return word_m
    return word_m[:-2] + "as" if word_m.endswith("os") else word_m


def plural(n: int, singular: str, plural_: str) -> str:
    return f"{n} {singular if n == 1 else plural_}"
