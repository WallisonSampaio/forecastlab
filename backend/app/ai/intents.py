"""Intent understanding for the AI Demand Analyst (PT-BR first, English too).

Deterministic and explainable:

* ``extract_entities`` finds hierarchy members in free text (customers, SKUs, products,
  brands, regions, channels, categories) - accent/case-insensitive, with PT/EN aliases,
  partial distinctive tokens ("Atlas", "Litoral"), fuzzy matching (difflib) and
  guards against false positives on common words.
* ``extract_months`` resolves months and relative periods ("dez", "próximo trimestre",
  "T1", "próximos 3 meses") to forecast-horizon months.
* ``parse`` scores every intent with weighted PT/EN patterns plus entity-aware boosts
  and returns the best one. It only returns ``None`` when nothing at all was
  recognized (no intent keyword, metric, period or entity) - the local LLM is then
  used as a fallback classifier when available.
"""

from __future__ import annotations

import difflib
import itertools
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

INTENTS = {
    "forecast_value": "How much will we sell: forecast value for a period / entity (consensus, statistical, P10-P90).",
    "target_feasibility": "Assess whether a sales target is realistic / will be reached.",
    "metric_lookup": "Value of an accuracy metric (WMAPE, accuracy, bias, RMSE...) for an entity or the portfolio.",
    "entity_overview": "Overview of one customer / region / channel / category / brand / SKU.",
    "what_if": "Simulate a what-if scenario (distribution, price, promotion, marketing, growth).",
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

# Tie-break order (most specific first).
PRIORITY = [
    "what_if",
    "target_feasibility",
    "fva_overrides",
    "best_model",
    "model_distribution",
    "metric_lookup",
    "bias_ranking",
    "worst_accuracy",
    "budget_gap",
    "forecast_value",
    "forecast_drivers",
    "risks",
    "series_types",
    "entity_overview",
    "summary",
]
THRESHOLD = 2.0


# ----------------------------------------------------------------------------- text utils
def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")


def norm(text: str) -> str:
    """Lower-case, accent-free, single-spaced text."""
    return re.sub(r"\s+", " ", _ascii(text).lower()).strip()


def _bound(body: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])")


def _has(text: str, *words: str) -> bool:
    return any(_bound(re.escape(w)).search(text) for w in words)


def _word(w: str) -> str:
    """Regex for one normalized word: ``*`` suffix = prefix; otherwise tolerant to plurals."""
    if w.endswith("*"):
        return re.escape(w[:-1]) + r"[a-z]*"
    if len(w) <= 3:
        return re.escape(w)
    if w.endswith("ao"):
        return re.escape(w[:-2]) + r"(?:ao|oes|aos|aes)"
    if w.endswith("al"):
        return re.escape(w[:-2]) + r"(?:al|ais)"
    if w.endswith("el"):
        return re.escape(w[:-2]) + r"(?:el|eis)"
    if w.endswith("m"):
        return re.escape(w[:-1]) + r"(?:m|ns)"
    if w.endswith(("r", "z", "s")):
        return re.escape(w) + r"(?:es|s)?"
    return re.escape(w) + "s?"


def _phrase_body(p: str) -> str:
    if p.startswith("re:"):
        return p[3:]
    parts: list[str] = []
    for i, tok in enumerate(p.split()):
        optional = tok.endswith("?") and i > 0
        tok = tok.rstrip("?")
        core = "(?:" + "|".join(_word(x) for x in tok.split("|")) + ")"
        if i == 0:
            parts.append(core)
        else:
            parts.append(rf"(?:\s+{core})?" if optional else rf"\s+{core}")
    return "".join(parts)


def _phrase(p: str) -> re.Pattern[str]:
    """Compile a phrase pattern.

    Words are separated by spaces; ``a|b`` = alternative words in one slot; a trailing ``?``
    makes a slot optional; ``*`` = prefix; ``;`` separates whole alternative phrases;
    ``re:`` = raw regex. Matching is on normalized (accent-free, lower-case) text.
    """
    bodies = [_phrase_body(x.strip()) for x in p.split(";") if x.strip()]
    return _bound("(?:" + "|".join(f"(?:{b})" for b in bodies) + ")")


# ----------------------------------------------------------------------------- vocabularies
def _words(text: str) -> set[str]:
    return set(text.split())


PT_HINTS = _words(
    "qual quais quanto quantos quantas que como onde porque por para pela pelo de da das dos em na nas nos o "
    "os e se um uma com esta estao estamos vamos vai sao tem meta metas previsao vender vendas cliente "
    "clientes regiao canal marca produto produtos mes meses proximo proximos trimestre crescimento cresce "
    "acontece aumentar aumenta cair distribuicao preco modelo melhor pior ajustes orcamento realista resumo "
    "resuma riscos acuracia vies fale sobre abaixo acima janeiro fevereiro marco abril maio junho julho "
    "agosto setembro outubro novembro dezembro"
)
EN_HINTS = _words(
    "what which who why where how is are the does will we our of for in by with if happens much many sell "
    "sales target realistic best worst model models performs customers customer region channel brand product "
    "products accuracy bias budget below above risks main driving growth increases decreases drops overrides "
    "reduced tell about summary summarize next month quarter january february march april june july august "
    "september october november december"
)

MONTHS = {
    1: ["janeiro", "january", "jan"],
    2: ["fevereiro", "february", "fev", "feb"],
    3: ["marco", "march", "mar"],
    4: ["abril", "april", "abr", "apr"],
    5: ["maio", "may", "mai"],
    6: ["junho", "june", "jun"],
    7: ["julho", "july", "jul"],
    8: ["agosto", "august", "ago", "aug"],
    9: ["setembro", "september", "sept", "set", "sep"],
    10: ["outubro", "october", "out", "oct"],
    11: ["novembro", "november", "nov"],
    12: ["dezembro", "december", "dez", "dec"],
}
SEASONAL_MONTHS = {
    12: ["natal", "christmas", "fim de ano", "festas de fim de ano"],
    11: ["black friday"],
    5: ["dia das maes", "mother's day", "mothers day"],
    8: ["dia dos pais", "father's day", "fathers day"],
}
# Abbreviations that are also common words ("set", "mar", "out", "ago", "dez" = ten, "may").
AMBIGUOUS_MONTH_TOKENS = {"mar", "may", "set", "out", "ago", "dez", "sep", "dec"}
_MONTH_CONTEXT = r"(?<![a-z])(?:em|de|no|na|para|ate|desde|in|for|of|until|since|mes|month|e|and|a)\s+$"
_PAST_AFTER = r"\s*(?:de\s+20\d{2}\s*)?(?:passad[oa]|anterior|ultimo|last|previous)(?![a-z])"
_PAST_BEFORE = r"(?:ultimo|ultima|last|previous|passado)\s+(?:mes\s+de\s+)?$"

DIM_WORDS = {
    "sku": ["sku*", "produto", "produtos", "product", "products", "item", "items", "itens"],
    "customer": ["cliente", "clientes", "customer", "customers", "account", "accounts", "contas"],
    "region": ["regiao", "regioes", "region", "regions"],
    "channel": ["canal", "canais", "channel", "channels"],
    "category": ["categoria", "categorias", "category", "categories"],
    "brand": ["marca", "marcas", "brand", "brands"],
    "planner": ["planejador", "planejadores", "planner", "planners"],
    "event_type": ["evento", "eventos", "event", "events"],
}
_DIM_RES = {d: [_phrase(w) for w in ws] for d, ws in DIM_WORDS.items()}

