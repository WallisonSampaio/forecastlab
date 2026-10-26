"""Root cause and recommended actions of the deep dive (spec §4.4).

* ``plan_tags``   – up to 2 tags explaining a plan deviation (node, breakdown member or series), primary first.
* ``cell_cause``  – exactly ONE forecast-error cause per backtest cell (Cliente × SKU × mês), by priority,
  with direction guards: a driver explains a cell only when the sign of the error (e = F − A) is the
  one that driver produces (a stock-out depresses sales -> over-forecast; a promotion lifts them ->
  under-forecast; more distribution or a lower price -> under-forecast).
* ``cell_evidence`` – the pt-BR evidence line of a backtest cell (drawer "Evidências").
* ``actions_for`` – the action buttons (``ActionSpec``) of a tag/cause, with their prefill.

Every threshold is a named module constant (unit-tested at the boundaries) and every label is pt-BR.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import pandas as pd

from app import db
from app.services import ptbr
from app.services.context import PlanningContext

from . import common, narrative

# ---------------------------------------------------------------------------------------- thresholds
TAG_GROWTH_GAP = 0.08  # |g_plan − g_fc| that makes a growth premise "optimistic" / momentum "not budgeted"
EFFECT_SHARE = 0.40  # an effect explains a deviation when |effect| ≥ 40% of |V| (same sign)
UNCERTAIN_BAND = (0.35, 0.65)  # prob_hit band where a small deviation is "within the uncertainty"
UNCERTAIN_VPCT = 0.05  # ... and only when |V%| < 5%
STRUCT_SHARE = 0.30  # share of X^r in declining/structural series that tags a "structural fall"
STRUCT_EVENTS = {"Perda de cliente", "Perda de distribuição", "Deslistagem"}
CHALLENGE_SHARE = 0.50  # fc_tg: Meta − Orçamento ≥ 50% of |V| -> "Meta acima do orçamento"
DIST_PP = 5.0  # distribution change (p.p. vs the backtest origin) that counts as a driver
PRICE_TOL = 0.05  # price change vs the reference price that counts as a driver
TS_LIMIT = 4.5  # |tracking signal| of persistent bias (same as alerts.engine)
NOISE_Z = 1.2815515655446004  # |e| ≤ Z90 · RMSE = inside the P10–P90 band
BREAK_WINDOW_MONTHS = 12  # a structural break explains the cells of the 12 months after it
ADJ_TOL = 0.005  # ac_cs: an adjustment "worsened" the cell when it adds > 0,5% of A to |e| (= fva.TOLERANCE)
HIGH_ERROR = 0.35  # forecast exception: series WMAPE ...
HIGH_BIAS = 0.15  # ... or |bias| ...
MIN_REV_SHARE = 0.001  # ... (WMAPE only for series with ≥ 0,1% of the company consensus revenue)
VOLATILE_TYPES = {"Intermittent", "Volatile", "Short History", "Inactive"}
DECLINE_TYPES = {"Declining", "Structural Change", "Inactive"}
PROMO_UPLIFT_CLIP = (0.05, 0.50)  # create_override prefill: series promo lift clipped to this range
DEFAULT_UPLIFT = {"Promoção": 0.25, "Merchandising": 0.12}  # services.overrides.EVENT_LIBRARY defaults
STRUCT_UPLIFT = -0.10  # queda_estrutural prefill ("Perda de distribuição")
_EPS = 1e-9  # boundary tolerance: thresholds are inclusive despite float noise (0,18 − 0,10 ≥ 0,08)

# ---------------------------------------------------------------------------------------- vocabularies
GROUP_LABEL = {
    "controllable": "Controlável pelo processo",
    "inherent": "Inerente à demanda",
    "unexplained": "Sem causa identificada",
}
GROUP_ORDER = ("controllable", "inherent", "unexplained")

# Forecast cell causes, in priority order: code -> (label, group).
CAUSES: dict[str, tuple[str, str]] = {
    "ajuste_piorou": ("Ajuste comercial piorou o forecast", "controllable"),
    "ruptura": ("Ruptura de estoque", "controllable"),
    "promocao": ("Promoção não antecipada", "controllable"),
    "merchandising": ("Merchandising não antecipado", "controllable"),
    "distribuicao": ("Mudança de distribuição", "controllable"),
    "preco": ("Mudança de preço", "controllable"),
    "patamar": ("Mudança de patamar", "controllable"),
    "volatilidade": ("Demanda intermitente ou volátil", "inherent"),
    "ruido": ("Variação normal (dentro da faixa P10–P90)", "inherent"),
    "nao_explicado": ("Sem causa identificada", "unexplained"),
}

# Plan tags, in rule order: code -> (label when V < 0, label when V ≥ 0).
PLAN_TAGS: dict[str, tuple[str, str]] = {
    "desafio_comercial": ("Meta acima do orçamento", "Meta acima do orçamento"),
    "sem_orcamento": ("Sem orçamento", "Sem orçamento"),
    "premissa_otimista": ("Premissa de crescimento otimista", "Premissa de crescimento otimista"),
    "momentum_nao_orcado": ("Crescimento não orçado", "Crescimento não orçado"),
    "queda_estrutural": ("Queda estrutural", "Queda estrutural"),
    "preco": ("Preço abaixo do orçado", "Preço acima do orçado"),
    "mix": ("Mix desfavorável", "Mix favorável"),
    "evento": ("Eventos comerciais", "Eventos comerciais"),
    "incerteza": ("Dentro da incerteza", "Dentro da incerteza"),
    "volume": ("Volume abaixo do orçado", "Volume acima do orçado"),
}

MONITOR = "Monitorar no próximo ciclo."

# Recommended action per plan tag / forecast cause. Keys prefixed "cause:" disambiguate the cause
# codes that share a name with a plan tag ("preco").
ACTIONS: dict[str, str] = {
    "premissa_otimista": "Revisar a premissa de crescimento do orçamento com o Key Account e o FP&A.",
    "momentum_nao_orcado": "Garantir abastecimento para a demanda adicional e avaliar elevar a meta.",
    "preco": "Validar a política de preço orçada com Pricing/FP&A.",
    "mix": "Revisar mix e sortimento com Trade Marketing.",
    "evento": "Confirmar os eventos comerciais com o time da conta.",
    "queda_estrutural": "Plano de recuperação ou ajuste do orçamento.",
    "desafio_comercial": "Decidir: recalibrar a meta ou comprometer alavancas.",
    "sem_orcamento": MONITOR,
    "promocao": "Cadastrar a promoção de {mes} como ajuste comercial.",
    "merchandising": "Cadastrar a ação de merchandising de {mes} como ajuste comercial.",
    "ruptura": "Erro causado por ruptura: tratar abastecimento e estoque de segurança — não é falha do modelo.",
    "distribuicao": "Atualizar a premissa de distribuição e simular.",
    "cause:preco": "Alinhar a política de preço com o planejamento de demanda.",
    "patamar": "Viés persistente: encurtar a janela de treino, registrar a mudança de patamar ou promover o desafiante.",
    "ajuste_piorou": "Revisar a regra de ajustes manuais (FVA negativo).",
    "volatilidade": "Gerir com estoque de segurança, não com precisão de ponto.",
    "ruido": MONITOR,
    "incerteza": MONITOR,
    "volume": MONITOR,
    "nao_explicado": MONITOR,
}

# ActionSpec button labels (pt-BR).
ACTION_LABEL = {
    "open_series": "Abrir ficha",
    "create_override": "Criar ajuste comercial",
    "simulate": "Simular cenário",
    "ask_ai": "Perguntar à IA",
    "open_fva": "Ver valor dos ajustes (FVA)",
    "open_workspace": "Abrir no workspace",
}
FVA_ROUTE = "/app/models?tab=fva"

# Primary buttons per tag/cause (spec §4.4 "Actions"); ask_ai is appended by ``actions_for``.
PRIMARY_ACTIONS: dict[str, tuple[str, ...]] = {
    "premissa_otimista": ("ask_ai", "simulate"),
    "momentum_nao_orcado": ("simulate",),
    "preco": ("ask_ai",),
    "mix": ("ask_ai",),
    "evento": ("open_series",),
    "queda_estrutural": ("create_override",),
    "desafio_comercial": ("simulate",),
    "promocao": ("create_override",),
    "merchandising": ("create_override",),
    "ruptura": ("open_series",),
    "distribuicao": ("simulate",),
    "patamar": ("open_workspace",),
    "ajuste_piorou": ("open_fva",),
}


# ---------------------------------------------------------------------------------------- helpers
def _num(v: Any) -> float | None:
    """float(v) or None for None/NaN/non-numeric."""
    if v is None or isinstance(v, bool | str):
        return float(v) if isinstance(v, bool) else None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _flag(v: Any) -> bool:
    """Truthy numeric flag (> 0); None/NaN = False."""
    f = _num(v)
    return f is not None and f > 0


def _sign(v: float) -> int:
    return (v > 0) - (v < 0)


def tag(code: str, variance: float | None = None) -> dict[str, str]:
    """{code, label} of a plan tag; the label follows the sign of the variance (V < 0 = adverse)."""
    adverse, favourable = PLAN_TAGS[code]
    return {"code": code, "label": adverse if (variance or 0.0) < 0 else favourable}


def cause_tag(code: str) -> dict[str, str]:
    """{code, label, group, group_label} of a forecast cause."""
    label, group = CAUSES[code]
    return {"code": code, "label": label, "group": group, "group_label": GROUP_LABEL[group]}


def recommended_action(code: str, *, cause: bool = False, mes: str = "") -> dict[str, str]:
    """{code, label} with the recommended action text for a plan tag or (``cause=True``) a forecast cause."""
    key = f"cause:{code}" if cause and f"cause:{code}" in ACTIONS else code
    text = ACTIONS.get(key, MONITOR)
    if "{mes}" in text and not mes:
        text = text.replace(" de {mes}", "")
    return {"code": code, "label": text.format(mes=mes)}


# ---------------------------------------------------------------------------------------- plan tags
def _effect(facts: Mapping[str, Any], name: str) -> float | None:
    eff = facts.get("effects")
    if isinstance(eff, Mapping) and name in eff:
        return _num(eff.get(name))
    return _num(facts.get(name))


def plan_tags(facts: Mapping[str, Any], cmp: str) -> list[dict[str, str]]:
    """Plan tags of a node/member/series, at most 2, primary first (spec §4.4 "Plan tags").

    ``facts`` keys: ``variance`` (V), ``variance_pct``, ``x`` (X), ``p`` (P), ``g_plan``, ``g_fc``,
    ``challenge`` (fc_tg: Meta − Orçamento), ``effects`` {volume, mix, price, events} (flat keys are also
    accepted), ``prob_hit`` (fc_*), ``decline_share`` (share of X^r in DECLINE_TYPES series) and
    ``structural_event`` (bool: an override in M with event_type ∈ STRUCT_EVENTS).
    Rules are evaluated in order; 'volume' is the fallback when no rule holds.
    """
    v = _num(facts.get("variance")) or 0.0
    x = _num(facts.get("x")) or 0.0
    p = _num(facts.get("p")) or 0.0
    vpct = _num(facts.get("variance_pct"))
    g_plan, g_fc = _num(facts.get("g_plan")), _num(facts.get("g_fc"))
    out: list[str] = []

    def explains(effect: float | None) -> bool:
        return (
            effect is not None
            and v != 0
            and _sign(effect) == _sign(v)
            and abs(effect) >= EFFECT_SHARE * abs(v) - _EPS * max(1.0, abs(v))
        )

    challenge = _num(facts.get("challenge"))
    if cmp == "fc_tg" and v < 0 and challenge is not None and challenge >= CHALLENGE_SHARE * abs(v) - _EPS:
        out.append("desafio_comercial")
    if p == 0 and x > 0:
        out.append("sem_orcamento")
    if v < 0 and g_plan is not None and g_fc is not None and g_plan - g_fc >= TAG_GROWTH_GAP - _EPS:
        out.append("premissa_otimista")
    if v > 0 and g_plan is not None and g_fc is not None and g_fc - g_plan >= TAG_GROWTH_GAP - _EPS:
        out.append("momentum_nao_orcado")
    decline = _num(facts.get("decline_share")) or 0.0
    if v < 0 and (decline >= STRUCT_SHARE - _EPS or bool(facts.get("structural_event"))):
        out.append("queda_estrutural")
    if explains(_effect(facts, "price")):
        out.append("preco")
    if explains(_effect(facts, "mix")):
        out.append("mix")
    if explains(_effect(facts, "events")):
        out.append("evento")
    prob = _num(facts.get("prob_hit"))
    lo, hi = UNCERTAIN_BAND
    if (
        cmp in ("fc_pl", "fc_tg")
        and prob is not None
        and lo - _EPS <= prob <= hi + _EPS
        and vpct is not None
        and abs(vpct) < UNCERTAIN_VPCT
    ):
        out.append("incerteza")
    codes = out[:2] or ["volume"]
    return [tag(c, v) for c in codes]


# ---------------------------------------------------------------------------------------- cell cause
def _break_in_window(row: Mapping[str, Any]) -> bool:
    if not row.get("structural_break") or pd.isna(row.get("structural_break")):
        return False
    brk, t = row.get("break_date"), row.get("date")
    if brk is None or t is None or pd.isna(brk) or pd.isna(t):
        return False
    brk, t = pd.Timestamp(brk), pd.Timestamp(t)
    return t - pd.DateOffset(months=BREAK_WINDOW_MONTHS) <= brk <= t


def _price_change(row: Mapping[str, Any]) -> float | None:
    """price_t / price_ref − 1 (None when either price is missing or ≤ 0)."""
    price, ref = _num(row.get("price")), _num(row.get("price_ref"))
    if price is None or ref is None or price <= 0 or ref <= 0:
        return None
    return price / ref - 1


def _dist_change(row: Mapping[str, Any]) -> float | None:
    """dist_t − dist_origin in p.p. (None when either is missing)."""
    d, d0 = _num(row.get("distribution")), _num(row.get("distribution_origin"))
    return None if d is None or d0 is None else d - d0


def cell_cause(row: Mapping[str, Any], cmp: str) -> str:
    """Exactly one CAUSES code per backtest cell, by priority with direction guards (spec §4.4).

    ``row`` keys: ``e`` (F − A, units), ``actual``, ``forecast`` (F of the lens), ``forecast_stat``, ``adj``
    (ac_cs), ``stockout``, ``promotion``, ``merchandising_event``, ``distribution``, ``distribution_origin``,
    ``price``, ``price_ref``, ``structural_break``, ``break_date``, ``date``, ``ts``, ``series_type``, ``rmse``.
    Missing drivers (NaN) never trigger a rule.
    """
    e = _num(row.get("e")) or 0.0
    a = _num(row.get("actual")) or 0.0
    adj = _num(row.get("adj")) or 0.0
    no_adj = cmp != "ac_cs" or adj == 0

    # 1. ac_cs: the commercial adjustment made the cell worse than the statistical forecast
    if cmp == "ac_cs" and adj != 0:
        f_cons = _num(row.get("forecast")) or 0.0
        f_stat = _num(row.get("forecast_stat")) or 0.0
        if abs(f_cons - a) > abs(f_stat - a) + ADJ_TOL * a:
            return "ajuste_piorou"
    # 2. stock-out depresses sales -> over-forecast
    if _flag(row.get("stockout")) and e > 0:
        return "ruptura"
    # 3–4. promotion / merchandising lift sales -> under-forecast (ac_cs: only when nobody adjusted)
    if _flag(row.get("promotion")) and e < 0 and no_adj:
        return "promocao"
    if _flag(row.get("merchandising_event")) and e < 0 and no_adj:
        return "merchandising"
    # 5. more distribution -> under-forecast; less -> over-forecast
    dd = _dist_change(row)
    if dd is not None and abs(dd) >= DIST_PP - _EPS and _sign(e) == -_sign(dd):
        return "distribuicao"
    # 6. regular-price change: price up -> over-forecast; price down -> under-forecast
    dp = _price_change(row)
    if not _flag(row.get("promotion")) and dp is not None and abs(dp) >= PRICE_TOL - _EPS and _sign(e) == _sign(dp):
        return "preco"
    # 7. level shift: structural break in the last 12 months or persistent bias
    ts = _num(row.get("ts")) or 0.0
    if _break_in_window(row) or abs(ts) >= TS_LIMIT - _EPS:
        return "patamar"
    # 8. inherently erratic demand
    if row.get("series_type") in VOLATILE_TYPES:
        return "volatilidade"
    # 9. inside the P10–P90 band of the model
    rmse = _num(row.get("rmse")) or 0.0
    if abs(e) <= NOISE_Z * rmse + _EPS:
        return "ruido"
    return "nao_explicado"


def cell_evidence(row: Mapping[str, Any]) -> str:
    """pt-BR evidence of a backtest cell: its true conditions joined with " · " (spec §4.3.3 series).

    Example: "Promoção ativa · sem ajuste registrado · preço -12,0% vs referência".
    ``row`` keys: those of ``cell_cause`` plus ``hist_adj`` (Σ historical adjustment of the cell).
    """
    parts: list[str] = []
    promo, merch = _flag(row.get("promotion")), _flag(row.get("merchandising_event"))
    if promo:
        parts.append("Promoção ativa")
    if merch:
        parts.append("Merchandising ativo")
    hist_adj = _num(row.get("hist_adj"))
    if hist_adj is None:
        hist_adj = _num(row.get("adj")) or 0.0
    if (promo or merch) and hist_adj == 0:
        parts.append("sem ajuste registrado")
    if _flag(row.get("stockout")):
        parts.append("Ruptura no mês")
    dp = _price_change(row)
    if dp is not None and abs(dp) >= PRICE_TOL - _EPS:
        parts.append(f"preço {ptbr.pct(dp, 1, signed=True)} vs referência")
    dd = _dist_change(row)
    if dd is not None and abs(dd) >= DIST_PP - _EPS:
        parts.append(f"distribuição {ptbr.dec(dd, 1, signed=True)} p.p. vs a origem")
    if _break_in_window(row):
        parts.append(f"mudança de patamar em {ptbr.month_label(row.get('break_date'))}")
    e, rmse = _num(row.get("e")) or 0.0, _num(row.get("rmse")) or 0.0
    if abs(e) > NOISE_Z * rmse + _EPS:
        parts.append("erro acima de 1,28 × o erro típico")
    if not parts:
        return "Sem fator registrado no mês"
    text = " · ".join(parts)
    return text[0].upper() + text[1:]


# ---------------------------------------------------------------------------------------- actions
def _profiles(ctx: PlanningContext) -> pd.DataFrame:
    """series_profiles of the active run (promo_lift, structural break), indexed by series_id (cached)."""

    def build() -> pd.DataFrame:
        cols = ["series_id", "promo_lift", "structural_break", "break_index"]
        if not ctx.run_id:
            return pd.DataFrame(columns=cols).set_index("series_id")
        df = db.query_df(
            "SELECT series_id, promo_lift, structural_break, break_index FROM series_profiles WHERE run_id = ?",
            [ctx.run_id],
        )
        return df.drop_duplicates("series_id").set_index("series_id")

    return common.cached(ctx, "series_profiles", build=build)


def promo_prefill_date(ctx: PlanningContext, month: Any) -> str | None:
    """Same calendar month next year when it falls in the horizon H, else H[0] ('YYYY-MM-DD')."""
    h = pd.DatetimeIndex(ctx.future_dates)
    if len(h) == 0:
        return None
    target = None
    if month is not None and not pd.isna(month):
        nxt = pd.Timestamp(month).to_period("M").to_timestamp() + pd.DateOffset(years=1)
        target = nxt if nxt in h else None
    return f"{(target if target is not None else h[0]):%Y-%m-%d}"


def promo_uplift(ctx: PlanningContext, series_id: str | None, event_type: str) -> float:
    """Promotion: the series' ``promo_lift`` clipped to PROMO_UPLIFT_CLIP when > 0; else the library default."""
    if event_type == "Promoção" and series_id:
        prof = _profiles(ctx)
        lift = _num(prof["promo_lift"].get(series_id)) if series_id in prof.index else None
        if lift is not None and lift > 0:
            lo, hi = PROMO_UPLIFT_CLIP
            return float(min(max(lift, lo), hi))
    return DEFAULT_UPLIFT.get(event_type, DEFAULT_UPLIFT["Promoção"])


