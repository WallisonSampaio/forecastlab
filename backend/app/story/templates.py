"""Formatting helpers and chapter templates of the executive report (spec §4.5).

Every function here turns a flat ``facts`` mapping (the numbers the builder computed once, from the
same ``deviations.service`` / ``trust`` / ``assess`` calls the deep dive uses) into pt-BR text. Numbers are
always written with ``services.ptbr`` through the helpers below, so a test can compare a headline with
``ptbr.money(facts[...])`` / ``ptbr.pct(facts[...])``.

Copy rules: headlines are statements with the number (answer first), at most 2 lines at 1440 px
(``MAX_HEADLINE_CHARS``); a missing input never prints "n/d" inside a sentence — the clause is dropped,
or the builder marks the chapter ``empty`` with a notice. Takeaways mark emphasis with ``**…**``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from app.deviations import common
from app.services import ptbr

CHAPTER_IDS = ("resumo", "realizado", "precisao", "projecao", "gap", "meta", "decisoes")

# id -> (short, question). The projecao short/title is "Próximos {h} meses" (filled at build time).
CHAPTERS: dict[str, tuple[str, str]] = {
    "resumo": ("Resumo", "Qual é a mensagem principal para a reunião de S&OP?"),
    "realizado": ("Realizado", "Como fechamos os últimos 12 meses frente ao orçamento — e por quê?"),
    "precisao": ("Precisão", "Quanto o forecast errou, em que direção e por quê?"),
    "projecao": ("Próximos {h} meses", "Para onde vamos, frente ao orçamento e à meta?"),
    "gap": ("Gap vs orçamento", "Quem explica o gap vs orçamento — e é premissa ou demanda?"),
    "meta": ("Meta", "Qual a chance de bater a meta e o que seria preciso?"),
    "decisoes": ("Decisões", "O que precisamos decidir hoje?"),
}
# Chapter titles (eyebrow "Capítulo n de 7 · {title}" and the H1 of an empty chapter).
TITLES: dict[str, str] = {
    "resumo": "Resumo executivo",
    "realizado": "Realizado vs orçamento",
    "precisao": "Precisão do forecast",
    "projecao": "Próximos {h} meses",
    "gap": "Gap vs orçamento",
    "meta": "Viabilidade da meta",
    "decisoes": "Decisões para hoje",
}
INVESTIGATE_LABEL = "Investigar no deep dive"
LINK_LABEL = "Ver no deep dive"
SIMULATE_LABEL = "Simular alavanca"

MAX_HEADLINE_CHARS = 220
ALIGNED_PCT = 0.005  # |gap vs orçamento| ≤ 0,5% reads "alinhado"
CONTROLLABLE_HEADLINE = 0.30  # precisao: "causa controlável" headline when its share of the error ≥ 30%
PROMO_PRICE_SHARE = 0.20  # realizado: promo months' share of the price effect worth a takeaway
LIKELY_PROB = 0.35  # gap: below this chance of reaching the budget the deviation is "provável"
RECURRENT_VPCT = 0.05  # same-direction realized deviation that makes a member "recorrente" (§4.2.2)

NOTICE_NO_PLAN = "Sem orçamento/meta nesta base — envie a aba 'Plano (opcional)' do modelo de planilha."
NOTICE_NO_PLAN_LTM = (
    "Sem orçamento para os últimos 12 meses nesta base — envie a aba 'Plano (opcional)' do modelo de planilha."
)
NOTICE_NO_TARGET = "Sem meta de vendas nesta base — envie a aba 'Plano (opcional)' do modelo de planilha."
NOTICE_NO_BACKTEST = (
    "Sem resultados de backtest nesta execução: o histórico das séries é curto demais para medir o erro "
    "fora da amostra."
)
NOTICE_NO_SERIES = "Nenhuma série neste recorte."

BRIDGE_NOTE = "Volume valorizado ao preço médio orçado; mix no nível Cliente × SKU × mês."
CAUSES_NOTE = (
    "Erro fora da amostra (backtest com origem móvel, {lag} de antecedência). WMAPE em unidades; impacto "
    "valorizado ao preço realizado. Cada mês-série recebe uma única causa, pela ordem de prioridade, e só "
    "quando o sinal do erro é coerente com a causa."
)

# Probed "Perguntar à IA" questions (spec §2.2.3 / §4.3.3). Do not reword without re-probing ai.intents.parse.
ASK_RESUMO = "Quais os principais riscos?"
ASK_REALIZADO = "Quanto vendemos nos últimos 12 meses?"
ASK_PRECISAO_FVA = "Quais ajustes comerciais pioraram a acurácia?"
ASK_PRECISAO_OVER = "Quais clientes estão superestimados?"
ASK_PRECISAO_UNDER = "Quais clientes estão subestimados?"
ASK_META = "A meta é realista?"
ARTICLE_LEVEL = {
    "region": "a região",
    "channel": "o canal",
    "customer": "o cliente",
    "category": "a categoria",
    "sku": "o SKU",
}


# ================================================================================== helpers (spec)
def M(v: float | None) -> str:
    """money(|v|): 'R$ 4,09 mi'."""
    return ptbr.money(abs(v) if v is not None else None)


def Ms(v: float | None) -> str:
    """money(v) with an explicit '+' for positive values: '+R$ 0,42 mi' / '-R$ 5,00 mi'."""
    s = ptbr.money(v)
    return f"+{s}" if v is not None and s != ptbr.NA and v > 0 else s


def P1(v: float | None) -> str:
    return ptbr.pct(v, 1)


def P1s(v: float | None) -> str:
    return ptbr.pct(v, 1, signed=True)


def P0(v: float | None) -> str:
    return ptbr.pct(v, 0)


def PP(v: float | None) -> str:
    """Fraction -> percentage points: 0.125 -> '12,5 p.p.'."""
    return f"{ptbr.dec(v * 100 if v is not None else None, 1)} p.p."


def MES(d: object) -> str:
    """'dez/2026'."""
    return ptbr.month_label(d)


def MES_LONG(d: object) -> str:
    """'dezembro de 2026'."""
    return ptbr.month_label(d, long=True)


def dir_(v: float | None) -> str:
    return "abaixo" if (v or 0.0) < 0 else "acima"


def grow(g: float | None) -> str:
    """'crescer 7,3%' | 'recuar 2,1%' | 'manter o patamar' (±0,5% band)."""
    if g is not None and g >= 0.005:
        return f"crescer {P1(g)}"
    if g is not None and g <= -0.005:
        return f"recuar {P1(abs(g))}"
    return "manter o patamar"


def plural(n: float | int, s: str, p: str) -> str:
    return s if n == 1 else p


# ================================================================================== extra helpers
def num(v: Any) -> float | None:
    """Finite float or None."""
    if v is None or isinstance(v, bool | str):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def lower_first(s: str | None) -> str:
    """'Promoção não antecipada' -> 'promoção não antecipada' (keeps 'P10–P90' and other acronyms)."""
    if not s:
        return ""
    return s[0].lower() + s[1:]


def join_names(names: list[str]) -> str:
    """'a' | 'a e b' | 'a, b e c'."""
    names = [n for n in names if n]
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} e {names[-1]}"


def level_word(level: str, n: int) -> str:
    """'cliente' / 'clientes', 'categoria' / 'categorias', 'SKU' / 'SKUs'."""
    return common.LEVEL_SINGULAR[level] if n == 1 else common.LEVEL_PLURAL[level]


def fit(*candidates: str) -> str:
    """First candidate within MAX_HEADLINE_CHARS (the last one otherwise)."""
    for c in candidates:
        if c and len(c) <= MAX_HEADLINE_CHARS:
            return c
    return candidates[-1]


def takeaway(text: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"text": text, "link": {"label": LINK_LABEL, "params": params} if params else None}


# ================================================================================== routes (lib/routes.ts)
_DEFAULT_PERIOD = common.DEFAULT_PERIOD
_LENS_FORECAST = ("ac_fc", "ac_cs")
_DIM_KEYS = ("region", "channel", "customer", "category", "brand", "sku")
_SCENARIO_KEYS = (
    "region",
    "channel",
    "customer",
    "category",
    "sku",
    "distribution_change_pct",
    "price_change_pct",
    "marketing_change_pct",
)


def _enc(v: Any) -> str:
    """JavaScript ``encodeURIComponent``."""
    return quote(str(v), safe="-_.!~*'()")


def _qs(pairs: list[tuple[str, Any]]) -> str:
    parts = [f"{_enc(k)}={_enc(v)}" for k, v in pairs if v is not None and v != ""]
    return f"?{'&'.join(parts)}" if parts else ""


def _next_level(path: Mapping[str, str]) -> str:
    return next((d for d in common.DRILL_ORDER if not path.get(d)), "series")


def deviations_href(state: Mapping[str, Any]) -> str:
    """Python twin of ``deviationsHref`` (frontend/src/lib/deviationsUrl.ts): defaults omitted, fixed key order."""
    cmp = state.get("cmp") or "fc_pl"
    path = state.get("path") or {}
    pairs: list[tuple[str, Any]] = []
    if cmp in _LENS_FORECAST:
        pairs.append(("lente", "previsao"))
    if cmp != "fc_pl":
        pairs.append(("cmp", cmp))
    periodo = state.get("periodo")
    if periodo and periodo != _DEFAULT_PERIOD[cmp]:
        pairs.append(("periodo", periodo))
    if state.get("medida") and state["medida"] != "revenue":
        pairs.append(("medida", state["medida"]))
    pairs += [(d, path.get(d)) for d in _DIM_KEYS]
    nivel = state.get("nivel")
    if nivel and nivel != _next_level(path):
        pairs.append(("nivel", nivel))
    pairs += [(k, state.get(k)) for k in ("sel", "causa", "serie", "de")]
    return f"/app/desvios{_qs(pairs)}"


def _num_param(v: float | None) -> str | None:
    """Numbers as JavaScript's String(n) would write them, rounded to 3 decimals ('0.133')."""
    if v is None:
        return None
    r = round(float(v), 3)
    return str(int(r)) if r == int(r) else repr(r)