LEVER_WORDS = {
    "distribution": ["distribuicao", "distribution", "listagem", "listagens", "listing", "listings", "pontos de venda"],
    "price": ["preco", "precos", "price", "prices", "pricing", "desconto", "descontos", "discount"],
    "marketing": [
        "marketing",
        "midia",
        "media",
        "publicidade",
        "propaganda",
        "advertising",
        "investimento em marketing",
    ],
    "promotion": ["promocao", "promocoes", "promotion", "promotions", "promo", "promos", "promocional"],
    "merchandising": ["merchandising", "display", "displays", "ponta de gondola", "end-cap", "endcap"],
    "customer_growth": [
        "crescimento de clientes",
        "base de clientes",
        "customer growth",
        "customer base",
        "novos clientes",
    ],
    "market_growth": ["crescimento de mercado", "market growth", "mercado"],
}
_DOWN = (
    r"(reduc|reduz|redu|decreas|cut|lower|drop|fall|diminu|queda|cai|caia|cair|corte|corta|minus|menos|baix|"
    r"desconto|discount|perd|lose|losing|lost|retir)"
)
_UP_GENERIC = r"(cresc|aument|sub|increas|grow|rais|eleva|mais)"

# Metric vocab -> metric code (first mentioned wins).
METRIC_WORDS: list[tuple[str, str]] = [
    ("smape", "smape"),
    ("wmape", "wmape"),
    ("mape", "wmape"),
    ("rmse", "rmse"),
    ("mase", "mase"),
    ("mae", "mae"),
    ("erro*", "wmape"),
    ("error*", "wmape"),
    ("erra|errar|errando|errou|erram|erramos|errem", "wmape"),
    ("acuracia", "accuracy"),
    ("accuracy", "accuracy"),
    ("precisao", "accuracy"),
    ("assertividade", "accuracy"),
    ("acerto*", "accuracy"),
    ("vies", "bias"),
    ("bias", "bias"),
    ("enviesad*", "bias"),
    ("superestim*", "bias"),
    ("subestim*", "bias"),
    ("re:(?:over|under)[\\s-]?forecast\\w*", "bias"),
]
_METRIC_RES = [(_phrase(w), m) for w, m in METRIC_WORDS]
_ACC_RES = [
    _phrase(p)
    for p in (
        "smape|wmape|mape|rmse|mase|mae",
        "erro*|error*",
        "erra|errar|errando|errou|erram|erramos|errem",
        "acuracia|accuracy|precisao|assertividade|acerto*",
        # "qual SKU tem o pior forecast?" -> accuracy ranking
        "re:(?:pior|piores|melhor|melhores|worst|best)\\s+(?:forecasts?|previsao|previsoes)",
        # "o forecast está bom?", "dá pra confiar no forecast?"
        "re:(?:forecasts?|previsao|previsoes)\\s+(?:esta|estao|e|sao|ta|is|are)\\s+(?:\\w+\\s+)?"
        "(?:bom|boa|bons|boas|ruim|ruins|bem|mal|preciso|precisa|confiavel|good|bad|accurate|reliable)",
        "confiar|confiavel|confiabilidade|reliable|reliability",
    )
]
_BIAS_RES = [_phrase(p) for p in ("vies|bias", "enviesad*")]
# Consensus vs statistical forecast = Forecast Value Added of the overrides.
_CONS_VS_STAT = (
    "re:consens\\w*\\s+(?:\\w+\\s+){0,5}(?:estatistic\\w*|statistical)|"
    "(?:estatistic\\w*|statistical)\\s+(?:\\w+\\s+){0,5}consens\\w*"
)
_FVA_CORE = _phrase(
    "ajuste*|override*|adjustment*|fva|agregar|agregaram|agrega; valor agregado|adicionado; value added"
    f";{_CONS_VS_STAT}"
)
# "cenário otimista / pessimista" is a forecast range question, not a bias one.
_OVER_RE = [
    _phrase(p)
    for p in (
        "superestim*",
        "sobreestim*",
        "re:over[\\s-]?forecast\\w*",
        "re:(?<!cenario )(?<!scenario )otimist\\w*",
        "acima do real",
    )
]
_UNDER_RE = [
    _phrase(p)
    for p in (
        "subestim*",
        "re:under[\\s-]?forecast\\w*",
        "re:(?<!cenario )(?<!scenario )pessimist\\w*",
        "abaixo do real",
    )
]
_RANK_RE = [
    _phrase(p)
    for p in (
        "pior|piores|melhor|melhores|maior|maiores|menor|menores",
        "top|ranking|rank|lista|liste|list",
        "worst|best|highest|lowest|most|least|biggest|largest",
        "quais|which",
        "mais|menos",
        "re:(?:qual|que|quais|which|what)\\s+(?:sku\\w*|produto\\w*|cliente\\w*|regia\\w*|regio\\w*|cana\\w*|"
        "categori\\w*|marca\\w*|product\\w*|customer\\w*|region\\w*|channel\\w*|categor\\w*|brand\\w*)",
        "re:(?:por|by)\\s+(?:sku\\w*|produto\\w*|cliente\\w*|regia\\w*|regio\\w*|cana\\w*|categori\\w*|marca\\w*|"
        "product\\w*|customer\\w*|region\\w*|channel\\w*|categor\\w*|brand\\w*)",
    )
]

_FV_WORDS = [
    _phrase(p)
    for p in (
        "previsao|previsto|prevista|previstos|projecao|projetado|projetada|estimativa",
        "forecast",
        "vender|vendera|venderao|venderemos|vendemos|vende|faturar|faturaremos|faturamento|sell|selling",
        "venda|vendas|sales|receita|revenue|volume|unidades|units",
        "consenso|consensus|p10|p50|p90",
    )
]

