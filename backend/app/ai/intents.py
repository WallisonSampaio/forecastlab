"""Intent extraction: deterministic, bilingual (EN / PT-BR) question parser.

Produces an ``Intent`` (what to compute) plus extracted entities (months,
dimension, hierarchy members, what-if levers). The local LLM is only used as
a fallback classifier when no rule matches.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

INTENTS = {
    "what_if": "Simulate a what-if scenario (distribution, price, promotion, marketing, growth).",
    "target_feasibility": "Assess whether a sales target is realistic.",
    "fva_overrides": "Forecast Value Added of commercial overrides.",
    "best_model": "Which forecasting model performs best for a selection.",
    "bias_ranking": "Rank entities by forecast bias (over/under-forecast).",
    "worst_accuracy": "Rank entities by forecast accuracy / error.",
    "budget_gap": "Where the consensus forecast is below/above budget.",
    "forecast_drivers": "Explain what drives forecast growth for a month or period.",
    "risks": "Main risks and alerts.",
    "model_distribution": "Which models are champions and how often.",
    "series_types": "Demand pattern classification of the portfolio.",
    "summary": "Executive summary of the forecast.",
}

PT_HINTS = {
    "qual",
    "quais",
    "que",
    "como",
    "meta",
    "previsao",
    "cliente",
    "clientes",
    "mes",
    "crescimento",
    "acontece",
    "aumentar",
    "aumenta",
    "distribuicao",
    "preco",
    "modelo",
    "melhor",
    "pior",
    "estao",
    "esta",
    "ajustes",
    "orcamento",
    "realista",
    "porque",
    "por",
    "se",
    "resumo",
    "riscos",
    "sao",
    "e",
    "julho",
    "dezembro",
    "acuracia",
    "vies",
}

MONTHS = {
    1: ["january", "jan", "janeiro"],
    2: ["february", "feb", "fevereiro", "fev"],
    3: ["march", "mar", "marco"],
    4: ["april", "apr", "abril", "abr"],
    5: ["may", "maio", "mai"],
    6: ["june", "jun", "junho"],
    7: ["july", "jul", "julho"],
    8: ["august", "aug", "agosto", "ago"],
    9: ["september", "sep", "sept", "setembro", "set"],
    10: ["october", "oct", "outubro", "out"],
    11: ["november", "nov", "novembro"],
    12: ["december", "dec", "dezembro", "dez"],
}
AMBIGUOUS_MONTH_TOKENS = {"mar", "may", "set", "out", "jun", "jul"}  # also common words; need context

DIM_WORDS = {
    "sku": ["sku", "skus", "product", "products", "produto", "produtos", "item", "items", "itens"],
    "customer": ["customer", "customers", "cliente", "clientes", "account", "accounts", "conta", "contas"],
    "region": ["region", "regions", "regiao", "regioes"],
    "channel": ["channel", "channels", "canal", "canais"],
    "category": ["category", "categories", "categoria", "categorias"],
    "brand": ["brand", "brands", "marca", "marcas"],
    "planner": ["planner", "planners", "planejador", "planejadores"],
    "event_type": ["event", "events", "evento", "eventos"],
}

LEVER_WORDS = {
    "distribution": ["distribution", "distribuicao", "listing", "listings", "numeric distribution"],
    "price": ["price", "preco", "pricing", "precos"],
    "marketing": ["marketing", "media", "midia", "advertising"],
    "promotion": ["promotion", "promotions", "promo", "promos", "promocao", "promocoes"],
    "merchandising": ["merchandising", "display", "displays", "end-cap", "endcap"],
    "customer_growth": ["customer growth", "crescimento de clientes", "customer base"],
    "market_growth": ["market growth", "crescimento de mercado", "market"],
}


def norm(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s.lower()).strip()


def _has(text: str, *words: str) -> bool:
    return any(re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", text) for w in words)


@dataclass
class Intent:
    name: str
    language: str = "en"
    months: list[str] = field(default_factory=list)
    dimension: str | None = None
    filters: dict[str, Any] = field(default_factory=dict)
    levers: dict[str, Any] = field(default_factory=dict)
    direction: str | None = None  # over / under / best / worst
    confidence: float = 1.0
    source: str = "rules"

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def detect_language(text: str) -> str:
    tokens = set(re.findall(r"[a-z]+", norm(text)))
    raw = text.lower()
    pt_score = len(tokens & PT_HINTS) + (2 if any(c in raw for c in "ãõçáéíóúâê") else 0)
    en_score = len(tokens & {"what", "which", "is", "the", "are", "how", "does", "happens", "if", "best", "worst"})
    return "pt" if pt_score > en_score else "en"


def extract_months(text: str, horizon: list[pd.Timestamp], last_actual: pd.Timestamp) -> list[str]:
    t = norm(text)
    found: list[int] = []
    for m, names in MONTHS.items():
        for name in names:
            if name in AMBIGUOUS_MONTH_TOKENS and not re.search(
                rf"(in|em|de|for|of|para|no|na|month|mes)\s+{name}\b|\b{name}\s*(/|\d{{2,4}})", t
            ):
                continue
            if _has(t, name):
                found.append(m)
                break
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", t)]
    out = []
    for m in found:
        candidates = [d for d in horizon if d.month == m]
        if years:
            candidates = [d for d in candidates if d.year in years] or [pd.Timestamp(year=years[0], month=m, day=1)]
        if not candidates:  # month in the past -> most recent actual month
            y = last_actual.year if m <= last_actual.month else last_actual.year - 1
            candidates = [pd.Timestamp(year=y, month=m, day=1)]
        out.append(candidates[0].strftime("%Y-%m-01"))
    if re.search(r"\b(q[1-4])\b", t) and horizon:
        q = int(re.search(r"\bq([1-4])\b", t).group(1))  # type: ignore[union-attr]
        out = [d.strftime("%Y-%m-01") for d in horizon[(q - 1) * 3 : q * 3]]
    if _has(t, "next month", "proximo mes", "mes que vem") and horizon:
        out = [horizon[0].strftime("%Y-%m-01")]
    return sorted(set(out))


def extract_dimension(text: str) -> str | None:
    t = norm(text)
    best, pos = None, 10**9
    for dim, words in DIM_WORDS.items():
        for w in words:
            m = re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", t)
            if m and m.start() < pos:
                best, pos = dim, m.start()
    return best


def extract_entities(text: str, members: dict[str, list[str]]) -> dict[str, Any]:
    """Match hierarchy members (customers, SKUs, products, regions...) mentioned in the text."""
    t = norm(text)
    filters: dict[str, Any] = {}
    for dim in ("region", "channel", "category", "brand", "customer"):
        for name in sorted(members.get(dim, []), key=len, reverse=True):
            n = norm(name)
            first = n.split(" ")[0]
            if (len(n) > 3 and n in t) or (dim == "customer" and len(first) > 4 and _has(t, first)):
                filters[dim] = name
                break
    for sku in members.get("sku", []):
        code = norm(sku)
        digits = re.sub(r"\D", "", sku)
        if code in t or (len(digits) >= 4 and re.search(rf"\b{digits}\b", t)):
            filters["sku"] = sku
            break
    if "sku" not in filters:
        for sku, product in members.get("product_map", []):
            p = norm(product)
            if p in t:
                filters["sku"] = sku
                break
    return filters


_DOWN = r"(reduc|decreas|cut|lower|drop|fall|diminu|queda|cair|corte|minus|menos|redu)"


def _number_near(t: str, words: list[str]) -> float | None:
    """Percentage closest to a lever word (prefers the one right after it)."""
    for w in words:
        for m in re.finditer(rf"(?<![a-z]){re.escape(w)}", t):
            after = t[m.end() : m.end() + 35]
            before = t[max(0, m.start() - 30) : m.start()]
            for seg, is_after in ((after, True), (before, False)):
                found = list(re.finditer(r"([+-]?\d+(?:[.,]\d+)?)\s*%", seg))
                if not found:
                    continue
                n = found[0] if is_after else found[-1]
                v = float(n.group(1).replace(",", ".")) / 100
                between = seg[: n.start()] if is_after else seg[n.end() :]
                # Words right before the lever ("reduce price"), stopping at another figure or conjunction.
                prefix = re.split(r"\d+(?:[.,]\d+)?\s*%|,|;| e | and ", before)[-1]
                if v > 0 and re.search(_DOWN, between + " " + prefix):
                    v = -v
                return v
    return None


def extract_levers(text: str) -> dict[str, Any]:
    t = norm(text)
    levers: dict[str, Any] = {}
    for lever, words in LEVER_WORDS.items():
        if lever in ("promotion", "merchandising"):
            if _has(t, *words):
                levers[lever] = True
            continue
        if lever == "market_growth" and not _has(t, "market growth", "crescimento de mercado", "mercado"):
            continue
        if any(w in t for w in words):
            v = _number_near(t, words)
            if v is not None:
                levers[lever] = v
    return levers


def parse(
    text: str, members: dict[str, list[str]], horizon: list[pd.Timestamp], last_actual: pd.Timestamp
) -> Intent | None:
    t = norm(text)
    lang = detect_language(text)
    months = extract_months(text, horizon, last_actual)
    dim = extract_dimension(text)
    filters = extract_entities(text, members)
    levers = extract_levers(text)

    def make(name: str, **kw: Any) -> Intent:
        return Intent(
            name=name,
            language=lang,
            months=months,
            dimension=kw.pop("dimension", dim),
            filters=filters,
            levers=levers,
            **kw,
        )

    if _has(
        t, "what if", "what happens", "e se", "o que acontece", "simulate", "simular", "simule", "scenario", "cenario"
    ) or (
        levers
        and _has(
            t,
            "increase",
            "increases",
            "decrease",
            "aumentar",
            "aumenta",
            "reduzir",
            "reduz",
            "cut",
            "raise",
            "if",
            "se",
        )
    ):
        if levers:
            return make("what_if")
    if _has(
        t,
        "override",
        "overrides",
        "ajuste",
        "ajustes",
        "fva",
        "value added",
        "valor agregado",
        "adjustments",
        "adjustment",
    ):
        return make("fva_overrides", dimension=dim if dim in ("planner", "event_type", "customer") else None)
    if _has(t, "target", "targets", "meta", "metas", "quota") and _has(
        t,
        "realistic",
        "realista",
        "achievable",
        "atingivel",
        "feasible",
        "viavel",
        "reach",
        "atingir",
        "aggressive",
        "agressiva",
        "possible",
        "possivel",
        "likely",
        "probabilidade",
        "probability",
        "is",
        "e",
    ):
        return make("target_feasibility")
    if _has(t, "model", "models", "modelo", "modelos", "algorithm", "algoritmo") and _has(
        t, "best", "melhor", "performs", "perform", "performa", "win", "ganha", "champion", "campeao"
    ):
        if _has(t, "most", "often", "distribution", "mais", "frequen", "how many", "quantos") and not filters:
            return make("model_distribution")
        return make("best_model")
    if _has(
        t,
        "overforecast",
        "overforecasted",
        "over-forecast",
        "over forecast",
        "superestim",
        "superestimado",
        "superestimados",
        "underforecast",
        "underforecasted",
        "under-forecast",
        "under forecast",
        "subestim",
        "subestimados",
        "bias",
        "vies",
        "enviesad",
    ):
        direction = (
            "under"
            if _has(
                t, "underforecast", "underforecasted", "under-forecast", "under forecast", "subestim", "subestimados"
            )
            else "over"
        )
        return make("bias_ranking", direction=direction, dimension=dim or "customer")
    if _has(t, "accuracy", "acuracia", "error", "erro", "erros", "wmape", "precise", "precisao", "mape"):
        direction = "best" if _has(t, "best", "melhor", "melhores", "highest accuracy", "maior acuracia") else "worst"
        return make("worst_accuracy", direction=direction, dimension=dim or "sku")
    if _has(t, "budget", "orcamento", "plano financeiro", "below plan", "abaixo do plano", "gap"):
        return make("budget_gap", dimension=dim or "customer")
    if _has(
        t,
        "driving",
        "drives",
        "driver",
        "drivers",
        "why",
        "por que",
        "porque",
        "explain",
        "explica",
        "growth",
        "crescimento",
        "cresce",
        "decline",
        "queda",
    ):
        return make("forecast_drivers")
    if _has(
        t,
        "risk",
        "risks",
        "risco",
        "riscos",
        "alert",
        "alerts",
        "alerta",
        "alertas",
        "problem",
        "problema",
        "problemas",
        "attention",
        "atencao",
    ):
        return make("risks")
    if _has(t, "champion", "champions", "campeao", "campeoes", "which models", "quais modelos"):
        return make("model_distribution")
    if _has(
        t,
        "intermittent",
        "intermitente",
        "seasonal",
        "sazonal",
        "pattern",
        "padrao",
        "padroes",
        "classification",
        "classificacao",
        "series type",
        "tipo de serie",
    ):
        return make("series_types")
    if _has(
        t,
        "summary",
        "summarize",
        "resumo",
        "resuma",
        "overview",
        "visao geral",
        "how are we",
        "como estamos",
        "forecast",
        "previsao",
    ):
        return make("summary")
    return None