def scenarios_route(scope: Mapping[str, str], levers: Mapping[str, float | None] | None = None) -> str:
    """Python twin of ``ROUTES.cenarios``: '/app/scenarios?region=Sul&distribution_change_pct=0.133'."""
    vals = {**{k: scope.get(k) for k in _SCENARIO_KEYS[:5]}, **{k: _num_param(v) for k, v in (levers or {}).items()}}
    return f"/app/scenarios{_qs([(k, vals.get(k)) for k in _SCENARIO_KEYS])}"


# ================================================================================== 1 · resumo
def governing_thought(f: Mapping[str, Any], h: int) -> str:
    fc_vs_ltm, gap, pct = num(f.get("fc_vs_ltm")), num(f.get("gap_pl")), num(f.get("gap_pl_pct"))
    prob = num(f.get("prob_tg"))
    if not f.get("has_plan") or gap is None or pct is None:
        return (
            f"Vamos {grow(fc_vs_ltm)} nos próximos {h} meses (consenso de {M(f.get('fc'))}); esta base não tem "
            "orçamento nem meta para comparar."
        )
    meta = f"a meta tem {P0(prob)} de chance" if prob is not None else ""
    if abs(pct) <= ALIGNED_PCT:
        cls = f" ({lower_first(f['class_tg'])})" if f.get("class_tg") else ""
        tail = f" e {meta}{cls}" if meta else ""
        return f"O consenso dos próximos {h} meses está alinhado ao orçamento{tail}."
    if pct > 0:
        tail = f"; {meta}" if meta else ""
        return (
            f"Vamos {grow(fc_vs_ltm)} e superar o orçamento em {M(gap)}{tail} — o foco é garantir abastecimento "
            "para a demanda adicional."
        )
    growing = fc_vs_ltm is not None and fc_vs_ltm >= 0.005
    joint = ", mas" if growing else " e"  # "crescer …, mas fechar abaixo" | "recuar … e fechar abaixo"
    lead = f"Vamos {grow(fc_vs_ltm)} nos próximos {h} meses{joint} fechar {M(gap)} abaixo do orçamento"
    n, share, level = f.get("n_top"), num(f.get("share_top")), f.get("level") or "customer"
    conc = ""
    if n and share is not None:
        n = int(n)
        conc = f": {n} {level_word(level, n)} {plural(n, 'concentra', 'concentram')} {P0(share)} das perdas"
    if conc and meta:
        return f"{lead}{conc} e {meta}."
    if conc:
        return f"{lead}{conc}."
    return f"{lead}; {meta}." if meta else f"{lead}."