# intent -> [(phrase, weight)]
_RAW_PATTERNS: dict[str, list[tuple[str, float]]] = {
    "what_if": [
        ("e se", 3),
        ("o que acontece|aconteceria|acontecera", 3),
        ("what if", 4),
        ("what happens; what would happen; what will happen", 3),
        ("simul*", 3),
        ("cenario", 2),
        ("scenario*", 2),
        ("hipote*", 2),
        ("caso", 1),
        ("impacto*|impact*", 1),
    ],
    "target_feasibility": [
        ("meta", 3),
        ("target*", 3),
        ("quota*|cota", 2),
        ("objetivo", 1),
        ("realist*", 2),
        ("atingi*|atingir|alcan*|cumpri*|cumprir", 2),
        ("bater|batemos|bateremos|bate|batendo|batida", 2),
        ("viave*|viabilidade|factive*|feasib*|achievab*|reach*", 2),
        ("chance*|probab*|likel*", 2),
        ("agressiv*|aggressive|desafiador*|stretch", 1),
        ("possive*|hit", 1),
    ],
    "forecast_value": [
        (
            "quanto vamos|vai|vao|devemos|deve|devem|iremos|ira|irao|vou|podemos|conseguimos? "
            "vender|faturar|vende|vendemos|comprar|pedir",
            5,
        ),
        ("how much will|are|do|can we? sell|selling", 5),
        ("quanto", 1),
        ("how much", 2),
        ("vender|vendera|venderao|venderemos|vendemos|faturar|faturaremos|sell|selling", 2),
        ("previsao|previsto|prevista|projecao|projetado|projetada|estimativa", 2),
        ("forecast", 1),
        ("venda|vendas|sales|faturamento|receita|revenue|volume|unidades|units", 1),
        ("consenso|consensus", 2),
        ("p10|p50|p90", 2),
        ("faixa|intervalo|incerteza|range|uncertainty", 2),
        ("cenario|scenario pessimista|otimista|conservador|agressivo; pior|melhor caso; worst|best case", 3),
        ("qual|quais|what o|a|is? previsao|forecast|projecao|estimativa", 2),
        ("previsao|forecast|projecao de|da|do|of vendas|venda|receita|volume|faturamento|sales|revenue", 2),
    ],
    "metric_lookup": [
        (
            "re:(?:qual|quanto|what|how)\\s+(?:e\\s+|is\\s+|esta\\s+|foi\\s+)?(?:o\\s+|a\\s+|the\\s+)?"
            "(?:smape|wmape|mape|rmse|mae|mase|acuracia|accuracy|vies|bias|erro|error|precisao)",
            2,
        ),
    ],
    "worst_accuracy": [],
    "bias_ranking": [],
    "best_model": [
        ("modelo|model|algoritmo|algorithm|metodo|method", 2),
        ("melhor|best|better", 2),
        ("funciona|performa|performs|perform|works|work|roda|ajusta melhor|best|bem|better", 3),
        ("campeao|champion", 2),
        ("ganha|vence|wins|win|venceu", 1),
        ("recomend*|indicad*|usar|use|devo", 1),
        ("qual|which|que modelo|model|algoritmo", 2),
        ("escolhid*|selecionad*|escolha|chosen|selected", 2),
    ],
    "model_distribution": [
        ("quais|which|que modelos|models|algoritmos", 3),
        ("campeoes|champions", 3),
        ("distribuicao|distribution|mix dos? de? modelos|models|campeoes|champions", 4),
        ("re:(?:mais|most)\\s+(?:usad\\w*|used|frequent\\w*|comu\\w*|common|often|vence\\w*|wins?)", 2),
        ("com mais frequencia|frequentemente", 2),
        ("quantas series; how many series", 1),
    ],
    "fva_overrides": [
        ("ajuste*", 4),
        ("override*", 4),
        ("adjustment*", 4),
        ("fva", 4),
        ("valor agregado|adicionado", 3),
        ("value added; add value; added value", 3),
        (_CONS_VS_STAT, 5),
        ("agregar|agregaram|agrega valor", 2),
        ("intervenc*|intervention*", 2),
        ("planejador|planner|kam; key account", 1),
        ("comercia*|commercial", 1),
        ("piorar|pioraram|piorou|pioram|piora|worsen*|reduced|hurt|melhoraram|melhorou|improved", 1),
    ],
    "budget_gap": [
        ("orcamento", 3),
        ("budget*", 3),
        ("aop", 2),
        ("plano financeiro; financial plan", 2),
        ("abaixo|below do|the? plano|plan", 2),
        ("gap", 2),
        ("abaixo|acima|below|above|aquem|short|shortfall|deficit", 1),
    ],
    "forecast_drivers": [
        ("por que; qual|quais motivo", 3),
        ("porque", 3),
        ("why", 3),
        ("driver*|driv*", 3),
        ("impulsion*", 3),
        ("puxa*", 2),
        ("explic*|explain*", 2),
        ("motivo|razao|reason*", 2),
        ("cresc*", 2),
        ("growth|grow*|growing", 2),
        ("aumento|queda|declin*|decline|drop|caindo|cai", 1),
        ("ponte|bridge|decomposic*|contribu*", 2),
        ("evento*|event*|incremental|uplift", 2),
    ],
    "risks": [
        ("risco|risk*", 3),
        ("alerta|alert*", 3),
        ("problema|problem*|issue*", 2),
        ("atencao|attention|preocup*|concern*|critic*|ameaca|threat*", 2),
        ("oportunidade|opportunit*", 2),
        ("prioridade*|priorizar|priorit*|foco|focar|focus; olhar primeiro; dar errado; go wrong", 3),
    ],
    "series_types": [
        ("quantas|quantos series|skus|produtos|itens; how many series|skus|products", 3),
        ("intermitent*|intermittent", 3),
        ("sazona*|seasonal*|sazonalidade|seasonality", 2),
        ("padrao|pattern*", 2),
        ("classificac*|classification|segmentac*|segmentation", 2),
        ("tipo|type de|of? serie|series|demanda|demand", 3),
        ("perfil|profile|profiling", 2),
        ("estave*|volat*|tendencia|trend*", 1),
    ],
    "summary": [
        ("resum*|summar*|sintese", 4),
        ("visao geral; overview|panorama; big picture", 3),
        ("como estamos; how are we", 3),
        (
            "como estao|vao|andam|anda|esta|vai as|os|o|a? vendas|numeros|negocios|resultados|forecast|previsao|"
            "previsoes|plano",
            3,
        ),
        ("how are|is sales|forecast; how is the forecast|business", 3),
        ("status|situacao|geral|plano", 1),
    ],
    "entity_overview": [
        ("como esta|estao|vai|vao|anda|andam", 3),
        ("me fale|fala|conte|conta", 3),
        ("fale|fala sobre|do|da|de|dos|das", 3),
        ("tell me about; what|how about", 3),
        ("how is|are|s", 2),
        ("re:^(?:e|and)\\s+(?:o|a|os|as|the|quanto\\s+(?:ao|a))\\b", 3),
        ("sobre|about", 1),
        ("desempenho|performance|situacao|visao|resultado", 2),
        ("detalh*|details", 1),
    ],
}
PATTERNS = {k: [(_phrase(p), w) for p, w in v] for k, v in _RAW_PATTERNS.items()}

_CONDITIONAL = _phrase("se|if|caso|quando|when|supondo|assuming")
_SIMULATION = _phrase("se|if|caso|supondo|assuming|simul*|cenario|scenario*|hipote*")
_CHAMPION_WORD = _phrase("campeao|champion*")
_TARGET_WORD = _phrase("meta|target*|quota*|cota")
_BUDGET_WORD = _phrase("orcamento|budget*|aop")
_WHERE = _phrase("onde|where|quais|which")
_MODEL_WORD = _phrase("modelo|model|algoritmo|algorithm|metodo")
_STATUS_WORD = _phrase("como esta|vai|anda|estamos|estao; how is|are; status|situacao")
_DRIVER_WORD = _phrase("por que; porque|why|driver*|driv*|impulsion*|puxa*|explic*|explain*|motivo|razao|cresc*|growth")
_BEST_WORD = _phrase("melhor|melhores|best; maior acuracia; highest accuracy; menor erro; lowest error; mais precis*")
_WORST_WORD = _phrase("pior|piores|worst")
_WHY = _phrase("por que; porque|why; o que explica; explic*|explain*|motivo|razao")
# Quality words that turn "planejadores" / "eventos" into an FVA question.
_QUALITY = _phrase(
    "piora*|melhora*|pior|piores|melhor|melhores|ajud*|agreg*|valor|acuracia|accuracy|erro*|error*|vies|bias|"
    "worse*|improv*|hurt*|help*|fva"
)
# Past-tense cues: "quanto vendemos em setembro?", "como foram as vendas de agosto?".
_PAST_CUE = _phrase(
    "foi|foram|vendemos|vendeu|venderam|faturamos|faturou|faturaram|tivemos|teve|realizado|realizada|realizados|"
    "realizou|fechou|fechamos|fecharam|ficou|ficaram|sold|was|were|did"
)
_PAST_TARGET = _phrase("bateu|batemos|atingimos|atingiu|alcancamos|alcancou|cumprimos|cumpriu")
_RELATIVE = _phrase("proxim*|next|seguinte*|que vem|coming|este|esse|neste|nesse|atual|corrente|this|current")
# Accuracy / bias only exist for closed months (rolling-origin backtest).
BACKTEST_INTENTS = {"metric_lookup", "worst_accuracy", "bias_ranking"}