def _scope(entity: Mapping[str, Any], dims: tuple[str, ...] = ("region", "channel", "customer", "category", "sku")):
    return {d: entity[d] for d in dims if entity.get(d)}


def _question(entity: Mapping[str, Any]) -> str | None:
    """'Perguntar à IA' question (narrative.ai_question; probed wordings only).

    A series entity asks about its customer in the plan lens ("Como está o cliente {c}?") and about
    "{cliente} {sku}" in the forecast lens ("Qual o WMAPE de {c} {sku}?" -> metric_lookup on both)."""
    cmp = entity.get("cmp") or "fc_pl"
    level, member = entity.get("level"), entity.get("member")
    if level == "series":
        if cmp in common.CMP_FORECAST and entity.get("customer") and entity.get("sku"):
            level, member = "sku", f"{entity['customer']} {entity['sku']}"
        elif entity.get("customer"):
            level, member = "customer", entity["customer"]
        else:
            level, member = None, None
    return narrative.ai_question(cmp, level, member, entity)


_FILTER_DIMS = ("region", "channel", "customer", "category", "brand", "sku")


def _ask_filters(entity: Mapping[str, Any]) -> dict[str, Any]:
    """Filters sent with 'Perguntar à IA': the drill ``path`` plus the focused member (a dimension member,
    or customer + sku for a series). Without ``path``, the entity's own dimensions."""
    path = entity.get("path")
    if not isinstance(path, Mapping):
        return _scope(entity, _FILTER_DIMS)
    filters = {k: v for k, v in path.items() if v}
    level, member = entity.get("level"), entity.get("member")
    if level in _FILTER_DIMS and member:
        filters[level] = member
    elif level == "series":
        filters.update(_scope(entity, ("customer", "sku")))
    return filters