def scqa(f: Mapping[str, Any], h: int, horizon_label: str, decisions: list[Mapping[str, Any]]) -> dict[str, str]:
    """Situação / Complicação / Resposta of the Resumo chapter (Minto)."""
    ac_vs_py, attain = num(f.get("ac_vs_py")), num(f.get("attain_pl"))
    situacao = f"Fechamos os últimos 12 meses com {M(f.get('ac_ltm'))}"
    if ac_vs_py is not None:
        situacao += f" ({P1s(ac_vs_py)} vs ano anterior)"
    if f.get("has_plan") and attain is not None:
        situacao += f" e {P1(attain)} do orçamento"
    situacao += "."
    head = f"O consenso para os próximos {h} meses ({horizon_label}) soma {M(f.get('fc'))}"
    gap_pl, gap_tg = num(f.get("gap_pl")), num(f.get("gap_tg"))
    if f.get("has_plan") and gap_pl is not None:
        complicacao = f"{head}: {M(gap_pl)} {dir_(gap_pl)} do orçamento"
        complicacao += f" e {M(gap_tg)} {dir_(gap_tg)} da meta." if gap_tg is not None else "."
    else:
        growth = f" ({P1s(f.get('fc_vs_ltm'))} vs últimos 12 meses)" if num(f.get("fc_vs_ltm")) is not None else ""
        band = ""
        if num(f.get("p10")) is not None and num(f.get("p90")) is not None:
            band = f", com faixa provável de {M(f['p10'])} a {M(f['p90'])}"
        complicacao = f"{head}{growth}{band}."
    n = len(decisions)
    if n == 0:
        resposta = "Nenhuma decisão crítica neste ciclo — manter o plano."
    else:
        shorts = "; ".join(str(d["short"]) for d in decisions[:2])
        resposta = f"{n} {plural(n, 'decisão', 'decisões')} para hoje: {shorts}."
    return {"situacao": situacao, "complicacao": complicacao, "resposta": resposta}


def _kpi(
    id_: str,
    label: str,
    value: float | None,
    fmt: str,
    *,
    text: str | None = None,
    delta: str | None = None,
    tone: str = "neutral",
    hint: str | None = None,
) -> dict[str, Any]:
    return {
        "id": id_,
        "label": label,
        "value": value,
        "format": fmt,
        "text": text,
        "delta": delta,
        "delta_tone": tone,
        "hint": hint,
    }


