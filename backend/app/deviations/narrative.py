"""pt-BR sentences of the deep dive: headlines and diagnosis (spec §4.3.3), shared by both lenses.

Numbers are always written with ``services.ptbr`` (``money``, ``pct``, ``dec``, ``units``). A missing input
never produces "n/d" inside a sentence: the clause (or the whole diagnosis sentence) is dropped instead.
``ai_question`` is final: every wording was probed against ``ai.intents.parse`` (spec §4.3.3
"Actions per focus") — do not write new wordings.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from app.metrics import bias_class
from app.services import ptbr

ARTICLE_LEVEL = {
    "region": "a região",
    "channel": "o canal",
    "customer": "o cliente",
    "category": "a categoria",
    "sku": "o SKU",
}

ALIGNED_VPCT = 0.005  # plan: |V%| below this reads "alinhado" (±0,5%)
PRICE_DIAG_SHARE = 0.25  # plan diagnosis: price sentence when |price effect| ≥ 25% of |V|
COVERAGE_NOTE = 0.80  # volume split: mention the backtest coverage when below 80%
MAX_DIAGNOSIS = 3

_FORECAST = ("ac_fc", "ac_cs")


# ------------------------------------------------------------------------------------------ helpers
def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool | str):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def M(v: float) -> str:
    """money(|v|): 'R$ 4,09 mi'."""
    return ptbr.money(abs(v))


def Ms(v: float) -> str:
    """Signed money: '+R$ 0,42 mi' / '-R$ 4,09 mi'."""
    return ("+" if v > 0 else "") + ptbr.money(v)


def P1(v: float) -> str:
    return ptbr.pct(v, 1)


def P1s(v: float) -> str:
    return ptbr.pct(v, 1, signed=True)


def P0(v: float) -> str:
    return ptbr.pct(v, 0)


def PP(v: float) -> str:
    """Percentage points from a fraction: 0.125 -> '12,5 p.p.'."""
    return f"{ptbr.dec(v * 100, 1)} p.p."


def plural(n: float, singular: str, plural_: str) -> str:
    return singular if abs(n) == 1 else plural_


def lower_first(s: str) -> str:
    """Lower-case only the first letter (keeps 'P10–P90', 'SKU' ...)."""
    return s[:1].lower() + s[1:] if s else s


def amount(v: float, measure: str = "revenue") -> str:
    """|v| in the measure: 'R$ 4,09 mi' or '12.345 unidades'."""
    return M(v) if measure == "revenue" else ptbr.units(abs(v))


def amount_signed(v: float, measure: str = "revenue") -> str:
    if measure == "revenue":
        return Ms(v)
    return ("+" if v > 0 else "-" if v < 0 else "") + ptbr.units(abs(v))


def _phrase(facts: Mapping[str, Any]) -> str:
    """Period inside a sentence ('nos próximos 12 meses'); falls back to 'em {period_label}'."""
    if facts.get("period_phrase"):
        return str(facts["period_phrase"])
    if facts.get("period_label"):
        return f"em {facts['period_label']}"
    return ""


def _join(*parts: str) -> str:
    return " ".join(p for p in parts if p)


def _ref(cmp: str) -> tuple[str, str]:
    """('do orçamento' | 'da meta', 'ao orçamento' | 'à meta')."""
    return ("da meta", "à meta") if cmp == "fc_tg" else ("do orçamento", "ao orçamento")


def _bias_label(facts: Mapping[str, Any]) -> str | None:
    if facts.get("bias_label"):
        return str(facts["bias_label"])
    b = _num(facts.get("bias"))
    return None if b is None else ptbr.BIAS_CLASS[bias_class(b)]


# ------------------------------------------------------------------------------------------ headlines
def summary_headline(facts: Mapping[str, Any], cmp: str) -> str:
    """Node headline (spec §4.3.3 "Headline templates": plan V<0 / V>0 / |V%|<0,5% and forecast).

    ``facts`` keys — plan: ``node``, ``period_phrase`` (or ``period_label``), ``variance``, ``variance_pct``,
    ``top``, ``top_share``, ``top_fav``, ``top_fav_share``, ``measure``; forecast: ``node``, ``period_phrase``,
    ``wmape``, ``abs_error``, ``bias``, ``bias_label``, ``cause1`` (label), ``cause1_share``, ``consensus`` (bool:
    ac_cs; default = cmp == 'ac_cs').
    Example (plan): "Empresa toda: consenso R$ 4,09 mi abaixo do orçamento (-4,2%) nos próximos 12 meses —
    Litoral Market responde por 32% das perdas."
    """
    node = str(facts.get("node") or "Empresa toda")
    if cmp in _FORECAST:
        return _forecast_headline(facts, cmp, node)
    return _plan_headline(facts, cmp, node)


def _plan_headline(facts: Mapping[str, Any], cmp: str, node: str) -> str:
    measure = str(facts.get("measure") or "revenue")
    x_word = "realizado" if cmp == "ac_pl" else "consenso"
    ref_do, ref_ao = _ref(cmp)
    phrase = _phrase(facts)
    v, vpct = _num(facts.get("variance")), _num(facts.get("variance_pct"))
    if v is None:
        return f"{_join(f'{node}: sem dados para comparar {ref_ao}', phrase)}."
    if v == 0 or (vpct is not None and abs(vpct) < ALIGNED_VPCT):
        return f"{_join(f'{node}: {x_word} alinhado {ref_ao}', phrase)} (±0,5%)."
    par = f" ({P1s(vpct)})" if vpct is not None else ""
    if v < 0:
        text = _join(f"{node}: {x_word} {amount(v, measure)} abaixo {ref_do}{par}", phrase)
        top, share = facts.get("top"), _num(facts.get("top_share"))
        if top and share is not None:
            text += f" — {top} responde por {P0(share)} das perdas"
    else:
        text = _join(f"{node}: {x_word} {amount(v, measure)} acima {ref_do}{par}", phrase)
        top, share = facts.get("top_fav"), _num(facts.get("top_fav_share"))
        if top and share is not None:
            text += f" — {top} lidera o ganho ({P0(share)})"
    return text + "."


def _forecast_headline(facts: Mapping[str, Any], cmp: str, node: str) -> str:
    consensus = facts.get("consensus")
    kind = "de consenso" if (consensus if consensus is not None else cmp == "ac_cs") else "estatístico"
    phrase = _phrase(facts)
    w, ae, b = _num(facts.get("wmape")), _num(facts.get("abs_error")), _num(facts.get("bias"))
    if w is None:
        return f"{_join(f'{node}: sem vendas', phrase)} para medir o erro do forecast."
    text = f"{node}: o forecast {kind} errou {P1(w)}"
    if ae is not None:
        text += f" ({M(ae)})"
    text = _join(text, phrase)
    clauses = []
    cause1, share1 = facts.get("cause1"), _num(facts.get("cause1_share"))
    if cause1 and share1 is not None:
        clauses.append(f"{lower_first(str(cause1))} explica {P0(share1)}")
    label = _bias_label(facts)
    if b is not None:
        clauses.append(f"o viés é de {P1s(b)}" + (f" ({label.lower()})" if label else ""))
    return text + ("; " + " e ".join(clauses) if clauses else "") + "."


def focus_headline(facts: Mapping[str, Any], cmp: str) -> str:
    """Selected-member headline; same keys as ``summary_headline`` plus ``member``, ``tag_label`` (plan
    primary tag), ``realized_variance_pct`` and ``recurrent`` (fc_*). Without ``member`` it is the
    summary headline.

    plan: "{member}: {money(|V|)} {abaixo|acima} {do orçamento|da meta} ({V%}); causa principal: {tag}."
    + " — já ficou {rv} vs orçamento nos últimos 12 meses." when recurrent (fc_*);
    forecast: "{member}: erro de {wmape} ({money(AE)}) e viés de {bias}; causa principal: {cause1} ({share} do erro)."
    """
    member = facts.get("member")
    if not member:
        return summary_headline(facts, cmp)
    member = str(member)
    if cmp in _FORECAST:
        w, ae, b = _num(facts.get("wmape")), _num(facts.get("abs_error")), _num(facts.get("bias"))
        if w is None:
            return f"{_join(f'{member}: sem vendas', _phrase(facts))} para medir o erro do forecast."
        text = f"{member}: erro de {P1(w)}" + (f" ({M(ae)})" if ae is not None else "")
        if b is not None:
            text += f" e viés de {P1s(b)}"
        cause1, share1 = facts.get("cause1"), _num(facts.get("cause1_share"))
        if cause1:
            text += f"; causa principal: {lower_first(str(cause1))}"
            if share1 is not None:
                text += f" ({P0(share1)} do erro)"
        return text + "."
    measure = str(facts.get("measure") or "revenue")
    ref_do, ref_ao = _ref(cmp)
    v, vpct = _num(facts.get("variance")), _num(facts.get("variance_pct"))
    if v is None:
        return f"{_join(f'{member}: sem dados para comparar {ref_ao}', _phrase(facts))}."
    if v == 0 or (vpct is not None and abs(vpct) < ALIGNED_VPCT):
        return f"{_join(f'{member}: alinhado {ref_ao}', _phrase(facts))} (±0,5%)."
    direction = "abaixo" if v < 0 else "acima"
    text = f"{member}: {amount(v, measure)} {direction} {ref_do}" + (f" ({P1s(vpct)})" if vpct is not None else "")
    if facts.get("tag_label"):
        text += f"; causa principal: {str(facts['tag_label']).lower()}"
    rv = _num(facts.get("realized_variance_pct"))
    if cmp in ("fc_pl", "fc_tg") and facts.get("recurrent") and rv is not None:
        text += f" — já ficou {P1s(rv)} vs orçamento nos últimos 12 meses"
    return text + "."


# ------------------------------------------------------------------------------------------ diagnosis
def _effect(facts: Mapping[str, Any], name: str) -> float | None:
    eff = facts.get("effects")
    if isinstance(eff, Mapping) and name in eff:
        return _num(eff.get(name))
    return _num(facts.get(name))


def _events(facts: Mapping[str, Any]) -> tuple[float, int, str | None]:
    """(Σ events value, n adjustments, largest event type).

    The total is ``effects.events`` (or a flat numeric ``events``) when given, else Σ of the list; the
    count and the largest type come from ``events_list`` / a list-valued ``events`` ([{event_type, value, n}])
    or from the flat ``n_events`` / ``top_event``."""
    lst = facts.get("events_list")
    if not isinstance(lst, list | tuple):
        lst = facts.get("events") if isinstance(facts.get("events"), list | tuple) else None
    total = _effect(facts, "events")
    if lst is not None:
        rows = [r for r in lst if isinstance(r, Mapping)]
        if total is None:
            total = sum(_num(r.get("value")) or 0.0 for r in rows)
        n = int(sum(_num(r.get("n")) or 0 for r in rows))
        top = max(rows, key=lambda r: abs(_num(r.get("value")) or 0.0), default=None)
        return total, n, (str(top["event_type"]) if top and top.get("event_type") else None)
    return total or 0.0, int(_num(facts.get("n_events")) or 0), facts.get("top_event")


def plan_diagnosis(facts: Mapping[str, Any], cmp: str) -> list[str]:
    """Up to 3 sentences, in spec order: recurrence (fc_*), growth premise, price, volume split (ac_pl), events.

    ``facts`` keys: ``member`` (None = "o recorte"), ``recurrent``, ``realized_variance_pct``, ``g_plan``,
    ``g_fc``, ``variance``, ``effects`` {volume, mix, price, events} (or flat keys), ``plan_price_premium``
    (fc_*), ``reg_price_gap`` and ``price_promo`` (ac_pl), ``volume_split`` {anticipated, surprise, uncovered,
    coverage} and ``lag_label`` (ac_pl), ``events_list`` ([{event_type, value, n}], fc_*; or a list-valued
    ``events``, or flat ``n_events`` / ``top_event``), ``measure``.
    """
    measure = str(facts.get("measure") or "revenue")
    out: list[str] = []
    rv = _num(facts.get("realized_variance_pct"))
    if cmp in ("fc_pl", "fc_tg") and facts.get("recurrent") and rv is not None:
        who = facts.get("member") or "o recorte"
        out.append(f"O desvio é recorrente: nos últimos 12 meses {who} já ficou {P1s(rv)} vs orçamento.")
    g_plan, g_fc = _num(facts.get("g_plan")), _num(facts.get("g_fc"))
    if g_plan is not None and g_fc is not None:
        if cmp == "ac_pl":
            out.append(
                f"O orçamento supunha {P1s(g_plan)} de crescimento sobre o ano anterior; o realizado foi {P1s(g_fc)}."
            )
        else:
            ref = "A meta" if cmp == "fc_tg" else "O orçamento"
            out.append(f"{ref} supõe {P1s(g_plan)} de crescimento sobre o ano anterior; o forecast indica {P1s(g_fc)}.")
    v, price = _num(facts.get("variance")), _effect(facts, "price")
    if v is not None and price is not None and v != 0 and abs(price) >= PRICE_DIAG_SHARE * abs(v):
        if cmp == "ac_pl":
            gap, promo = _num(facts.get("reg_price_gap")), _num(facts.get("price_promo"))
            if gap is not None:
                text = f"Preço realizado {P1s(gap)} vs o orçado nos meses regulares"
                if promo is not None:
                    text += f"; {M(promo)} do efeito preço veio de meses com promoção"
                out.append(text + ".")
        else:
            premium = _num(facts.get("plan_price_premium"))
            if premium is not None:
                out.append(f"O orçamento assume preço {P1s(premium)} vs o praticado.")
    split = facts.get("volume_split")
    if cmp == "ac_pl" and isinstance(split, Mapping) and (_num(split.get("coverage")) or 0.0) > 0:
        vol = _effect(facts, "volume")
        if vol is None:
            vol = sum(_num(split.get(k)) or 0.0 for k in ("anticipated", "surprise", "uncovered"))
        # lag_label comes from the run's fold_horizon ("1–3 meses"); never hard-coded (spec §2.0 rule 6)
        lag = f" {facts['lag_label']} antes" if facts.get("lag_label") else ""
        cov = _num(split.get("coverage")) or 0.0
        text = (
            f"Do efeito volume ({amount_signed(vol, measure)}), "
            f"{amount_signed(_num(split.get('anticipated')) or 0.0, measure)} já estava no forecast{lag} e "
            f"{amount_signed(_num(split.get('surprise')) or 0.0, measure)} foi surpresa de demanda"
        )
        if cov < COVERAGE_NOTE:
            text += f" ({P0(cov)} dos meses-série cobertos pelo backtest)"
        out.append(text + ".")
    if cmp != "ac_pl":
        total, n, top = _events(facts)
        if total != 0:
            extra = f"{n} {plural(n, 'ajuste', 'ajustes')}" + (f"; maior: {top}" if top else "")
            out.append(f"Eventos comerciais somam {amount_signed(total, measure)} ({extra}).")
    return out[:MAX_DIAGNOSIS]


def forecast_diagnosis(facts: Mapping[str, Any], cmp: str) -> list[str]:
    """Up to 3 sentences, in spec order: systematic share (always), top cause, FVA (ac_cs).

    ``facts`` keys: ``systematic_share``, ``cause1`` (label), ``cause1_abs_error``, ``cause1_n_cells``,
    ``cause1_direction`` ('over' | 'under' | 'mixed'), ``fva_pp`` (ac_cs; fraction, statistical − consensus WMAPE).
    """
    out: list[str] = []
    sys_share = _num(facts.get("systematic_share"))
    if sys_share is not None:
        out.append(f"{P0(sys_share)} do erro é viés sistemático; o restante é ruído que se compensa.")
    cause1, ae1 = facts.get("cause1"), _num(facts.get("cause1_abs_error"))
    if cause1 and ae1 is not None:
        n = int(_num(facts.get("cause1_n_cells")) or 0)
        direction = facts.get("cause1_direction")
        tail = {
            "under": "quase sempre subestimando",
            "over": "quase sempre superestimando",
        }.get(str(direction), "com erros nos dois sentidos")
        out.append(f"{cause1}: {M(ae1)} de erro em {n} {plural(n, 'mês-série', 'meses-série')}, {tail}.")
    fva = _num(facts.get("fva_pp"))
    if cmp == "ac_cs" and fva is not None:
        if fva > 0:
            out.append(f"Ajustes comerciais: {PP(fva)} de ganho de acurácia.")
        elif fva < 0:
            out.append(f"Ajustes comerciais: {PP(abs(fva))} de perda de acurácia.")
        else:
            out.append("Ajustes comerciais: sem efeito na acurácia.")
    # When the largest cause is inherent (nothing to act on), name the controllable cause that leads,
    # so the deep dive still points at what the team can fix (the report's Precisão chapter does the same).
    lead, lead_ae = facts.get("lead_controllable"), _num(facts.get("lead_controllable_abs_error"))
    lead_share = _num(facts.get("lead_controllable_share"))
    if lead and lead_ae is not None and lead_share is not None:
        out.append(
            f"Entre as causas controláveis, {lower_first(str(lead))} lidera: {M(lead_ae)} ({P0(lead_share)} do erro)."
        )
    return out[:MAX_DIAGNOSIS]


# ------------------------------------------------------------------------------------------ AI question
def ai_question(cmp: str, level: str | None, member: str | None, facts: Mapping[str, Any]) -> str | None:
    """Question for the 'Perguntar à IA' action of a focus (node when ``member`` is None).

    ``facts``: ``variance`` (plan) or ``bias`` (forecast). Returns None for champion/series_type levels.
    """
    if level in ("champion", "series_type"):
        return None
    if cmp == "ac_cs":
        return "Quais ajustes comerciais pioraram a acurácia?"
    if cmp == "ac_fc":
        if member:
            return f"Qual o WMAPE de {member}?"
        return (
            "Quais clientes estão superestimados?"
            if (facts.get("bias") or 0.0) > 0
            else "Quais clientes estão subestimados?"
        )
    if cmp == "fc_tg":
        return "A meta é realista?"
    if cmp == "ac_pl":
        return "Quanto vendemos nos últimos 12 meses?"
    # fc_pl
    if member and level in ARTICLE_LEVEL:
        return f"Como está {ARTICLE_LEVEL[level]} {member}?"
    return (
        "Onde estamos abaixo do orçamento?"
        if (facts.get("variance") or 0.0) < 0
        else "Onde estamos acima do orçamento?"
    )