# ----------------------------------------------------------------------------- intent
@dataclass
class Intent:
    name: str
    language: str = "pt"
    months: list[str] = field(default_factory=list)
    dimension: str | None = None
    filters: dict[str, Any] = field(default_factory=dict)
    levers: dict[str, Any] = field(default_factory=dict)
    direction: str | None = None  # over / under / best / worst
    metric: str | None = None  # wmape / accuracy / bias / rmse / mae / smape / mase
    period: str | None = None  # month / quarter / next_n / year / horizon ...
    confidence: float = 1.0
    source: str = "rules"
    scores: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def detect_language(text: str) -> str:
    """'pt' unless the question is clearly English (Portuguese is the default)."""
    tokens = re.findall(r"[a-z]+", norm(text))
    raw = (text or "").lower()
    pt_score = sum(1 for w in tokens if w in PT_HINTS) + (2 if any(c in raw for c in "ãõçáéíóúâêô") else 0)
    en_score = sum(1 for w in tokens if w in EN_HINTS)
    return "en" if en_score > pt_score else "pt"


# ----------------------------------------------------------------------------- periods
def _horizon(horizon: list[pd.Timestamp], last_actual: pd.Timestamp) -> list[pd.Timestamp]:
    if horizon:
        return [pd.Timestamp(d).to_period("M").to_timestamp() for d in horizon]
    start = pd.Timestamp(last_actual).to_period("M").to_timestamp() + pd.DateOffset(months=1)
    return list(pd.date_range(start, periods=12, freq="MS"))


def _iso(d: pd.Timestamp) -> str:
    return pd.Timestamp(d).strftime("%Y-%m-01")


def _resolve_month(m: int, year: int | None, hz: list[pd.Timestamp], last_actual: pd.Timestamp) -> pd.Timestamp:
    if year:
        return pd.Timestamp(year=year, month=m, day=1)
    inside = [d for d in hz if d.month == m]
    if inside:
        return inside[0]
    y = last_actual.year if m <= last_actual.month else last_actual.year - 1
    return pd.Timestamp(year=y, month=m, day=1)


def _block(
    month_nums: list[int], year: int | None, hz: list[pd.Timestamp], last_actual: pd.Timestamp
) -> list[pd.Timestamp]:
    """A calendar block (quarter, semester, year) - the first occurrence touching the horizon."""
    if year is None:
        years = sorted({d.year for d in hz if d.month in month_nums})
        if years:
            year = years[0]
        else:
            year = last_actual.year if max(month_nums) <= last_actual.month else last_actual.year - 1
    return [pd.Timestamp(year=year, month=m, day=1) for m in month_nums]


def _year_after(t: str, end: int) -> int | None:
    m = re.match(r"\s*(?:de\s+|of\s+|/\s*|-\s*|,\s*)?(20\d{2}|\d{2})(?!\d)", t[end:])
    if not m:
        return None
    y = m.group(1)
    if len(y) == 2:
        if not re.match(r"\s*[/-]", t[end:]):
            return None
        return 2000 + int(y)
    return int(y)