def _tone(v: float | None, good_if_positive: bool = True) -> str:
    if v is None or abs(v) < 1e-12:
        return "neutral"
    return "good" if (v > 0) == good_if_positive else "bad"


CLASS_TONE = {"REALISTIC": "good", "UNDERESTIMATED": "good", "STRETCH": "neutral", "AGGRESSIVE": "bad"}
VERDICT_TONE = {"confiavel": "good", "cautela": "neutral", "nao_confiavel": "bad"}


def resumo_cards(f: Mapping[str, Any], h: int) -> list[dict[str, Any]]:
    """Exactly 4 KpiSpec of the Resumo row (no icons; spec §4.5 "KPI cards")."""
    has_plan = bool(f.get("has_plan"))
    ac, ac_vs_py, pl_ltm = num(f.get("ac_ltm")), num(f.get("ac_vs_py")), num(f.get("pl_ltm"))
    hint1 = f"{P1s(ac / pl_ltm - 1)} vs orçamento" if has_plan and ac is not None and pl_ltm else None
    c1 = _kpi(
        "actual_ltm",
        "Real · últimos 12 meses",
        ac,
        "currency",
        delta=f"{P1s(ac_vs_py)} vs ano anterior" if ac_vs_py is not None else None,
        tone=_tone(ac_vs_py),
        hint=hint1,
    )
    fc_vs_ltm, pct = num(f.get("fc_vs_ltm")), num(f.get("gap_pl_pct"))
    vs_ltm = f"{P1s(fc_vs_ltm)} vs últimos 12 meses" if fc_vs_ltm is not None else None
    band = None
    if num(f.get("p10")) is not None and num(f.get("p90")) is not None:
        band = f"{M(f['p10'])}–{M(f['p90'])}"
    if has_plan and pct is not None:
        tone2 = "neutral" if abs(pct) < ALIGNED_PCT else _tone(pct)
        c2 = _kpi(
            "consensus",
            f"Consenso · próximos {h} meses",
            num(f.get("fc")),
            "currency",
            delta=f"{P1s(pct)} vs orçamento",
            tone=tone2,
            hint=vs_ltm,
        )
    else:
        # When card 3 shows the P10–P90 band (no target), card 2 does not repeat it in its hint.
        band_card = not (has_plan and num(f.get("prob_tg")) is not None)
        c2 = _kpi(
            "consensus",
            f"Consenso · próximos {h} meses",
            num(f.get("fc")),
            "currency",
            delta=vs_ltm,
            tone=_tone(fc_vs_ltm),
            hint=f"faixa {band}" if band and not band_card else None,
        )
    if has_plan and num(f.get("prob_tg")) is not None:
        c3 = _kpi(
            "prob_target",
            "Chance de bater a meta",
            num(f.get("prob_tg")),
            "percent",
            delta=f.get("class_tg"),
            tone=CLASS_TONE.get(str(f.get("class_code")), "neutral"),
            hint=f"meta {M(f.get('target'))}" if num(f.get("target")) is not None else None,
        )
    else:
        c3 = _kpi("band", "Faixa provável (P10–P90)", None, "text", text=band or "—", hint="consenso ± incerteza")
    bias = num(f.get("bias"))
    c4 = _kpi(
        "accuracy",
        "Acurácia do forecast",
        num(f.get("accuracy")),
        "percent",
        delta=f.get("verdict_label"),
        tone=VERDICT_TONE.get(str(f.get("verdict")), "neutral"),
        hint=f"viés {P1s(bias)}" if bias is not None else None,
    )
    return [c1, c2, c3, c4]


# ================================================================================== 2 · realizado
EFFECT_WORD = {"volume": "volume", "mix": "mix", "price": "preço"}


def _effects(f: Mapping[str, Any]) -> list[tuple[str, float]]:
    return [
        (EFFECT_WORD[k], v)
        for k in ("volume", "mix", "price")
        if (v := num(f.get(k if k != "volume" else "vol"))) is not None
    ]


def realizado_headline(f: Mapping[str, Any]) -> str:
    v, v_pct, vol = num(f.get("v")) or 0.0, num(f.get("v_pct")), num(f.get("vol")) or 0.0
    effects = _effects(f)
    pct_txt = f" ({P1(abs(v_pct))})" if v_pct is not None else ""
    if v < 0:
        negs = sorted(((w, x) for w, x in effects if w != "volume" and x < 0), key=lambda e: e[1])
        units_pct = num(f.get("units_pct"))
        if vol > 0 and negs and units_pct is not None and v_pct is not None:
            parts = join_names([f"{w} ({Ms(x)})" for w, x in negs])
            verb = "anularam" if len(negs) > 1 else "anulou"
            return (
                f"Vendemos {P1(units_pct)} mais unidades que o orçado, mas a receita ficou {P1(abs(v_pct))} abaixo "
                f"do orçamento ({M(v)}): {parts} {verb} o ganho de volume."
            )
        word, x = min(effects, key=lambda e: e[1]) if effects else ("volume", v)
        share = x / v if v else None
        lead = f"A receita dos últimos 12 meses ficou {M(v)}{pct_txt} abaixo do orçamento"
        if share is not None and share <= 1.0:
            return f"{lead}; {word} explica {P0(share)} do desvio."
        return f"{lead}; o principal fator é {word} ({Ms(x)})."
    word, x = max(effects, key=lambda e: e[1]) if effects else ("volume", v)
    pct_s = f" ({P1s(v_pct)})" if v_pct is not None else ""
    return f"Superamos o orçamento dos últimos 12 meses em {M(v)}{pct_s}, puxados por {word} ({Ms(x)})."


