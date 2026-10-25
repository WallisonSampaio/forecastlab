"""Self-contained executive HTML report (inline CSS + SVG, no external assets)."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from app.alerts.engine import build_alerts
from app.config import APP_NAME, APP_TAGLINE, AUTHOR
from app.fva.fva import fva_report
from app.services.context import PlanningContext
from app.sop.cockpit import cockpit

CSS = """
:root{--ink:#1f2430;--muted:#6b7080;--line:#e3e3e3;--bg:#ededed;--card:#fff;--brand:#3483fa;--green:#059669;
--red:#dc2626;--amber:#d97706;--blue:#2563eb}
*{box-sizing:border-box}body{margin:0;font-family:Inter,Segoe UI,system-ui,sans-serif;background:var(--bg);color:var(--ink)}
.wrap{max-width:1180px;margin:0 auto;padding:32px 24px;border-top:6px solid #ffe600}header{display:flex;justify-content:space-between;align-items:flex-end;
border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:24px}h1{margin:0;font-size:28px;letter-spacing:-.02em}
h2{font-size:16px;margin:28px 0 12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.sub{color:var(--muted);font-size:13px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.k{font-size:12px;color:var(--muted)}.v{font-size:24px;font-weight:700;margin-top:4px;font-variant-numeric:tabular-nums}
.d{font-size:12px;margin-top:2px}.pos{color:var(--green)}.neg{color:var(--red)}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:13px}
th{background:#2d3277;color:#fff;text-align:left;padding:8px 10px;font-weight:600}td{padding:8px 10px;border-top:1px solid var(--line)}
td.n{text-align:right;font-variant-numeric:tabular-nums}.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:700}
.REALISTIC{background:#d1fae5;color:#065f46}.STRETCH{background:#fef3c7;color:#92400e}.AGGRESSIVE{background:#fee2e2;color:#991b1b}
.UNDERESTIMATED{background:#dbeafe;color:#1e40af}footer{margin-top:40px;border-top:1px solid var(--line);padding-top:16px;font-size:12px;color:var(--muted)}
a{color:var(--brand)}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:800px){.grid{grid-template-columns:repeat(2,1fr)}.two{grid-template-columns:1fr}}
"""


def _m(v: float | None) -> str:
    if v is None:
        return "n/a"
    a = abs(v)
    s = f"{a / 1e6:.2f}M" if a >= 1e6 else f"{a / 1e3:.1f}K" if a >= 1e3 else f"{a:.0f}"
    return ("-" if v < 0 else "") + "R$ " + s


def _p(v: float | None, signed: bool = False) -> str:
    if v is None:
        return "n/a"
    return f"{v * 100:+.1f}%" if signed else f"{v * 100:.1f}%"


def _svg_chart(timeline: list[dict[str, Any]]) -> str:
    w, h, pad = 1100, 300, 48
    keys = [
        ("actual", "#0b1220", ""),
        ("consensus", "#059669", ""),
        ("base", "#4f46e5", "4 3"),
        ("budget", "#d97706", "6 4"),
        ("target", "#dc2626", "2 3"),
    ]
    vals = [r.get(k) for r in timeline for k, *_ in keys if r.get(k) is not None]
    if not vals:
        return ""
    vmax = max(vals) * 1.08
    n = len(timeline)

    def x(i: int) -> float:
        return pad + i * (w - 2 * pad) / max(n - 1, 1)

    def y(v: float) -> float:
        return h - pad + 10 - (v / vmax) * (h - 2 * pad)

    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Revenue timeline">']
    for g in range(5):
        gv = vmax * g / 4
        parts.append(f'<line x1="{pad}" x2="{w - pad}" y1="{y(gv):.1f}" y2="{y(gv):.1f}" stroke="#e2e8f0"/>')
        parts.append(
            f'<text x="{pad - 6}" y="{y(gv) + 4:.1f}" font-size="10" text-anchor="end" fill="#64748b">{_m(gv)}</text>'
        )
    band = [(i, r) for i, r in enumerate(timeline) if r.get("p10") is not None and r.get("p90") is not None]
    if band:
        pts = [f"{x(i):.1f},{y(r['p90']):.1f}" for i, r in band] + [
            f"{x(i):.1f},{y(r['p10']):.1f}" for i, r in reversed(band)
        ]
        parts.append(f'<polygon points="{" ".join(pts)}" fill="#4f46e5" fill-opacity="0.10"/>')
    for key, color, dash in keys:
        pts = [f"{x(i):.1f},{y(r[key]):.1f}" for i, r in enumerate(timeline) if r.get(key) is not None]
        if len(pts) > 1:
            parts.append(
                f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2" '
                f'stroke-dasharray="{dash}"/>'
            )
    for i, r in enumerate(timeline):
        if i % 3 == 0:
            parts.append(
                f'<text x="{x(i):.1f}" y="{h - 12}" font-size="10" text-anchor="middle" fill="#64748b">'
                f"{str(r['date'])[:7]}</text>"
            )
    legend = " ".join(f'<tspan fill="{c}">■ {k.title()}</tspan>' for k, c, _ in keys)
    parts.append(f'<text x="{pad}" y="16" font-size="11">{legend} <tspan fill="#4f46e5">▨ P10-P90</tspan></text>')
    parts.append("</svg>")
    return "".join(parts)


def build_html(ctx: PlanningContext, filters: dict[str, Any] | None = None) -> str:
    ck = cockpit(ctx, filters, "revenue")
    k = ck.get("kpis", {})
    f = ck.get("feasibility") or {}
    fva = fva_report(ctx, filters)
    alerts = build_alerts(ctx)[:8]
    e = html.escape

    def card(label: str, value: str, delta: str = "", tone: str = "") -> str:
        return (
            f'<div class="card"><div class="k">{e(label)}</div><div class="v">{value}</div>'
            f'<div class="d {tone}">{delta}</div></div>'
        )

    gb = k.get("gap_vs_budget_pct")
    cards = "".join(
        [
            card("Actual (last 12M)", _m(k.get("actual_ltm")), f"{_p(k.get('actual_growth'), True)} YoY"),
            card("Statistical forecast 12M", _m(k.get("statistical"))),
            card("Consensus forecast 12M", _m(k.get("consensus")), f"+ {_m(k.get('incremental'))} events"),
            card("Budget 12M", _m(k.get("budget")), f"Gap {_p(gb, True)}", "pos" if (gb or 0) >= 0 else "neg"),
            card("Sales target 12M", _m(k.get("target")), f"Gap {_p(k.get('gap_vs_target_pct'), True)}"),
            card("Forecast accuracy", _p(k.get("accuracy")), f"WMAPE {_p(k.get('wmape'))}"),
            card("Bias", _p(k.get("bias"), True), e(str(k.get("bias_class") or ""))),
            card("Revenue at risk", _m(k.get("risk")), f"Opportunity {_m(k.get('opportunity'))}"),
        ]
    )
    risks = "".join(
        f"<tr><td>{e(str(r.get('customer')))}</td><td>{e(str(r.get('sku')))} {e(str(r.get('product')))}"
        f"</td><td class=n>{_m(r.get('consensus'))}</td><td class=n>{_m(r.get('budget'))}</td>"
        f"<td class=n>{_m(r.get('gap'))}</td></tr>"
        for r in ck.get("risks", [])[:8]
    )
    feas_rows = "".join(
        f"<tr><td>{e(str(r['member']))}</td><td class=n>{_m(r['target'])}</td><td class=n>"
        f"{_m(r['consensus'])}</td><td class=n>{_p(r['probability'])}</td><td><span class='badge "
        f"{r['classification']}'>{r['classification']}</span></td></tr>"
        for r in ck.get("feasibility_by_region", [])
    )
    alert_rows = "".join(
        f"<tr><td>{a['icon']} {e(a['title'])}</td><td>{e(str(a['entity'].get('customer', '')))} "
        f"{e(str(a['entity'].get('sku') or ''))}</td><td>{e(a['magnitude'])}</td>"
        f"<td>{e(a['recommendation'])}</td></tr>"
        for a in alerts
    )
    fs = fva.get("summary", {})
    st = fva.get("stairstep", {})
    reasons = "".join(f"<li>{e(r)}</li>" for r in f.get("reasons", []))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{APP_NAME} - Executive S&amp;OP Report</title>
<style>{CSS}</style></head><body><div class="wrap">
<header><div><h1>{APP_NAME} · Executive S&amp;OP Report</h1><div class="sub">{e(APP_TAGLINE)} — dataset {e(ctx.version)},
run {e(ctx.run_id or "-")}, last actual {ctx.last_actual:%b %Y}, generated {datetime.now():%Y-%m-%d %H:%M}</div></div>
<div class="sub" style="text-align:right">{e(AUTHOR["signature_en"])}<br>{e(AUTHOR["title_en"])}<br>
<a href="{AUTHOR["linkedin"]}">{AUTHOR["linkedin"].replace("https://", "")}</a></div></header>
<div class="grid">{cards}</div>
<h2>Demand plan — actual, statistical, consensus, budget and target (R$)</h2><div class="card">{_svg_chart(ck.get("timeline", []))}</div>
<div class="two"><div><h2>Target feasibility</h2><div class="card"><span class="badge {f.get("classification", "")}">
{f.get("classification", "n/a")}</span> &nbsp; Probability of reaching target: <b>{_p(f.get("probability"))}</b>
<ul>{reasons}</ul><p>{e(f.get("recommendation", ""))}</p></div></div>
<div><h2>Forecast Value Added</h2><div class="card">Naive WMAPE <b>{_p(st.get("naive"))}</b> → Statistical <b>{_p(st.get("statistical"))}</b>
→ Consensus <b>{_p(st.get("consensus"))}</b><br><br>{fs.get("overrides", 0)} overrides evaluated —
<b>{_p(fs.get("value_added_pct"))}</b> added value; FVA on overridden cells <b>{_p(fs.get("fva_pp_overridden"), True)}</b> WMAPE points.</div></div></div>
<h2>Feasibility by region</h2><table><tr><th>Region</th><th>Target</th><th>Consensus</th><th>Probability</th><th>Class</th></tr>{feas_rows}</table>
<h2>Top risks vs budget</h2><table><tr><th>Customer</th><th>SKU</th><th>Consensus</th><th>Budget</th><th>Gap</th></tr>{risks}</table>
<h2>Alert center</h2><table><tr><th>Alert</th><th>Entity</th><th>Magnitude</th><th>Recommended investigation</th></tr>{alert_rows}</table>
<footer><b>{APP_NAME}</b> — {e(AUTHOR["signature_en"])} · {e(AUTHOR["title_en"])} ·
<a href="{AUTHOR["linkedin"]}">LinkedIn</a><br>Synthetic, fictitious demo data. Numbers are produced by statistical engines; the
AI layer only explains them.</footer></div></body></html>"""