def _parse_period(text: str, horizon: list[pd.Timestamp], last_actual: pd.Timestamp) -> tuple[list[str], str | None]:
    t = norm(text)
    hz = _horizon(horizon, pd.Timestamp(last_actual))
    la = pd.Timestamp(last_actual).to_period("M").to_timestamp()
    years = [int(y) for y in re.findall(r"(?<![\d.,/-])(20\d{2})(?![\d%])", t)]
    year = years[0] if len(set(years)) == 1 else None
    out: list[pd.Timestamp] = []
    kind: str | None = None

    # Explicit months (names / abbreviations), with an optional year right after them.
    for mnum, names in MONTHS.items():
        for name in names:
            for hit in _bound(re.escape(name)).finditer(t):
                if name in AMBIGUOUS_MONTH_TOKENS:
                    before = t[: hit.start()]
                    after = t[hit.end() :]
                    in_context = re.search(_MONTH_CONTEXT, before) or re.match(r"\s*[/-]\s*\d{2}", after)
                    numeric = re.match(r"\s*(?:por\s*cento|%|pontos?|p\.?p|meses|mes|dias|anos|mil|vezes|x\b)", after)
                    if not in_context or numeric:
                        continue
                y = _year_after(t, hit.end()) or year
                if y is None and (re.match(_PAST_AFTER, t[hit.end() :]) or re.search(_PAST_BEFORE, t[: hit.start()])):
                    y = la.year if mnum <= la.month else la.year - 1  # "abril passado", "último março"
                out.append(_resolve_month(mnum, y, hz, la))
                kind = "month"
                break
    for y_, m_ in re.findall(r"(?<!\d)(20\d{2})-(0[1-9]|1[0-2])(?!\d)", t):
        out.append(pd.Timestamp(year=int(y_), month=int(m_), day=1))
        kind = "month"
    # Retail calendar dates ("previsão para o Natal", "meta da Black Friday").
    if not out:
        for mnum, words in SEASONAL_MONTHS.items():
            if _has(t, *words):
                out.append(_resolve_month(mnum, year, hz, la))
                kind = "month"

    # Quarters / semesters.
    q = None
    qm = re.search(
        r"(?<![a-z0-9])(?:([1-4])\s*(?:o|a|st|nd|rd|th)?\s*(?:trimestre|tri|quarter)|[tq]([1-4])|([1-4])q|"
        r"quarter\s*([1-4])|(primeiro|segundo|terceiro|quarto|first|second|third|fourth)\s+(?:trimestre|tri|quarter))"
        r"(?![a-z0-9])",
        t,
    )
    if qm:
        words = {
            "primeiro": 1,
            "segundo": 2,
            "terceiro": 3,
            "quarto": 4,
            "first": 1,
            "second": 2,
            "third": 3,
            "fourth": 4,
        }
        g = [x for x in qm.groups() if x]
        q = int(g[0]) if g[0].isdigit() else words[g[0]]
        y = _year_after(t, qm.end()) or year
        out = _block([3 * (q - 1) + i for i in (1, 2, 3)], y, hz, la)
        kind = "quarter"
    else:
        cur_q = (hz[0].month - 1) // 3
        if _has(t, "proximo trimestre", "trimestre que vem", "next quarter", "proximo tri"):
            start = pd.Timestamp(year=hz[0].year, month=cur_q * 3 + 1, day=1) + pd.DateOffset(months=3)
            out = list(pd.date_range(start, periods=3, freq="MS"))
            kind = "quarter"
        elif _has(t, "este trimestre", "esse trimestre", "trimestre atual", "neste trimestre", "this quarter"):
            start = pd.Timestamp(year=hz[0].year, month=cur_q * 3 + 1, day=1)
            out = [d for d in pd.date_range(start, periods=3, freq="MS") if d >= hz[0]]
            kind = "quarter"
        elif _has(t, "ultimo trimestre", "trimestre passado", "last quarter", "previous quarter"):
            end = la - pd.DateOffset(months=la.month % 3)  # last closed calendar quarter
            out = list(pd.date_range(end - pd.DateOffset(months=2), end, freq="MS"))
            kind = "quarter"
    sm = re.search(
        r"(?<![a-z0-9])(?:([12])\s*(?:o|st|nd)?\s*semestre|h([12])|(primeiro|segundo|first|second)\s+(?:semestre|half))"
        r"(?![a-z0-9])",
        t,
    )
    if sm and q is None:
        g = [x for x in sm.groups() if x]
        s = int(g[0]) if g[0].isdigit() else (1 if g[0] in ("primeiro", "first") else 2)
        out = _block(list(range(6 * (s - 1) + 1, 6 * s + 1)), _year_after(t, sm.end()) or year, hz, la)
        kind = "semester"

    # Relative months.
    nm = re.search(r"(?:proxim[oa]s|next|seguintes|coming)\s+(\d{1,2})\s+(?:meses|months)", t) or re.search(
        r"(?<![a-z0-9])(\d{1,2})\s+(?:proximos|seguintes)\s+meses", t
    )
    lm = re.search(r"(?:ultim[oa]s|last|past)\s+(\d{1,2})\s+(?:meses|months)", t)
    if nm:
        n = max(1, min(int(nm.group(1)), len(hz)))
        if n >= len(hz):
            out, kind = [], "horizon"
        else:
            out, kind = hz[:n], "next_n"
    elif lm and not _has(t, "ultimos 12 meses de backtest"):
        n = max(1, int(lm.group(1)))
        out = list(pd.date_range(la - pd.DateOffset(months=n - 1), la, freq="MS"))
        kind = "last_n"
    if _has(t, "proximo mes", "mes que vem", "next month", "mes seguinte", "following month"):
        out, kind = [hz[1] if len(hz) > 1 else hz[0]], "month"
    elif _has(
        t, "este mes", "esse mes", "neste mes", "nesse mes", "mes atual", "mes corrente", "this month", "current month"
    ):
        out, kind = [hz[0]], "month"
    elif _has(t, "mes passado", "ultimo mes", "last month", "previous month"):
        out, kind = [la], "month"

    # Years.
    if not out and kind is None:
        if _has(t, "proximo ano", "ano que vem", "next year"):
            yy = hz[0].year + 1
            out, kind = [d for d in hz if d.year == yy] or _block(list(range(1, 13)), yy, hz, la), "year"
        elif _has(t, "este ano", "esse ano", "neste ano", "nesse ano", "this year", "ano atual", "current year"):
            out, kind = _block(list(range(1, 13)), hz[0].year, hz, la), "year"
        elif year is not None and not re.search(r"(?:vs|versus|contra)\s+(?:o\s+)?(?:ano\s+)?(?:de\s+)?20\d{2}", t):
            out, kind = _block(list(range(1, 13)), year, hz, la), "year"
        elif _has(
            t,
            "12 meses",
            "doze meses",
            "12 months",
            "horizonte",
            "horizon",
            "ano todo",
            "ano inteiro",
            "full year",
            "proximo periodo",
        ) and not _has(t, "ultimos 12 meses", "last 12 months"):
            kind = "horizon"
    return sorted({_iso(d) for d in out}), kind


def extract_months(text: str, horizon: list[pd.Timestamp], last_actual: pd.Timestamp) -> list[str]:
    return _parse_period(text, horizon, last_actual)[0]


def _explicit_year(t: str) -> bool:
    """'dezembro de 2025', 'dez/25', '2026-03' - the user pinned the year."""
    return bool(re.search(r"(?<![\d.,])20\d{2}(?![\d%])", t) or re.search(r"[a-z]\s*/\s*\d{2}(?!\d)", t))


def _to_past(months: list[str], last_actual: pd.Timestamp) -> list[str]:
    """Shift future months back by whole years to their latest closed occurrence (<= last actual)."""
    la = pd.Timestamp(last_actual).to_period("M").to_timestamp()
    out = set()
    for m in months:
        d = pd.Timestamp(m)
        while d > la:
            d -= pd.DateOffset(years=1)
        out.add(_iso(d))
    return sorted(out)


def extract_dimension(text: str, exclude: set[str] | None = None) -> str | None:
    """First dimension word mentioned ("por região", "quais clientes"), skipping ``exclude``."""
    t = norm(text)
    best, pos = None, 10**9
    for dim, regs in _DIM_RES.items():
        if exclude and dim in exclude:
            continue
        for rx in regs:
            m = rx.search(t)
            if m and m.start() < pos:
                best, pos = dim, m.start()
    return best


# ----------------------------------------------------------------------------- entities
# PT / EN aliases for well-known hierarchy values (data values are Portuguese).
ALIASES: dict[str, list[list[str]]] = {
    "region": [
        ["sudeste", "southeast", "south east", "south-east"],
        ["sul", "south"],
        ["nordeste", "northeast", "north east", "north-east"],
        ["centro oeste", "centro-oeste", "centrooeste", "midwest", "mid-west", "center west", "central west"],
        ["norte", "north"],
    ],
    "channel": [
        ["varejo moderno", "modern trade", "modern retail", "autosservico"],
        ["atacarejo", "cash and carry", "cash & carry", "cash carry", "wholesale", "atacado"],
        ["varejo tradicional", "traditional trade", "traditional retail", "tradicional"],
        ["e-commerce", "ecommerce", "e commerce", "online", "digital", "comercio eletronico"],
        ["farma", "pharma", "pharmacy", "pharmacies", "farmacia", "farmacias", "drogaria", "drogarias", "drugstore"],
    ],
    "category": [
        ["bebidas", "bebida", "beverages", "beverage", "drinks"],
        ["snacks", "snack", "salgadinhos", "salgadinho"],
        ["cuidados pessoais", "cuidado pessoal", "personal care", "higiene pessoal"],
        ["limpeza", "cleaning", "home care", "household", "produtos de limpeza"],
    ],
}
STOP_TOKENS = _words("de do da dos das e o a os as com em no na para por the of and on in for to un ml kg lt")
GENERIC_TOKENS = _words(
    "rede supermercado supermercados mercado mercados hipermercado hipermercados atacado atacadista atacarejo "
    "distribuidora distribuicao online farmacia farmacias drogaria drogarias market conveniencia loja lojas "
    "comercio ltda grupo cia store stores varejo agua suco batata desodorante aromatizador pacote meta venda "
    "vendas total"
)
# Tokens that are also everyday words: only matched when capitalized, paired or with a context word.
AMBIGUOUS_TOKENS = _words(
    "horizonte certo ponto bom boa verde vila serra fresco brisa sabor vida presente zero festa classica "
    "classico sport men kit refil gas mais max"
)
_CONTEXT_WORDS = r"(?:cliente|clientes|rede|conta|customer|account|marca|brand|produto|product|sku|item)"
# Words in product names that do not identify a product line on their own.
NON_PRODUCT_TOKENS = _words("meta venda vendas total pacote linha kit refil classico classica unidade unidades")


