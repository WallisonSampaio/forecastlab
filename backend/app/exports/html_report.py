"""Self-contained executive HTML report in Portuguese (inline CSS + SVG, no external assets).

The file is the same 7-chapter story as the "Relatório executivo" page (``story.builder.build_story``):
header, then one ``<section>`` per chapter — eyebrow, the headline as ``<h2>``, context, takeaways and the
chapter visual as its "Ver tabela" table. Chapter 1's headline is the governing thought and carries the
SCQA under it (as on screen), so neither is printed twice. The projection chapter keeps the inline SVG
timeline, whose P10–P90 band is the consensus band. An empty chapter prints its notice. The footer carries
the disclosure line and the author signature.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

from app.config import APP_NAME, AUTHOR
from app.services import ptbr
from app.services.context import PlanningContext, clean, records, timeline
from app.story.builder import build_story

REPORT_TITLE = "Relatório Executivo de S&OP"
FOOTER_NOTE = (
    "Dados de demonstração sintéticos e fictícios. Os números são produzidos pelos motores estatísticos e "
    "por regras determinísticas; a camada de IA apenas os explica."
)

CSS = """
:root{--ink:#1b1f3b;--muted:#5f6478;--line:#e3e6ef;--bg:#f4f6fb;--card:#fff;--brand:#3483fa;--navy:#2d3277;
--good:#0ca30c;--bad:#d03b3b;--soft:#eef1fa}
*{box-sizing:border-box}body{margin:0;font-family:Inter,Segoe UI,system-ui,sans-serif;background:var(--bg);color:var(--ink);
line-height:1.5}.wrap{max-width:1120px;margin:0 auto;padding:32px 24px}
header{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;border-bottom:1px solid var(--line);
padding-bottom:16px;margin-bottom:24px}h1{margin:0;font-size:26px;letter-spacing:-.02em;color:var(--navy)}
.sub{color:var(--muted);font-size:13px}
.scqa p{margin:4px 0;color:var(--muted);font-size:14px}.scqa b{color:var(--ink)}
section{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px 24px;margin:20px 0;
box-shadow:0 6px 20px rgba(45,50,119,.06);break-inside:avoid}
.eyebrow{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}
h2{font-size:20px;line-height:1.35;margin:6px 0 4px;max-width:60ch}.q{font-size:14px;margin:0}
.ctx{font-size:12px;color:var(--muted);margin:2px 0 14px}ol{margin:8px 0 16px;padding-left:22px}ol li{margin:4px 0;font-size:14px}
.notice{background:var(--soft);border-radius:12px;padding:12px 14px;font-size:14px}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}caption{text-align:left;font-size:12px;
color:var(--muted);padding-bottom:6px}th{background:var(--soft);color:var(--ink);text-align:left;padding:7px 10px;font-weight:600}
td{padding:7px 10px;border-top:1px solid var(--line);vertical-align:top}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;
white-space:nowrap}.pos{color:var(--good)}.neg{color:var(--bad)}.muted{color:var(--muted);font-size:12px}
.chart{margin:8px 0 4px}footer{margin-top:36px;border-top:1px solid var(--line);padding-top:16px;font-size:12px;color:var(--muted)}
a{color:var(--brand)}@media (max-width:800px){header{flex-direction:column;align-items:flex-start}}
@media print{body{background:#fff}section{box-shadow:none}}
"""

# (field, color, dash pattern, legend label) of the projection timeline (IBCS: ink = real, hatched = forecast)
SERIES = [
    ("actual", "#1b1f3b", "", "Real"),
    ("consensus", "#3483fa", "", "Consenso"),
    ("base", "#5f6478", "4 3", "Estatístico"),
    ("budget", "#1b1f3b", "6 4", "Orçamento"),
    ("target", "#d03b3b", "2 3", "Meta"),
]
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _rich(text: str) -> str:
    """Escapes the text and turns ``**…**`` into ``<strong>`` (no HTML from the data is ever trusted)."""
    return _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", _e(text))


def _m(v: Any) -> str:
    return ptbr.money(v)


def _ms(v: Any) -> str:
    s = ptbr.money(v)
    return f"+{s}" if isinstance(v, int | float) and v > 0 else s


def _p(v: Any, digits: int = 1, signed: bool = False) -> str:
    return ptbr.pct(v, digits, signed=signed)


def _tone(v: Any) -> str:
    return "" if not isinstance(v, int | float) else ("pos" if v > 0 else "neg" if v < 0 else "")


def _kpi_value(k: dict[str, Any]) -> str:
    v, fmt = k.get("value"), k.get("format")
    if fmt == "text" or v is None:
        return str(k.get("text") or ptbr.NA)
    return {
        "currency": _m(v),
        "currency_signed": _ms(v),
        "units": ptbr.units(v),
        # probabilities (ids prob_*) are whole percentages, as on screen and in the headlines
        "percent": _p(v, 0 if str(k.get("id", "")).startswith("prob") else 1),
        "percent_signed": _p(v, 1, True),
        "pp": f"{ptbr.dec(v * 100, 1, signed=True)} p.p.",
    }.get(str(fmt), ptbr.num(v, 2))


def _table(caption: str, head: list[tuple[str, bool]], rows: list[list[tuple[str, str]]]) -> str:
    """head: [(label, numeric)], rows: [[(html, css class)]]."""
    th = "".join(
        f'<th scope="col" class="n">{_e(h)}</th>' if num else f'<th scope="col">{_e(h)}</th>' for h, num in head
    )
    body = "".join("<tr>" + "".join(f'<td class="{c}">{v}</td>' for v, c in r) + "</tr>" for r in rows)
    return f"<table><caption>{_e(caption)}</caption><tr>{th}</tr>{body}</table>"


def _svg_chart(timeline_rows: list[dict[str, Any]]) -> str:
    w, h, pad = 1060, 300, 56
    vals = [r.get(k) for r in timeline_rows for k, *_ in SERIES if r.get(k) is not None]
    if not vals:
        return ""
    vmax = max(vals) * 1.08 or 1.0
    n = len(timeline_rows)

    def x(i: int) -> float:
        return pad + i * (w - 2 * pad) / max(n - 1, 1)

    def y(v: float) -> float:
        return h - pad + 10 - (v / vmax) * (h - 2 * pad)

    parts = [
        f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
        'aria-label="Receita mensal: real, estatístico, consenso, orçamento e meta">'
    ]
    band = [(i, r) for i, r in enumerate(timeline_rows) if r.get("p10") is not None and r.get("p90") is not None]
    if band:
        pts = [f"{x(i):.1f},{y(r['p90']):.1f}" for i, r in band] + [
            f"{x(i):.1f},{y(r['p10']):.1f}" for i, r in reversed(band)
        ]
        parts.append(f'<polygon points="{" ".join(pts)}" fill="#3483fa" fill-opacity="0.10"/>')
    for key, color, dash, _ in SERIES:
        pts = [f"{x(i):.1f},{y(r[key]):.1f}" for i, r in enumerate(timeline_rows) if r.get(key) is not None]
        if len(pts) > 1:
            parts.append(
                f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2" '
                f'stroke-dasharray="{dash}"/>'
            )
    for i, r in enumerate(timeline_rows):
        if i % 3 == 0:
            parts.append(
                f'<text x="{x(i):.1f}" y="{h - 12}" font-size="10" text-anchor="middle" fill="#5f6478">'
                f"{ptbr.month_label(r['date'])}</text>"
            )
    legend = " ".join(f'<tspan fill="{c}">— {label}</tspan>' for _, c, _, label in SERIES)
    band_label = ' <tspan fill="#3483fa">▨ Faixa P10–P90 do consenso</tspan>' if band else ""
    parts.append(f'<text x="{pad}" y="16" font-size="11">{legend}{band_label}</text>')
    parts.append("</svg>")
    return "".join(parts)


# ------------------------------------------------------------------------------------------ visual tables
def _kpis_table(data: dict[str, Any]) -> str:
    rows = [
        [
            (_e(k.get("label")), ""),
            (_e(_kpi_value(k)), "n"),
            (_e(k.get("delta") or ""), ""),
            (_e(k.get("hint") or ""), "muted"),
        ]
        for k in data.get("cards") or []
    ]
    return _table(
        "Indicadores", [("Indicador", False), ("Valor", True), ("Variação", False), ("Referência", False)], rows
    )


def _bridge_table(data: dict[str, Any]) -> str:
    rows = []
    for s in data.get("steps") or []:
        delta = s.get("kind") == "delta"
        value = _ms(s.get("value")) if delta else _m(s.get("value"))
        rows.append([(_e(s.get("label")), ""), (_e(value), f"n {_tone(s.get('value')) if delta else ''}")])
    return _table(data.get("note") or "Ponte do desvio", [("Etapa", False), ("Valor (R$)", True)], rows)


def _causes_table(data: dict[str, Any]) -> str:
    rows = [
        [
            (_e(c.get("label")), ""),
            (_e(c.get("group_label")), "muted"),
            (_e(_m(c.get("abs_error"))), "n"),
            (_e(_p(c.get("share"), 0)), "n"),
        ]
        for c in data.get("causes") or []
    ]
    return _table(
        data.get("note") or "Causas do erro",
        [("Causa", False), ("Grupo", False), ("Erro absoluto (R$)", True), ("Participação", True)],
        rows,
    )


def _monthly_table(data: dict[str, Any]) -> str:
    p_label = data.get("p_label") or "Orçamento"
    rows = [
        [
            (_e(ptbr.month_label(r.get("date"))), ""),
            (_e(_m(r.get("x"))), "n"),
            (_e(_m(r.get("p"))), "n"),
            (_e(_ms(r.get("variance"))), f"n {_tone(r.get('variance'))}"),
            (_e(_p(r.get("variance_pct"), 1, True)), "n"),
        ]
        for r in data.get("rows") or []
    ]
    head = [
        ("Mês", False),
        (data.get("x_label") or "Consenso", True),
        (p_label, True),
        ("Desvio", True),
        ("Desvio %", True),
    ]
    out = _table(f"Consenso × {p_label.lower()} por mês (R$)", head, rows)
    quarters = data.get("quarters") or []
    if quarters:
        qrows = [
            [(_e(q.get("label")), ""), (_e(_ms(q.get("variance"))), f"n {_tone(q.get('variance'))}")] for q in quarters
        ]
        out += _table("Desvio por trimestre (R$)", [("Trimestre", False), ("Desvio", True)], qrows)
    return out


def _variance_table(data: dict[str, Any]) -> str:
    rows = [
        [
            (_e(r.get("label")), ""),
            (_e(_m(r.get("x"))), "n"),
            (_e(_m(r.get("p"))), "n"),
            (_e(_ms(r.get("variance"))), f"n {_tone(r.get('variance'))}"),
            (_e(_p(r.get("variance_pct"), 1, True)), "n"),
            (_e(_p(r.get("prob_hit"), 0)), "n"),
        ]
        for r in data.get("rows") or []
    ]
    others = data.get("others")
    if others:
        rows.append(
            [
                (_e(f"Demais ({others['n']})"), "muted"),
                ("", "n"),
                ("", "n"),
                (_e(_ms(others.get("value"))), f"n {_tone(others.get('value'))}"),
                ("", "n"),
                ("", "n"),
            ]
        )
    head = [
        (data.get("level_label") or "Membro", False),
        ("Consenso", True),
        ("Orçamento", True),
        ("Desvio", True),
        ("Desvio %", True),
        ("Chance de atingir", True),
    ]
    return _table("Desvio vs orçamento por membro (R$)", head, rows)


def _feasibility_table(data: dict[str, Any]) -> str:
    label = (data.get("display") or {}).get("label") or ptbr.label(ptbr.CLASSIFICATION, data.get("classification"))
    items = [
        ("P10 (consenso)", _m(data.get("p10"))),
        ("Consenso (P50)", _m(data.get("consensus"))),
        ("P90 (consenso)", _m(data.get("p90"))),
        ("Orçamento", _m(data.get("budget"))),
        ("Meta", _m(data.get("target"))),
        ("Chance de bater a meta", _p(data.get("probability"), 0)),
        ("Classificação", str(label or ptbr.NA)),
    ]
    rows = [[(_e(k), ""), (_e(v), "n")] for k, v in items]
    return _table("Viabilidade da meta", [("Indicador", False), ("Valor", True)], rows)


def _decision_table(data: dict[str, Any], h: int) -> str:
    basis = {"horizonte": f"nos próximos {h} meses", "backtest_anualizado": "erro anualizado da janela de backtest"}
    rows = [
        [
            (_e(d.get("decision")), ""),
            (_e(d.get("evidence")), "muted"),
            (f"{_e(_m(d.get('impact')))}<br><span class=muted>{_e(basis.get(d.get('impact_basis'), ''))}</span>", "n"),
            (_e(d.get("owner")), ""),
        ]
        for d in data.get("rows") or []
    ]
    if not rows:
        return '<p class="notice">Nenhuma decisão crítica neste ciclo — plano alinhado.</p>'
    head = [("Decisão", False), ("Evidência", False), ("Impacto", True), ("Responsável", False)]
    note = "Regras determinísticas sobre desvios, viabilidade, erro e ajustes — nenhum número é gerado por IA."
    return _table(note, head, rows)


def _visual(ch: dict[str, Any], h: int, timeline_rows: list[dict[str, Any]]) -> str:
    v = ch.get("visual") or {}
    kind, data = v.get("kind"), v.get("data") or {}
    if kind == "kpis":
        return _kpis_table(data)
    if kind == "bridge":
        return _bridge_table(data)
    if kind == "cause_bars":
        return _causes_table(data)
    if kind == "monthly_variance":
        chart = _svg_chart(timeline_rows)
        return (f'<div class="chart">{chart}</div>' if chart else "") + _monthly_table(data)
    if kind == "variance_bars":
        return _variance_table(data)
    if kind == "feasibility_range":
        return _feasibility_table(data)
    if kind == "decision_table":
        return _decision_table(data, h)
    return ""


def _consensus_band(timeline_rows: list[dict[str, Any]], chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Timeline rows whose p10/p90 are the CONSENSUS band of the projection chapter (``low``/``high``):
    in the journey "P10–P90" always means the consensus band, never the statistical one (spec §2.0)."""
    proj = next((c for c in chapters if c.get("id") == "projecao"), None) or {}
    rows = ((proj.get("visual") or {}).get("data") or {}).get("rows") or []
    band = {str(r.get("date"))[:10]: (r.get("low"), r.get("high")) for r in rows}
    out = []
    for r in timeline_rows:
        low, high = band.get(str(r.get("date"))[:10], (None, None))
        out.append({**r, "p10": low, "p90": high})
    return out


def _scqa(scqa: dict[str, Any]) -> str:
    return (
        f'<div class="scqa"><p><b>Situação</b> {_e(scqa.get("situacao"))}</p>'
        f"<p><b>Complicação</b> {_e(scqa.get('complicacao'))}</p>"
        f"<p><b>Resposta</b> {_e(scqa.get('resposta'))}</p></div>"
    )


def _section(ch: dict[str, Any], h: int, timeline_rows: list[dict[str, Any]], intro: str = "") -> str:
    """One chapter. ``intro`` (the SCQA) goes under the Resumo headline, as on screen."""
    eyebrow = f"Capítulo {ch['index']} de 7 · {ch['title']}"
    head = (
        f'<div class="eyebrow">{_e(eyebrow)}</div><h2>{_e(ch["headline"])}</h2>'
        f'<p class="q">{_e(ch["question"])}</p><p class="ctx">{_e(ch["context"])}</p>{intro}'
    )
    if ch.get("status") == "empty":
        return f'<section id="{_e(ch["id"])}">{head}<p class="notice">{_e(ch.get("notice"))}</p></section>'
    items = "".join(f"<li>{_rich(t['text'])}</li>" for t in ch.get("takeaways") or [])
    takeaways = f"<ol>{items}</ol>" if items else ""
    return f'<section id="{_e(ch["id"])}">{head}{takeaways}{_visual(ch, h, timeline_rows)}</section>'


def build_html(ctx: PlanningContext, filters: dict[str, Any] | None = None) -> str:
    story = clean(build_story(ctx, filters))
    signature, title = _e(AUTHOR["signature_pt"]), _e(AUTHOR["title_pt"])
    linkedin = AUTHOR["linkedin"]
    generated = f"{datetime.now():%d/%m/%Y %H:%M}"
    if not story.get("available"):
        body = f'<section><p class="notice">{_e(story.get("reason"))}</p></section>'
        ref: dict[str, Any] = {}
    else:
        ref = story["reference"]
        h = int(ref.get("horizon_months") or 0)
        chapters = story["chapters"]
        tl = _consensus_band(records(timeline(ctx, filters, "revenue", history_months=24)), chapters)
        # The governing thought is the Resumo headline (chapter 1), followed by the SCQA: printed once.
        scqa = _scqa(story["scqa"])
        body = "".join(_section(ch, h, tl, scqa if ch["id"] == "resumo" else "") for ch in chapters)
    scope = ref.get("scope_label") or "Empresa toda"
    cycle = f"Ciclo S&OP {ref['cycle_label']} · " if ref.get("cycle_label") else ""
    disclosure = ""
    if ref:
        disclosure = (
            f"Base {ref.get('dataset_version')} · execução {ref.get('run_id')} · orçamento: "
            f"{ref.get('plan_source') or ptbr.NA} · erro de previsão medido em backtest fora da amostra "
            f"({ref.get('lag_label')} de antecedência)."
        )
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{APP_NAME} · {_e(REPORT_TITLE)}</title>
<style>{CSS}</style></head><body><div class="wrap">
<header><div><div class="eyebrow">{_e(cycle)}{_e(scope)}</div><h1>{APP_NAME} · {_e(REPORT_TITLE)}</h1>
<div class="sub">{_e(ptbr.APP_TAGLINE)} — último mês com dados reais: {ptbr.month_label(ctx.last_actual, long=True)},
gerado em {generated}</div></div>
<div class="sub" style="text-align:right">{signature}<br>{title}<br>
<a href="{linkedin}">{linkedin.replace("https://", "")}</a></div></header>
{body}
<footer><p>{_e(disclosure)}</p><b>{APP_NAME}</b> — {signature} · {title} · <a href="{linkedin}">LinkedIn</a><br>{_e(FOOTER_NOTE)}</footer>
</div></body></html>"""