def realizado_takeaways(f: Mapping[str, Any], level: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    ac, py, g = num(f.get("ac")), num(f.get("py")), num(f.get("ac_vs_py"))
    attain_pl, attain_tg = num(f.get("attain_pl")), num(f.get("attain_tg"))
    tg = f" e {P1(attain_tg)} da meta" if attain_tg is not None else ""
    reach = f"atingimos **{P1(attain_pl)}** do orçamento{tg}" if attain_pl is not None else ""
    if g is not None and py:
        lead = (
            f"Crescemos **{P1s(g)}** sobre o ano anterior"
            if g >= 0
            else f"Recuamos **{P1(abs(g))}** frente ao ano anterior"
        )
        out.append(takeaway(f"{lead} ({M(py)} → {M(ac)}){' e ' + reach if reach else ''}."))
    elif reach:
        out.append(takeaway(f"{reach[0].upper()}{reach[1:]}."))
    price, promo = num(f.get("price")), num(f.get("price_promo"))
    reg, avg = num(f.get("reg_price_gap")), num(f.get("avg_price_gap"))
    if (
        price is not None
        and price < 0
        and promo is not None
        and abs(promo) >= PROMO_PRICE_SHARE * abs(price)
        and reg is not None
    ):
        out.append(
            takeaway(
                f"**{P0(promo / price)}** do efeito preço veio de meses com promoção; nos meses regulares o preço "
                f"realizado ficou **{P1s(reg)}** vs o orçado."
            )
        )
    elif avg is not None:
        out.append(takeaway(f"Preço realizado **{P1s(avg)}** vs o orçado, sem efeito de mix."))
    # ``sel`` carries the member KEY (a series id at the series level), never its display label.
    top, share, tv = f.get("top_adv"), num(f.get("top_adv_share")), num(f.get("top_adv_v"))
    if top and share is not None and tv is not None:
        params = {"cmp": "ac_pl", "periodo": "u12m", "nivel": level, "sel": f.get("top_adv_key") or top}
        out.append(takeaway(f"**{top}** responde por {P0(share)} das perdas vs orçamento ({Ms(tv)}).", params))
    elif f.get("top_fav") and num(f.get("top_fav_v")) is not None:
        params = {"cmp": "ac_pl", "periodo": "u12m", "nivel": level, "sel": f.get("top_fav_key") or f["top_fav"]}
        out.append(takeaway(f"**{f['top_fav']}** lidera o ganho vs orçamento ({Ms(f['top_fav_v'])}).", params))
    return out[:3]


# ================================================================================== 3 · precisao
def precisao_headline(f: Mapping[str, Any]) -> str:
    wmape, naive, gain = num(f.get("wmape")), num(f.get("naive")), num(f.get("gain_pp"))
    if gain is None or gain <= 0:
        ref = f" ({P1(naive)})" if naive is not None else ""
        return (
            f"Atenção: o forecast errou {P1(wmape)} fora da amostra e não superou o método ingênuo{ref} — revise os "
            "modelos antes de decidir."
        )
    ctrl, cause1, share1 = num(f.get("controllable_share")), f.get("cause1"), num(f.get("cause1_share"))
    if ctrl is not None and ctrl >= CONTROLLABLE_HEADLINE and cause1 and share1 is not None:
        return (
            f"O forecast errou {P1(wmape)} fora da amostra — {PP(gain)} a menos que o método ingênuo — e "
            f"{P0(ctrl)} do erro tem causa controlável: {lower_first(cause1)} lidera ({P0(share1)})."
        )
    inherent = num(f.get("inherent_share")) or 0.0
    return (
        f"O forecast errou {P1(wmape)} fora da amostra ({PP(gain)} a menos que o ingênuo); {P0(inherent)} do erro é "
        "variação inerente à demanda — gerencie com estoque de segurança, não com ajustes."
    )


def precisao_takeaways(f: Mapping[str, Any], level: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    bias, sys_share = num(f.get("bias")), num(f.get("systematic_share"))
    if bias is not None:
        label = f" ({lower_first(f['bias_label'])})" if f.get("bias_label") else ""
        tail = (
            f": **{P0(sys_share)}** do erro é sistemático; o restante é ruído que se compensa"
            if sys_share is not None
            else ""
        )
        out.append(takeaway(f"Viés de **{P1s(bias)}**{label}{tail}."))
    fva = num(f.get("fva_pp"))
    if f.get("has_history") and fva is not None:
        verb = "melhoraram" if fva >= 0 else "pioraram"
        added = num(f.get("value_added"))
        txt = f"Os ajustes comerciais {verb} a acurácia em **{PP(abs(fva))}**"
        if added is not None:
            txt += f" ({P0(added)} dos ajustes agregaram valor)"
        worst, wpp = f.get("worst_event"), num(f.get("worst_event_pp"))
        if worst and wpp is not None and wpp < 0:
            txt += f"; ajustes de **{lower_first(str(worst))}** pioraram {PP(abs(wpp))}"
        out.append(takeaway(txt if txt.endswith(".") else f"{txt}."))
    else:
        out.append(takeaway("Sem histórico de ajustes comerciais para medir o valor agregado."))
    n, share, names = f.get("n_top_err"), num(f.get("share_top_err")), f.get("names")
    if n and share is not None and names:
        n = int(n)
        out.append(
            takeaway(
                f"**{n}** {level_word(level, n)} {plural(n, 'concentra', 'concentram')} {P0(share)} do erro ({names}).",
                {"cmp": "ac_fc", "nivel": level},
            )
        )
    return out[:3]


# ================================================================================== 4 · projecao
def projecao_headline(f: Mapping[str, Any]) -> str:
    vs = f" ({P1s(f['fc_vs_ltm'])} vs últimos 12 meses)" if num(f.get("fc_vs_ltm")) is not None else ""
    lead = f"O consenso projeta {M(f.get('fc'))} até {MES(f.get('horizon_end'))}{vs}"
    gap_pl, gap_tg = num(f.get("gap_pl")), num(f.get("gap_tg"))
    if f.get("has_plan") and gap_pl is not None:
        tail = f" e {M(gap_tg)} {dir_(gap_tg)} da meta" if gap_tg is not None else ""
        return f"{lead}: {M(gap_pl)} {dir_(gap_pl)} do orçamento{tail}."
    if num(f.get("p10")) is not None and num(f.get("p90")) is not None:
        return f"{lead}; a faixa provável vai de {M(f['p10'])} a {M(f['p90'])}."
    return f"{lead}."


def _band_position(v: float | None, p10: float, p90: float, inside: str, above: str, below: str) -> str | None:
    if v is None:
        return None
    return above if v > p90 else below if v < p10 else inside


def _events_takeaway(f: Mapping[str, Any]) -> dict[str, Any]:
    n = int(num(f.get("n_events")) or 0)
    events = num(f.get("events")) or 0.0
    if n == 0 and abs(events) < 0.5:
        return takeaway("Nenhum evento comercial cadastrado no horizonte — o consenso é igual ao estatístico.")
    return takeaway(f"Eventos comerciais cadastrados somam **{Ms(events)}** ({n} {plural(n, 'ajuste', 'ajustes')}).")


def projecao_takeaways(f: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not f.get("has_plan"):
        vs, peak = num(f.get("fc_vs_ltm")), f.get("peak_month")
        if vs is not None and peak:
            out.append(
                takeaway(
                    f"O consenso fica **{P1s(vs)}** frente aos últimos 12 meses; o pico é **{MES(peak)}** "
                    f"({M(f.get('peak_value'))})."
                )
            )
        out.append(_events_takeaway(f))
        return out
    wq, wq_gap, wm, wm_gap = (
        f.get("worst_q"),
        num(f.get("worst_q_gap")),
        f.get("worst_month"),
        num(f.get("worst_month_gap")),
    )
    if wq and wq_gap is not None and wm and wm_gap is not None:
        if wq_gap < 0:
            q_start, q_end = f.get("worst_q_start"), f.get("worst_q_end")
            in_quarter = not (q_start and q_end) or str(q_start) <= str(wm)[:10] <= str(q_end)
            month = (
                f"**{MES(wm)}** sozinho responde por {Ms(wm_gap)}"
                if in_quarter
                else f"o pior mês é **{MES(wm)}** ({Ms(wm_gap)})"
            )
            out.append(takeaway(f"**{wq}** é o trimestre mais crítico ({Ms(wq_gap)}); {month}."))
        else:
            out.append(
                takeaway(f"Todos os trimestres ficam acima do orçamento; o mais apertado é **{wq}** ({Ms(wq_gap)}).")
            )
    p10, p90 = num(f.get("p10")), num(f.get("p90"))
    if p10 is not None and p90 is not None:
        b = _band_position(num(f.get("budget")), p10, p90, "dentro da", "acima da", "abaixo da")
        t = _band_position(num(f.get("target")), p10, p90, "dentro dela", "acima dela", "abaixo dela")
        if b:
            txt = f"O orçamento está {b} faixa provável P10–P90 ({M(p10)}–{M(p90)})"
            if b == "dentro da" and t == "dentro dela":
                txt = f"Orçamento e meta estão dentro da faixa provável P10–P90 ({M(p10)}–{M(p90)})"
                out.append(takeaway(f"{txt}."))
            else:
                out.append(takeaway(f"{txt}; a meta está {t}." if t else f"{txt}."))
    out.append(_events_takeaway(f))
    return out[:3]


# ================================================================================== 5 · gap
def gap_headline(f: Mapping[str, Any]) -> str:
    v, level = num(f.get("v")) or 0.0, str(f.get("level") or "customer")
    if v >= 0:
        top, tv = f.get("top_pos"), num(f.get("top_pos_v"))
        if top and tv is not None:
            return f"O consenso supera o orçamento em {M(v)}; {top} lidera o ganho ({Ms(tv)})."
        return f"O consenso supera o orçamento em {M(v)}."
    n, share = int(num(f.get("n_top")) or 0), num(f.get("share"))
    names = [str(f[k]) for k in ("n1", "n2", "n3") if f.get(k)]
    if not n or share is None or not names:
        return f"O consenso fica {M(v)} abaixo do orçamento ({P1s(f.get('v_pct'))})."
    names = names[:n]
    word = level_word(level, n)
    lead = f"{n} {word} concentram {P0(share)} das perdas vs orçamento"
    short = f"{lead}: {join_names(names)}." if n > 1 else f"{names[0]} concentra {P0(share)} das perdas vs orçamento."
    if n == 3:
        return fit(short)
    premise = all(f.get(f"tag{i}_code") == "premissa_otimista" for i in range(1, n + 1))
    growth_ok = all(num(f.get(f"gp{i}")) is not None and num(f.get(f"gf{i}")) is not None for i in range(1, n + 1))
    tags = [lower_first(str(f.get(f"tag{i}") or "")) for i in range(1, n + 1)]
    if n == 1:
        if premise and growth_ok:
            long = (
                f"{names[0]} concentra {P0(share)} das perdas vs orçamento: o orçamento supõe {P1s(f['gp1'])} de "
                f"crescimento e o forecast indica {P1s(f['gf1'])}."
            )
        else:
            tag = f" ({tags[0]})" if tags[0] else ""
            long = f"{names[0]}{tag} concentra {P0(share)} das perdas vs orçamento."
        return fit(long, short)
    if premise and growth_ok:
        long = (
            f"{lead}: {names[0]} e {names[1]} orçaram {P1s(f['gp1'])} e {P1s(f['gp2'])} de crescimento; o forecast "
            f"indica {P1s(f['gf1'])} e {P1s(f['gf2'])}."
        )
    else:
        parts = [f"{nm} ({t})" if t else nm for nm, t in zip(names, tags, strict=True)]
        long = f"{lead}: {join_names(parts)}."
    return fit(long, short)


def gap_takeaways(f: Mapping[str, Any], level: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    eff = [num(f.get(k)) for k in ("vol", "mix", "price", "events")]
    if all(x is not None for x in eff):
        vol, mix, price, events = eff
        txt = f"Por quê: volume **{Ms(vol)}**, mix **{Ms(mix)}**, preço **{Ms(price)}**, eventos **{Ms(events)}**"
        prem = num(f.get("plan_price_premium"))
        if prem is not None:
            txt += f" — o orçamento assume preço {P1s(prem)} vs o atual"
        out.append(takeaway(f"{txt}."))
    n_pos, pos, top_pos, top_pos_v = (
        int(num(f.get("n_pos")) or 0),
        num(f.get("pos")),
        f.get("top_pos"),
        num(f.get("top_pos_v")),
    )
    if n_pos > 0 and pos is not None and top_pos and top_pos_v is not None:
        if n_pos == 1:
            out.append(takeaway(f"Oportunidade: só {top_pos} fica acima do orçamento (**{Ms(pos)}**)."))
        else:
            out.append(
                takeaway(
                    f"Oportunidade: {n_pos} {level_word(level, n_pos)} acima do orçamento somam **{Ms(pos)}**; {top_pos} "
                    f"lidera ({Ms(top_pos_v)})."
                )
            )
    v, top1, p, rv = num(f.get("v")) or 0.0, f.get("n1"), num(f.get("p_top1")), num(f.get("rv_top1"))
    if v < 0 and top1 and p is not None:
        params = {"cmp": "fc_pl", "periodo": "h", "nivel": level, "sel": f.get("key1") or top1}
        if rv is not None and rv <= -RECURRENT_VPCT:
            txt = (
                f"{top1} tem **{P0(p)}** de chance de atingir o orçamento e já ficou **{P1s(rv)}** vs orçamento nos "
                "últimos 12 meses — desvio recorrente, não ruído."
            )
        elif p < LIKELY_PROB:
            txt = f"{top1} tem **{P0(p)}** de chance de atingir o orçamento — desvio provável, não ruído."
        else:
            txt = f"{top1} está dentro da incerteza ({P0(p)} de chance de atingir o orçamento)."
        out.append(takeaway(txt, params))
    return out[:3]


# ================================================================================== 6 · meta
LEVER_LIMIT = {"Distribution": 0.20, "Marketing": 0.50}  # = feasibility.PLAUSIBLE (Promotions: n_months / 3)


def pick_lever(levers: list[Mapping[str, Any]], n_months: int) -> Mapping[str, Any] | None:
    """Plausible lever with the smallest NORMALISED effort |required_change| / limit, Price excluded
    (a price cut is not a revenue lever). Promotions are in months, so their limit is n_months / 3."""
    limits = {**LEVER_LIMIT, "Promotions": max(n_months, 1) / 3}
    cands = [
        lv
        for lv in levers or []
        if lv.get("plausible") and lv.get("lever") in limits and num(lv.get("required_change")) is not None
    ]
    if not cands:
        return None
    return min(cands, key=lambda lv: abs(float(lv["required_change"])) / limits[lv["lever"]])


def lever_text(lever: str | None, change: float | None) -> str:
    if lever == "Distribution" and change is not None:
        return f"{P1s(change)} de distribuição numérica"
    if lever == "Marketing" and change is not None:
        return f"{P1s(change)} de investimento em marketing"
    if lever == "Promotions" and change is not None:
        n = max(1, math.ceil(change - 1e-9))
        return f"{n} {plural(n, 'mês', 'meses')} de promoção"
    return "mais de uma alavanca combinada"


def meta_headline(f: Mapping[str, Any]) -> str:
    cls, target, prob = f.get("classification"), f.get("target"), num(f.get("prob"))
    lead = f"A meta de {M(target)}"
    if cls == "STRETCH":
        return (
            f"{lead} é desafiadora: {P0(prob)} de chance — fechar {M(f.get('gap'))} exige "
            f"{lever_text(f.get('lever'), num(f.get('lever_change')))}."
        )
    if cls == "AGGRESSIVE":
        req, fcg = num(f.get("required_growth")), num(f.get("forecast_growth"))
        if req is not None and fcg is not None:
            return (
                f"{lead} é improvável ({P0(prob)}): exige {P1s(req)} de crescimento contra {P1s(fcg)} previstos — "
                "recalibre ou comprometa alavancas concretas."
            )
        return f"{lead} é improvável ({P0(prob)} de chance) — recalibre ou comprometa alavancas concretas."
    if cls == "REALISTIC":
        return f"{lead} é realista ({P0(prob)} de chance): proteja a base — disponibilidade e execução."
    return f"{lead} está abaixo do resultado provável ({P0(prob)} de chance) — há espaço para elevá-la."


def _reason_text(r: str) -> str:
    """``assess`` reason as a sentence, with the journey's typography ('P10–P90', ' — ')."""
    r = str(r).strip().replace("P10-P90", "P10–P90").replace(" - ", " — ")
    return r if r.endswith(".") else f"{r}."


def meta_takeaways(f: Mapping[str, Any], reasons: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    req, fcg, hist = num(f.get("required_growth")), num(f.get("forecast_growth")), num(f.get("historical_growth"))
    # Takeaway 1 = the first ``assess`` reason; the growth reason is skipped because takeaway 2 already
    # states required vs forecast vs historical growth (no sentence says the same number twice).
    rest = [r for r in reasons if r and (req is None or P1s(req) not in str(r))]
    if rest:
        out.append(takeaway(_reason_text(rest[0])))
    if req is not None:
        parts = [f"Crescimento exigido **{P1s(req)}**"]
        tail = []
        if fcg is not None:
            tail.append(f"previsto {P1s(fcg)}")
        if hist is not None:
            tail.append(f"histórico {P1s(hist)}")
        out.append(takeaway(f"{parts[0]} vs {join_names(tail)}." if tail else f"{parts[0]}."))
    r1, p1, dim = f.get("r1"), num(f.get("p1")), str(f.get("feas_dim") or "region")
    if r1 and p1 is not None and int(num(f.get("n_by")) or 0) >= 2:  # "menor chance" needs ≥ 2 members
        n = int(num(f.get("n_aggr")) or 0)
        aggr = (
            f"nenhum{'a' if dim in ('region', 'category') else ''} {common.LEVEL_SINGULAR[dim]} com meta agressiva"
            if n == 0
            else f"{n} {level_word(dim, n)} com meta agressiva"
        )
        out.append(takeaway(f"Menor chance por {common.LEVEL_SINGULAR[dim]}: **{r1}** ({P0(p1)}); {aggr}."))
    return out[:3]


# ================================================================================== 7 · decisoes
def decisoes_headline(decisions: list[Mapping[str, Any]]) -> str:
    """Impacts are never summed: they overlap (the target gap contains part of the budget gap)."""
    n = len(decisions)
    if n == 0:
        return "Nenhuma decisão crítica neste ciclo — plano alinhado."
    shorts = join_names([str(d["short"]) for d in decisions[:3]])
    long = f"{n} {plural(n, 'decisão', 'decisões')} para hoje — a maior envolve {M(decisions[0]['impact'])}: {shorts}."
    return fit(long, f"{n} {plural(n, 'decisão', 'decisões')} para hoje — a maior envolve {M(decisions[0]['impact'])}.")