@dataclass
class _Cand:
    dim: str
    value: str
    start: int
    end: int
    tokens: int
    exact: bool
    score: float


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", norm(s))


def _name_re(name: str) -> re.Pattern[str] | None:
    toks = _tokens(name)
    if not toks:
        return None
    return _bound(r"[\s\-/.]*".join(re.escape(x) for x in toks))


def _qtokens(t: str) -> list[tuple[str, int, int]]:
    toks = [(m.group(0), m.start(), m.end()) for m in re.finditer(r"[a-z0-9]+", t)]
    pairs = [(a[0] + b[0], a[1], b[2]) for a, b in itertools.pairwise(toks)]
    return toks + pairs


def _find_token(token: str, qtoks: list[tuple[str, int, int]], fuzzy: bool) -> tuple[int, int, bool] | None:
    for q, s, e in qtoks:
        if q == token:
            return s, e, True
    if fuzzy and len(token) >= 5:
        best: tuple[float, int, int] | None = None
        for q, s, e in qtoks:
            if len(q) < 4 or abs(len(q) - len(token)) > 2 or q[0] != token[0]:
                continue
            sm = difflib.SequenceMatcher(None, q, token)
            if sm.quick_ratio() < 0.85:
                continue
            r = sm.ratio()
            if r >= 0.85 and (best is None or r > best[0]):
                best = (r, s, e)
        if best:
            return best[1], best[2], False
    return None


def _capitalized(original: str, token: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(token[:1].upper())}{re.escape(token[1:])}", original) is not None


def _with_context(t: str, start: int) -> bool:
    return re.search(_CONTEXT_WORDS + r"\s+(?:\w+\s+){0,1}$", t[:start]) is not None


def _match_entities(text: str, members: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[int, int]]]:
    t = norm(text)
    original = _ascii(text)
    qtoks = _qtokens(t)
    cands: list[_Cand] = []
    alias_terms = {norm(a) for groups in ALIASES.values() for g in groups for a in g}
    all_names: dict[str, set[str]] = {}
    for dim in ("region", "channel", "category", "brand", "customer"):
        all_names[dim] = {norm(x) for x in members.get(dim, []) or []}
    other_dim_names = set().union(*all_names.values()) if all_names else set()

    # 1) Exact member names (any dimension) and SKU codes.
    for dim in ("region", "channel", "category", "brand", "customer"):
        for name in members.get(dim, []) or []:
            rx = _name_re(str(name))
            if rx is None:
                continue
            for m in rx.finditer(t):
                ntok = len(_tokens(str(name)))
                tok = _tokens(str(name))[0]
                if (
                    ntok == 1
                    and tok in AMBIGUOUS_TOKENS
                    and not (_capitalized(original, tok) or _with_context(t, m.start()))
                ):
                    continue
                cands.append(_Cand(dim, name, m.start(), m.end(), ntok, True, 100 + ntok))
    for sku in members.get("sku", []) or []:
        code = str(sku)
        digits = re.sub(r"\D", "", code)
        rx = _name_re(code)
        hits = list(rx.finditer(t)) if rx else []
        if not hits and len(digits) >= 4:
            hits = list(re.finditer(rf"(?<![\d.,]){digits}(?![\d%])", t))
        for m in hits:
            cands.append(_Cand("sku", code, m.start(), m.end(), 3, True, 200))

    # 2) PT / EN aliases (regions, channels, categories).
    for dim, groups in ALIASES.items():
        names = members.get(dim, []) or []
        for group in groups:
            gnorm = {norm(a) for a in group}
            target = next((n for n in names if norm(n) in gnorm or norm(n).replace("-", " ") in gnorm), None)
            if target is None:
                continue
            for alias in group:
                rx = _name_re(alias)
                if rx is None:
                    continue
                for m in rx.finditer(t):
                    cands.append(_Cand(dim, target, m.start(), m.end(), len(_tokens(alias)), True, 90))

    # 3) Partial / fuzzy customer names using distinctive tokens.
    customers = [str(c) for c in members.get("customer", []) or []]
    df: dict[str, int] = {}
    for c in customers:
        for tok in set(_tokens(c)):
            df[tok] = df.get(tok, 0) + 1
    for c in customers:
        toks = [
            x
            for x in _tokens(c)
            if len(x) >= 4
            and x not in STOP_TOKENS
            and x not in GENERIC_TOKENS
            and df.get(x, 0) == 1
            and x not in alias_terms
            and x not in (other_dim_names - {norm(c)})
            and not any(x in names for names in MONTHS.values())
        ]
        hits = []
        for tok in toks:
            f = _find_token(tok, qtoks, fuzzy=tok not in AMBIGUOUS_TOKENS)
            if f:
                hits.append((tok, *f))
        if not hits:
            continue
        strong = [h for h in hits if h[0] not in AMBIGUOUS_TOKENS]
        weak_ok = [
            h for h in hits if h[0] in AMBIGUOUS_TOKENS and (_capitalized(original, h[0]) or _with_context(t, h[1]))
        ]
        if not strong and not weak_ok:
            # Only everyday words ("Ponto Certo", "Vila Verde"): they must appear together, in order.
            in_order = [tok for tok in toks if any(h[0] == tok for h in hits)]
            if len(in_order) < 2 or not _bound(r"[\s\-]+".join(map(re.escape, in_order))).search(t):
                continue
        start, end = min(h[1] for h in hits), max(h[2] for h in hits)
        exact = all(h[3] for h in hits)
        cands.append(_Cand("customer", c, start, end, len(hits), exact, 50 + 10 * len(hits) + (5 if exact else 0)))

    # 4) Products (-> SKU) by distinctive product-name tokens, brand-aware.
    pmap = [(str(s), str(p)) for s, p in (members.get("product_map", []) or []) if isinstance(p, str)]
    brands = {norm(b) for b in members.get("brand", []) or []}
    pdf: dict[str, int] = {}
    ptoks: dict[str, list[str]] = {}
    for sku, prod in pmap:
        toks = [
            x
            for x in _tokens(prod)
            if len(x) >= 3 and x not in STOP_TOKENS and not re.search(r"\d", x) and x not in alias_terms
        ]
        ptoks[sku] = toks
        for tok in set(toks):
            pdf[tok] = pdf.get(tok, 0) + 1
    best_prod: list[tuple[float, str, int, int, int]] = []
    for sku, toks in ptoks.items():
        score, hits, unique_strong = 0.0, [], 0
        for tok in toks:
            f = _find_token(tok, qtoks, fuzzy=tok not in AMBIGUOUS_TOKENS and tok not in brands)
            if not f:
                continue
            hits.append(f)
            if tok in brands:
                score += 0.5
            else:
                score += 1.0 / pdf[tok]
                if pdf[tok] == 1 and tok not in AMBIGUOUS_TOKENS and tok not in GENERIC_TOKENS:
                    unique_strong += 1
        non_brand = [tok for tok in toks if tok not in brands]
        matched_non_brand = sum(1 for tok in non_brand if _find_token(tok, qtoks, fuzzy=False))
        if unique_strong >= 1 or matched_non_brand >= 2:
            best_prod.append((score, sku, min(h[0] for h in hits), max(h[1] for h in hits), len(hits)))
    if best_prod:
        best_prod.sort(reverse=True)
        top = best_prod[0]
        tied = [b for b in best_prod if b[0] == top[0]]
        if len(tied) == 1:
            cands.append(_Cand("sku", top[1], top[2], top[3], top[4], True, 60 + 10 * top[4]))
        else:  # "água mineral" -> two AquaViva SKUs: fall back to their common brand
            common = set.intersection(*(set(ptoks[b[1]]) & brands for b in tied))
            brand_names = {norm(b): str(b) for b in members.get("brand", []) or []}
            if len(common) == 1:
                cands.append(_Cand("brand", brand_names[common.pop()], top[2], top[3], top[4], True, 45))
    else:
        # A generic product word shared by one brand's SKUs only ("desodorante" -> Brisa, "suco" -> Frutalle).
        brand_names = {norm(b): str(b) for b in members.get("brand", []) or []}
        for q, s, e in qtoks:
            if len(q) < 4 or q in AMBIGUOUS_TOKENS or q in NON_PRODUCT_TOKENS or q in brands:
                continue
            owners = [sku for sku, toks in ptoks.items() if q in toks]
            sku_brands = {b for sku in owners for b in set(ptoks[sku]) & brands}
            if owners and len(sku_brands) == 1:
                cands.append(_Cand("brand", brand_names[sku_brands.pop()], s, e, 1, True, 35))
                break

    # 5) Brand fuzzy (e.g. "aqua viva", "frutale").
    for b in members.get("brand", []) or []:
        tok = norm(str(b)).replace(" ", "")
        if tok in AMBIGUOUS_TOKENS or len(tok) < 5:
            continue
        f = _find_token(tok, qtoks, fuzzy=True)
        if f:  # exact compound ("aqua viva") or fuzzy ("frutale")
            cands.append(_Cand("brand", str(b), f[0], f[1], 1, False, 40))

    # Resolve overlaps: SKU codes first, then longer / more specific matches; one value per dimension.
    # ("Nordeste Atacadista" -> customer, not region; "NutriBar Proteína" -> SKU, not just the brand.)
    filters: dict[str, Any] = {}
    spans: list[tuple[int, int]] = []
    for c in sorted(cands, key=lambda c: (c.score < 200, -(c.end - c.start), -c.score)):
        if c.dim in filters or any(not (c.end <= s or c.start >= e) for s, e in spans):
            continue
        filters[c.dim] = c.value
        spans.append((c.start, c.end))
    return filters, spans