def _action(kind: str, prefill: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": kind, "label": ACTION_LABEL[kind]}
    if prefill is not None:
        out["prefill"] = prefill
    return out


def _build(kind: str, code: str, entity: Mapping[str, Any], ctx: PlanningContext) -> dict[str, Any] | None:
    customer, sku, sid = entity.get("customer"), entity.get("sku"), entity.get("series_id")
    if kind == "ask_ai":
        q = _question(entity)
        if not q:
            return None
        return _action("ask_ai", {"question": q, "filters": _ask_filters(entity)})
    if kind in ("open_series", "open_workspace"):
        return _action(kind, {"series_id": sid}) if sid else None
    if kind == "open_fva":
        return _action("open_fva", {"route": FVA_ROUTE})
    if kind == "simulate":
        # a series is scoped by customer + SKU (spec §4.4 'distribuicao'); a node by its drill path + member
        scope = _scope(entity, ("customer", "sku")) if sid else _scope(entity)
        prefill: dict[str, Any] = {"scope": scope, **scope}
        if code == "distribuicao":
            dd = _num(entity.get("dist_change"))
            if dd is not None:
                prefill["distribution_change_pct"] = round(dd / 100.0, 4)
        elif _num(entity.get("distribution_change_pct")) is not None:
            prefill["distribution_change_pct"] = float(entity["distribution_change_pct"])
        return _action("simulate", prefill)
    if kind == "create_override":
        if not customer:
            return None
        if code == "queda_estrutural":
            event, uplift = "Perda de distribuição", STRUCT_UPLIFT
            date = promo_prefill_date(ctx, None)
            comment = "Sugerido pelo deep dive: queda estrutural"
        else:
            event = "Merchandising" if code == "merchandising" else "Promoção"
            uplift = promo_uplift(ctx, sid, event)
            month = entity.get("date")
            date = promo_prefill_date(ctx, month)
            cause_label = (entity.get("cause_label") or CAUSES.get(code, (event,))[0]).lower()
            when = f" em {ptbr.month_label(month)}" if month is not None and not pd.isna(month) else ""
            comment = f"Sugerido pelo deep dive: {cause_label}{when}"
        return _action(
            "create_override",
            {
                "customer": customer,
                "sku": sku or None,
                "date": date,
                "event_type": event,
                "uplift_pct": round(float(uplift), 4),
                "comment": comment,
            },
        )
    return None


def actions_for(code: str, entity: Mapping[str, Any], ctx: PlanningContext) -> list[dict[str, Any]]:
    """ActionSpec list ({kind, label, prefill?}) for a tag/cause code and an entity, primary first.

    ``entity`` keys (all optional): ``cmp``, ``level`` and ``member`` (the focus, for the AI question),
    ``variance`` (plan) / ``bias`` (forecast), ``series_id``, ``customer``, ``sku``, ``region``, ``channel``,
    ``category``, ``brand``, ``path`` (drill path + focus as filters, sent with ask_ai; default = the
    entity's own dimensions), ``date`` (month of the cell that motivated a promotion/merchandising action),
    ``cause_label``, ``dist_change`` (Δ distribution in p.p., cause 'distribuicao') and
    ``distribution_change_pct`` (lever of 'desafio_comercial', from ``assess().levers``).

    Prefills: create_override {customer, sku, date, event_type, uplift_pct, comment} (OverrideForm /
    POST /api/overrides); simulate {scope:{dims}, <dims flat>, distribution_change_pct?} (ROUTES.cenarios);
    ask_ai {question, filters}; open_series / open_workspace {series_id}; open_fva {route}.
    Buttons whose entity lacks what they need (e.g. create_override without a customer) are skipped;
    ask_ai (probed question) is appended unless the level is champion/series_type.
    """
    out: list[dict[str, Any]] = []
    for kind in (*PRIMARY_ACTIONS.get(code, ()), "ask_ai"):
        if any(a["kind"] == kind for a in out):
            continue
        spec = _build(kind, code, entity, ctx)
        if spec is not None:
            out.append(spec)
    return out


MENU_ORDER = ("open_series", "create_override", "simulate", "ask_ai")  # spec §2.3.4 row "Ações" menu
DRAWER_ORDER = ("open_workspace", "create_override", "simulate", "ask_ai")  # spec §2.3.6 sticky action bar


def menu_actions(code: str | None, entity: Mapping[str, Any], ctx: PlanningContext, *, drawer: bool = False):
    """Full action menu of a series: the exceptions row "Ações" (Abrir ficha · Criar ajuste comercial ·
    Simular cenário · Perguntar à IA) or, with ``drawer``, the drawer's action bar (Abrir no workspace ·
    Criar ajuste comercial · Simular cenário · Perguntar à IA).

    The order is fixed, so every row shows the same item in the same place; an item takes the cause's
    own prefill when the cause's primary action is of that kind (e.g. 'promocao' -> create_override with
    event, month and uplift; 'distribuicao' -> simulate with the distribution lever). A primary action
    outside the fixed menu (open_fva of 'ajuste_piorou'; open_workspace of 'patamar' in a row) is appended."""
    own = {a["kind"]: a for a in (actions_for(code, entity, ctx) if code else [])}
    if drawer and "open_series" in own:  # the drawer IS the series card: "open" goes to the workspace
        own.pop("open_series")
        own.setdefault("open_workspace", _build("open_workspace", code or "", entity, ctx))
    out: list[dict[str, Any]] = []
    for kind in DRAWER_ORDER if drawer else MENU_ORDER:
        spec = own.pop(kind, None)
        if spec is None and kind == "create_override" and entity.get("customer"):
            spec = _action(
                "create_override",
                {
                    "customer": entity["customer"],
                    "sku": entity.get("sku") or None,
                    "date": promo_prefill_date(ctx, None),
                },
            )
        elif spec is None:
            spec = _build(kind, code or "", entity, ctx)
        if spec is not None:
            out.append(spec)
    out.extend(a for a in own.values() if a is not None)
    return out