def _mask(t: str, spans: list[tuple[int, int]] | None) -> str:
    for s, e in spans or []:
        t = t[:s] + " " * (e - s) + t[e:]
    return t


def extract_entities(text: str, members: dict[str, Any]) -> dict[str, Any]:
    """Hierarchy members mentioned in the text, e.g. {"customer": "Atlas Hipermercados", "region": "Sul"}."""
    return _match_entities(text, members)[0]


# ----------------------------------------------------------------------------- levers
NUMBER_WORDS = {
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "quinze": 15,
    "vinte": 20,
    "vinte e cinco": 25,
    "trinta": 30,
    "quarenta": 40,
    "cinquenta": 50,
    "one": 1,
    "two": 2,
    "three": 3,
    "five": 5,
    "ten": 10,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "fifty": 50,
}


def _number_near(t: str, words: list[str]) -> float | None:
    """Percentage closest to a lever word (prefers the one right after it)."""
    for w in words:
        for m in re.finditer(rf"(?<![a-z]){re.escape(w)}", t):
            after = t[m.end() : m.end() + 40]
            before = t[max(0, m.start() - 35) : m.start()]
            for seg, is_after in ((after, True), (before, False)):
                found = list(
                    re.finditer(r"([+-]?\d+(?:[.,]\d+)?)\s*(?:%|por\s*cento|percent|pontos percentuais|p\.?p\.?)", seg)
                )
                if not found:
                    continue
                n = found[0] if is_after else found[-1]
                v = float(n.group(1).replace(",", ".")) / 100
                # "aumentar 10% de distribuição" / "perdermos 10% de distribuição": the verb sits before the number.
                between = (
                    seg[: n.start()]
                    if is_after
                    else seg[n.end() :] + " " + re.split(r",|;| e | and ", seg[: n.start()])[-1]
                )
                # Words right before the lever ("reduzir o preço"), stopping at another figure or conjunction.
                prefix = re.split(r"\d+(?:[.,]\d+)?\s*%|,|;| e | and ", before)[-1]
                if v > 0 and (re.search(_DOWN, between + " " + prefix) or w in ("desconto", "descontos", "discount")):
                    v = -v
                return v
    return None


def extract_levers(text: str, spans: list[tuple[int, int]] | None = None) -> dict[str, Any]:
    t = _mask(norm(text), spans)  # hide entity names ("Litoral Market", "Vila Verde Mercados")
    # "dez por cento" -> "10%"
    t = re.sub(
        r"(?<![a-z])(" + "|".join(NUMBER_WORDS) + r")\s+(?=por\s*cento|%|percent)",
        lambda m: f"{NUMBER_WORDS[m.group(1)]} ",
        t,
    )
    levers: dict[str, Any] = {}
    for lever, words in LEVER_WORDS.items():
        if lever in ("promotion", "merchandising"):
            if _has(t, *words):
                levers[lever] = True
            continue
        if lever == "market_growth" and not _has(t, *words):
            continue
        if _has(t, *words) or any(re.search(rf"(?<![a-z]){re.escape(w)}", t) for w in words if " " not in w):
            v = _number_near(t, words)
            if v is not None:
                levers[lever] = v
    # "e se as vendas crescerem 10%?" -> generic market growth when no lever is named.
    numeric = [k for k, v in levers.items() if not isinstance(v, bool)]
    if not numeric and _SIMULATION.search(t):
        m = re.search(r"([+-]?\d+(?:[.,]\d+)?)\s*(?:%|por\s*cento)", t)
        if (
            m
            and (re.search(_UP_GENERIC, t) or re.search(_DOWN, t))
            and re.search(r"(?<![a-z])(vend|demand|volume|sales|mercado|market|cresc|grow|consum)", t)
        ):
            v = float(m.group(1).replace(",", ".")) / 100
            ctx = t[max(0, m.start() - 40) : m.end() + 25]
            if v > 0 and re.search(_DOWN, ctx) and not re.search(r"(cresc|aument|grow|increas)", ctx):
                v = -v
            levers["market_growth"] = v
    return levers


# ----------------------------------------------------------------------------- scoring
def _hits(t: str, regs: list[re.Pattern[str]]) -> int:
    return sum(1 for r in regs if r.search(t))


def _metric(t: str) -> str | None:
    best: tuple[int, str] | None = None
    for rx, code in _METRIC_RES:
        m = rx.search(t)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), code)
    return best[1] if best else None


def score_intents(
    t: str,
    *,
    has_period: bool,
    has_entity: bool,
    levers: dict[str, Any],
    dim_free: bool,
    dim: str | None = None,
) -> dict[str, float]:
    """Weighted pattern score per intent (``t`` is normalized text)."""
    s = {name: sum(w for rx, w in pats if rx.search(t)) for name, pats in PATTERNS.items()}

    over, under = _hits(t, _OVER_RE), _hits(t, _UNDER_RE)
    ranking = _hits(t, _RANK_RE) > 0
    acc_words = _hits(t, _ACC_RES)
    bias_words = _hits(t, _BIAS_RES)
    rank_boost = (2 if ranking else 0) + (1 if dim_free else 0)
    plan_word = bool(_BUDGET_WORD.search(t) or _TARGET_WORD.search(t))

    # Accuracy / bias rankings vs single-value lookups.
    s["worst_accuracy"] = (2 + rank_boost) if acc_words else 0
    if not (acc_words or bias_words or over or under or plan_word) and dim_free and _WORST_WORD.search(t):
        s["worst_accuracy"] = 2 + rank_boost  # "top 5 piores SKUs"
    s["bias_ranking"] = (
        ((2 if bias_words else 0) + (4 if over or under else 0) + rank_boost) if (bias_words or over or under) else 0
    )
    if acc_words or bias_words or over or under:
        s["metric_lookup"] += 2 if (acc_words or bias_words) else 1
        if has_entity and not ranking:
            s["metric_lookup"] += 4
        elif (over or under) and not ranking and not dim_free:
            s["metric_lookup"] += 4  # "o forecast está superestimado?" -> the portfolio bias
        s["metric_lookup"] -= rank_boost
    else:
        s["metric_lookup"] = 0

    # What-if needs levers (or at least an explicit simulation phrase).
    if levers:
        s["what_if"] += 4 + (1 if _CONDITIONAL.search(t) else 0)
    else:
        s["what_if"] *= 0.5

    if _TARGET_WORD.search(t):
        s["target_feasibility"] += (
            (2 if has_period else 0) + (1 if has_entity else 0) + (1 if _STATUS_WORD.search(t) else 0)
        )
    else:
        s["target_feasibility"] = min(s["target_feasibility"], 1)

    fv_word = _hits(t, _FV_WORDS) > 0
    if has_period:
        s["forecast_value"] += 1 + (2 if fv_word else 0)
        s["forecast_drivers"] += 1 if _DRIVER_WORD.search(t) else 0
        if has_entity and _STATUS_WORD.search(t):  # "como está o Atlas em dezembro?"
            s["forecast_value"] += 2
    if has_entity and fv_word:
        s["forecast_value"] += 1

    # "por que dezembro cresce?" / "por que a previsão de dezembro é tão alta?" -> drivers.
    if _WHY.search(t) and not (plan_word or acc_words or bias_words or _MODEL_WORD.search(t)):
        s["forecast_drivers"] += 2

    if _BUDGET_WORD.search(t):
        s["budget_gap"] += 1 if _WHERE.search(t) else 0
    if _MODEL_WORD.search(t):
        s["forecast_drivers"] = max(0.0, s["forecast_drivers"] - 3)  # "por que o modelo escolhido foi ETS?"
        if has_entity:
            s["best_model"] += 2
    else:
        s["best_model"] = min(s["best_model"], 1)
        if not _CHAMPION_WORD.search(t):
            s["model_distribution"] = 0
    if not _FVA_CORE.search(t):
        s["fva_overrides"] = min(s["fva_overrides"], 1)
    # "quais planejadores / eventos pioram o forecast?" -> FVA of the overrides.
    if dim in ("planner", "event_type") and _QUALITY.search(t):
        s["fva_overrides"] += 5

    if has_entity:
        s["entity_overview"] += 2 - (2 if has_period else 0)
        others = max(v for k, v in s.items() if k != "entity_overview")
        if others < THRESHOLD:
            s["entity_overview"] += 2
    else:
        s["entity_overview"] = 0
    return {k: round(float(v), 2) for k, v in s.items()}


def parse(text: str, members: dict[str, Any], horizon: list[pd.Timestamp], last_actual: pd.Timestamp) -> Intent | None:
    t = norm(text)
    lang = detect_language(text)
    filters, spans = _match_entities(text, members)
    masked = _mask(t, spans)  # "Rede Horizonte" is a customer, not the forecast horizon
    months, period = _parse_period(masked, horizon, last_actual)
    levers = extract_levers(text, spans)
    dim = extract_dimension(masked, exclude=set(filters))
    dim_free = dim is not None and dim not in filters
    has_period = bool(months) or period is not None
    scores = score_intents(
        masked, has_period=has_period, has_entity=bool(filters), levers=levers, dim_free=dim_free, dim=dim
    )
    metric = _metric(masked)

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], PRIORITY.index(kv[0])))
    name, best = ranked[0]
    if best < THRESHOLD:
        if filters:
            name = "entity_overview"
        elif has_period:
            name = "forecast_value"
        elif metric:
            name = "metric_lookup"
        elif best > 0:
            pass
        elif levers:
            name = "what_if"
        elif dim:
            name = "summary"
        else:
            return None

    # Month names resolve to the forecast horizon by default. Accuracy / bias questions and past-tense
    # questions ("quanto vendemos em setembro?") refer to the latest closed occurrence instead.
    past_question = _PAST_CUE.search(masked) or (name == "target_feasibility" and _PAST_TARGET.search(masked))
    if (
        months
        and period in ("month", "quarter", "semester")
        and not _explicit_year(masked)
        and not _RELATIVE.search(masked)
        and (name in BACKTEST_INTENTS or (name in ("forecast_value", "target_feasibility") and past_question))
    ):
        months = _to_past(months, last_actual)
    # "batemos a meta de agosto?" about a closed month: actual vs target, not a feasibility assessment.
    if name == "target_feasibility" and months and max(months) <= _iso(pd.Timestamp(last_actual)):
        name = "forecast_value"

    direction = None
    if name == "bias_ranking":
        over, under = _hits(t, _OVER_RE), _hits(t, _UNDER_RE)
        # "qual cliente tem o maior viés?" -> largest absolute bias ("abs"); otherwise over / under.
        direction = "under" if under and not over else "over" if over else "abs"
    elif name == "worst_accuracy":
        direction = "best" if _BEST_WORD.search(t) and not _has(t, "pior", "piores", "worst") else "worst"

    if name in ("bias_ranking",):
        dim = dim or "customer"
    elif name == "worst_accuracy":
        dim = dim or "sku"
    elif name == "budget_gap":
        dim = dim or ("sku" if "customer" in filters else "customer")
    elif name == "fva_overrides":
        dim = dim if dim in ("planner", "event_type", "customer") else None

    top = max(scores.get(name, 0.0), 0.0)
    runner = max([v for k, v in scores.items() if k != name] or [0.0])
    return Intent(
        name=name,
        language=lang,
        months=months,
        dimension=dim,
        filters=filters,
        levers=levers,
        direction=direction,
        metric=metric,
        period=period or ("month" if months else None),
        confidence=round(max(0.3, min(1.0, 0.4 + 0.08 * top + 0.05 * (top - runner))), 2),
        source="rules",
        scores={k: v for k, v in scores.items() if v > 0},
    )
