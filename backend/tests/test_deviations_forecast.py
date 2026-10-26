"""Forecast-error lens of the deep dive (spec §4.2.7, §4.3.3, §4.8): identities against the existing
metrics (backtest_metrics, fva_report), additivity of causes / systematic + noise / breakdown, one cause
per cell, the endpoint shapes and the ac_cs capability rules.

The ``api_client`` fixture (2 customers, derived plan) has NO historical overrides: ac_cs is unavailable
there. The ac_cs arithmetic is exercised with monkeypatched historical adjustments (cache cleared around).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from app.deviations import common, forecast_error, narrative, rootcause, service
from app.fva.fva import fva_report
from app.services import context, datasets
from app.services.context import backtest_metrics, filter_ids

TOL = 1e-9


@pytest.fixture
def ctx(api_client):
    common.clear_cache()
    c = context.get_context()
    yield c
    common.clear_cache()


def _all_cells(ctx, cmp="ac_fc", filters=None):
    return forecast_error.error_cells(ctx, cmp, filter_ids(ctx, filters or {}), common.backtest_months(ctx))


# ------------------------------------------------------------------------------------------ cells
def test_error_cells_contract_and_one_cause_per_cell(ctx):
    cells = _all_cells(ctx)
    assert list(cells.columns[: len(forecast_error.ERROR_CELL_COLUMNS)]) == forecast_error.ERROR_CELL_COLUMNS
    assert len(cells) == len(ctx.backtest)
    assert not cells.duplicated(["series_id", "date"]).any()
    assert cells["cause"].notna().all()
    assert set(cells["cause"]) <= set(rootcause.CAUSES)
    assert (cells["group"] == cells["cause"].map(lambda c: rootcause.CAUSES[c][1])).all()
    # ac_fc: F = F_stat, adj = 0; e = F − A; AE = |e·p|
    assert (cells["adj"] == 0).all()
    assert np.allclose(cells["forecast"], cells["forecast_stat"])
    assert np.allclose(cells["e"], cells["forecast"] - cells["actual"])
    assert np.allclose(cells["AE"], (cells["e"] * cells["p"]).abs())
    # rmse / ts are series constants computed on the whole window, whatever the months asked
    one_month = common.backtest_months(ctx)[-1:]
    part = forecast_error.error_cells(ctx, "ac_fc", filter_ids(ctx, {}), one_month)
    full = cells.set_index(["series_id", "date"])
    for r in part.itertuples():
        assert full.at[(r.series_id, r.date), "rmse"] == pytest.approx(r.rmse)
        assert full.at[(r.series_id, r.date), "ts"] == pytest.approx(r.ts)


def test_cell_causes_match_rule_function(ctx):
    cells = _all_cells(ctx)
    for r in cells.head(60).to_dict("records"):
        assert rootcause.cell_cause(r, "ac_fc") == r["cause"]


def test_rmse_is_the_interval_sigma_and_ts_matches_alerts(ctx):
    cells = _all_cells(ctx)
    for sid, g in cells.groupby("series_id"):
        e = (g["forecast_stat"] - g["actual"]).to_numpy()
        assert g["rmse"].iloc[0] == pytest.approx(math.sqrt(float(np.mean(e**2))))
        last = g.sort_values("date").tail(6)
        err = (last["forecast"] - last["actual"]).to_numpy(float)
        mad = np.mean(np.abs(err))
        assert g["ts"].iloc[0] == pytest.approx(float(err.sum() / mad) if mad else 0.0)


# ------------------------------------------------------------------------------------------ identities
@pytest.mark.parametrize("filters", [{}, {"customer": ["Vila Verde Mercados"]}, {"customer": ["CuraMais Farmácias"]}])
def test_ac_fc_wmape_and_bias_equal_backtest_metrics(ctx, filters):
    ids = filter_ids(ctx, filters)
    m = forecast_error.node_metrics(_all_cells(ctx, filters=filters))
    ref = backtest_metrics(ctx, ids)
    assert m["wmape"] == pytest.approx(ref["wmape"], abs=TOL)
    assert m["bias"] == pytest.approx(ref["bias"], abs=TOL)
    assert m["accuracy"] == pytest.approx(ref["accuracy"], abs=TOL)


def test_summary_kpis_equal_backtest_metrics(ctx):
    s = service.summary(ctx, {}, "ac_fc")
    ref = backtest_metrics(ctx, filter_ids(ctx, {}))
    assert s["available"] is True
    assert len(s["kpis"]) == 4
    kpi = {k["id"]: k for k in s["kpis"]}
    assert kpi["accuracy"]["value"] == pytest.approx(1 - ref["wmape"], abs=TOL)
    assert kpi["bias"]["value"] == pytest.approx(ref["bias"], abs=TOL)
    assert kpi["abs_error"]["value"] == pytest.approx(forecast_error.node_metrics(_all_cells(ctx))["abs_error"])


def test_naive_wmape_equals_fva_stairstep(ctx):
    assert forecast_error.naive_wmape(ctx) == pytest.approx(fva_report(ctx)["stairstep"]["naive"], abs=TOL)


def test_causes_add_up_and_split_is_additive(ctx):
    cells = _all_cells(ctx)
    total = float(cells["AE"].sum())
    causes = forecast_error.cause_rows(cells)
    assert causes, "the fixture has backtest error"
    assert sum(c["abs_error"] for c in causes) == pytest.approx(total, rel=TOL)
    assert sum(c["share"] for c in causes) == pytest.approx(1.0, abs=TOL)
    assert sum(c["n_cells"] for c in causes) == len(cells)
    # grouped controllable -> inherent -> unexplained
    order = [rootcause.GROUP_ORDER.index(c["group"]) for c in causes]
    assert order == sorted(order)
    for c in causes:
        assert c["direction"] in ("over", "under", "mixed")
        assert c["group_label"] == rootcause.GROUP_LABEL[c["group"]]
    m = forecast_error.node_metrics(cells)
    assert m["systematic"] + m["noise"] == pytest.approx(m["abs_error"], rel=TOL)
    assert 0 <= m["systematic"] <= m["abs_error"] + TOL
    assert sum(forecast_error.group_shares(cells).values()) == pytest.approx(1.0, abs=TOL)


def test_focus_causes_split_and_monthly(ctx):
    f = service.focus(ctx, {}, "ac_fc")
    cells = _all_cells(ctx)
    total = float(cells["AE"].sum())
    assert f["available"] is True and f["lens"] == "forecast"
    assert sum(c["abs_error"] for c in f["causes"]) == pytest.approx(total, rel=1e-9)
    assert sum(c["share"] for c in f["causes"]) == pytest.approx(1.0, abs=TOL)
    assert f["split"]["systematic"] + f["split"]["noise"] == pytest.approx(total, rel=1e-9)
    assert f["bridge"] is None and f["drivers"] is None and f["quarters"] is None
    assert [r["date"] for r in f["monthly"]] == [f"{d:%Y-%m-%d}" for d in common.backtest_months(ctx)]
    assert sum(r["abs_error"] for r in f["monthly"]) == pytest.approx(total, rel=1e-9)
    assert 1 <= len(f["diagnosis"]) <= 3
    assert f["by_model"] and len(f["by_model"]) <= forecast_error.TOP_MODELS
    assert f["fva"] is None
    assert any(a["kind"] == "ask_ai" for a in f["actions"])


def test_breakdown_is_additive_and_drill_consistent(ctx):
    s = service.summary(ctx, {}, "ac_fc", level="customer")
    rows, others = s["breakdown"]["rows"], s["breakdown"]["others"]
    node_ae = next(k for k in s["kpis"] if k["id"] == "abs_error")["value"]
    assert sum(r["abs_error"] for r in rows) + (others["value"] if others else 0) == pytest.approx(node_ae)
    assert sum(r["share"] for r in rows) + (others["value"] / node_ae if others else 0) == pytest.approx(1.0)
    for r in rows:
        assert r["label"]
        assert r["systematic"] + r["noise"] == pytest.approx(r["abs_error"])
        assert r["drillable"] == (r["n_series"] > 1)
        # drilling into the member gives the same numbers
        sub = service.summary(ctx, {"customer": [r["key"]]}, "ac_fc")
        kpi = {k["id"]: k for k in sub["kpis"]}
        assert kpi["abs_error"]["value"] == pytest.approx(r["abs_error"])
        assert 1 - kpi["accuracy"]["value"] == pytest.approx(r["wmape"])
    assert [r["abs_error"] for r in rows] == sorted((r["abs_error"] for r in rows), reverse=True)
    conc = s["concentration"]
    assert conc is None or 1 <= conc["n_top"] <= forecast_error.CONC_MAX


@pytest.mark.parametrize("level", ["region", "category", "sku", "series", "champion", "series_type"])
def test_every_level_renders(ctx, level):
    s = service.summary(ctx, {}, "ac_fc", level=level)
    b = s["breakdown"]
    assert b["level"] == level and b["level_label"] == common.LEVEL_LABEL[level]
    assert all(r["label"] for r in b["rows"])
    if level in ("series", "champion", "series_type"):
        assert not any(r["drillable"] for r in b["rows"])
    if level == "series":
        assert all(r["series_id"] == r["key"] for r in b["rows"])
    assert {lv["value"] for lv in b["levels"]} == set(common.FORECAST_LEVELS)


def test_month_period_and_few_months_notice(ctx):
    month = common.backtest_months(ctx)[-1]
    s = service.summary(ctx, {}, "ac_fc", period=f"{month:%Y-%m}")
    assert s["period"]["months"] == [f"{month:%Y-%m-%d}"]
    assert forecast_error.NOTE_FEW_MONTHS in s["notices"]
    with pytest.raises(common.DeviationError):
        service.summary(ctx, {}, "ac_fc", period="h")


def test_empty_node_is_unavailable_with_portuguese_reason(ctx):
    s = service.summary(ctx, {"customer": ["Cliente Inexistente"]}, "ac_fc")
    assert s["available"] is False and s["reason"] == forecast_error.MSG_EMPTY_NODE
    assert s["node"]["n_series"] == 0


# ------------------------------------------------------------------------------------------ exceptions / series
def test_exceptions_follow_the_rule_and_sort_by_impact(ctx):
    e = service.exceptions(ctx, {}, "ac_fc", limit=200)
    rows = e["rows"]
    assert e["total"] == len(rows)
    assert [r["impact"] for r in rows] == sorted((r["impact"] for r in rows), reverse=True)
    share = forecast_error._rev_share(ctx)
    for r in rows:
        assert forecast_error._is_exception(r["wmape"], r["bias"], r["tracking_signal"], share.get(r["series_id"], 0))
        assert r["impact"] >= 0 and r["label"] and r["recommended_action"]["label"]
        assert {a["kind"] for a in r["actions"]} >= {"open_series", "ask_ai"}
    page = service.exceptions(ctx, {}, "ac_fc", limit=1, offset=0)
    assert page["total"] == e["total"] and len(page["rows"]) <= 1
    with pytest.raises(common.DeviationError):
        service.exceptions(ctx, {}, "ac_fc", cause="inexistente")
    if rows:
        code = rows[0]["top_cause"]["code"]
        only = service.exceptions(ctx, {}, "ac_fc", cause=code, limit=200)
        assert only["total"] >= 1 and all(r["top_cause"]["code"] == code for r in only["rows"])
    for r in rows:  # fixed row menu (spec §2.3.4)
        assert [a["kind"] for a in r["actions"]][:4] == list(rootcause.MENU_ORDER)


def test_cause_filter_lists_every_series_led_by_the_cause(ctx):
    """``cause`` (CauseBars click / report link) lists all series whose top cause it is, by impact —
    not only the exception series (otherwise the inherent causes would always give an empty table)."""
    st = forecast_error._series_table(ctx, _all_cells(ctx))
    codes = sorted(set(st["top_cause"].dropna()))
    assert codes
    for code in codes:
        out = service.exceptions(ctx, {}, "ac_fc", cause=code, limit=200)
        assert out["total"] == int((st["top_cause"] == code).sum()) == len(out["rows"])
        assert all(r["top_cause"]["code"] == code for r in out["rows"])
        assert [r["impact"] for r in out["rows"]] == sorted((r["impact"] for r in out["rows"]), reverse=True)
    assert service.exceptions(ctx, {}, "ac_fc", cause="ajuste_piorou") == {"total": 0, "rows": []}


def test_both_lenses_offer_the_same_comparisons(ctx):
    plan_side = service.summary(ctx, {}, "fc_pl")["comparisons"]
    assert service.summary(ctx, {}, "ac_fc")["comparisons"] == plan_side
    assert service.summary(ctx, {}, "ac_cs")["comparisons"] == plan_side


def test_series_drawer(ctx):
    sid = ctx.series["series_id"].iloc[0]
    d = service.series(ctx, sid, "ac_fc")
    cells = _all_cells(ctx, filters={"customer": [sid.split("|")[0]], "sku": [sid.split("|")[1]]})
    assert d["series_id"] == sid and d["label"]
    assert len(d["evidence"]) == len(cells)
    assert sum(r["error"] for r in d["evidence"]) == pytest.approx(d["summary"]["variance"])
    for r in d["evidence"]:
        assert r["cause"]["code"] in rootcause.CAUSES and r["evidence"]
    assert d["months"] is None and d["effects"] is None
    kinds = [a["kind"] for a in d["actions"]]
    assert "open_workspace" in kinds and "open_series" not in kinds
    assert len(d["timeline"]) > 0
    with pytest.raises(common.DeviationError) as exc:
        service.series(ctx, "X|Y", "ac_fc")
    assert exc.value.status == 404


# ------------------------------------------------------------------------------------------ ac_cs
def test_ac_cs_without_history_is_unavailable(ctx):
    assert not forecast_error.has_history(ctx)
    s = service.summary(ctx, {}, "ac_cs")
    assert s["available"] is False and s["reason"] == common.MSG_NO_OVERRIDES
    assert "ajustes" in s["reason"]
    f = service.focus(ctx, {}, "ac_cs")
    assert f["available"] is False and f["reason"] == common.MSG_NO_OVERRIDES
    assert service.exceptions(ctx, {}, "ac_cs") == {"total": 0, "rows": []}
    comp = {c["cmp"]: c for c in s["comparisons"]}
    assert comp["ac_cs"]["available"] is False and comp["ac_fc"]["available"] is True


def test_ac_cs_with_adjustments_matches_fva(ctx, monkeypatch):
    """Monkeypatched historical adjustments: consensus WMAPE == fva stairstep consensus, FVA KPI coherent."""
    bt = ctx.backtest.sort_values(["series_id", "date"]).reset_index(drop=True)
    pick = bt.iloc[::3]
    rng = np.random.default_rng(1)
    attrs = ctx.series.set_index("series_id")
    hist = pd.DataFrame(
        {
            "dataset_version": ctx.version,
            "date": pick["date"].to_numpy(),
            "customer": pick["series_id"].map(attrs["customer"]).to_numpy(),
            "sku": pick["series_id"].map(attrs["sku"]).to_numpy(),
            "planner": "Planejador de Demanda",
            "event_type": "Promoção",
            "adjustment_pct": rng.uniform(-0.3, 0.4, len(pick)),
            "comment": "teste",
        }
    )
    adj = pd.DataFrame(
        {
            "series_id": hist["customer"] + "|" + hist["sku"],
            "date": pd.to_datetime(hist["date"]),
            "hist_adj": hist["adjustment_pct"],
        }
    )
    monkeypatch.setattr(forecast_error, "historical_adjustments", lambda c: adj)
    monkeypatch.setattr(datasets, "get_historical_overrides", lambda v=None: hist.copy())
    common.clear_cache()

    cells = _all_cells(ctx, "ac_cs")
    assert (cells["adj"] != 0).sum() == len(pick)
    assert np.allclose(cells["forecast"], (cells["forecast_stat"] * (1 + cells["adj"])).clip(lower=0))
    stair = fva_report(ctx)["stairstep"]
    m = forecast_error.node_metrics(cells)
    assert m["wmape"] == pytest.approx(stair["consensus"], abs=TOL)
    fva = forecast_error._fva(cells)
    assert fva["statistical_wmape"] == pytest.approx(stair["statistical"], abs=TOL)
    assert fva["fva_pp"] == pytest.approx(stair["fva_consensus_vs_statistical"], abs=TOL)
    # ajuste_piorou only where the adjustment made the cell worse
    worse = cells[cells["cause"] == "ajuste_piorou"]
    assert (worse["adj"] != 0).all()
    assert ((worse["forecast"] - worse["actual"]).abs() > (worse["forecast_stat"] - worse["actual"]).abs()).all()

    s = service.summary(ctx, {}, "ac_cs")
    assert s["available"] is True
    kpi = {k["id"]: k for k in s["kpis"]}
    assert list(kpi) == ["accuracy", "bias", "abs_error", "fva"]
    assert kpi["fva"]["format"] == "pp" and kpi["fva"]["value"] == pytest.approx(fva["fva_pp"])
    assert "de consenso" in s["headline"]
    f = service.focus(ctx, {}, "ac_cs")
    assert f["fva"]["fva_pp"] == pytest.approx(fva["fva_pp"])
    assert any(d.startswith("Ajustes comerciais:") for d in f["diagnosis"])
    ask = [a for a in f["actions"] if a["kind"] == "ask_ai"]
    assert ask and ask[0]["prefill"]["question"] == "Quais ajustes comerciais pioraram a acurácia?"
    common.clear_cache()


# ------------------------------------------------------------------------------------------ copy
ENGLISH = {"budget", "target", "revenue", "balanced", "over", "under", "none", "nan"}
TEXT_KEYS = {
    "label",
    "headline",
    "reason",
    "notices",
    "hint",
    "text",
    "delta",
    "diagnosis",
    "evidence",
    "note",
    "level_label",
    "group_label",
}


def _texts(obj, key=None):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _texts(v, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _texts(v, key)
    elif isinstance(obj, str) and key in TEXT_KEYS:
        yield obj


def test_forecast_lens_text_is_portuguese(ctx):
    sid = ctx.series["series_id"].iloc[0]
    payloads = [
        service.summary(ctx, {}, "ac_fc"),
        service.summary(ctx, {}, "ac_fc", level="champion"),
        service.focus(ctx, {}, "ac_fc"),
        service.focus(ctx, {}, "ac_fc", focus_level="customer", focus=ctx.series["customer"].iloc[0]),
        service.exceptions(ctx, {}, "ac_fc", limit=50),
        service.series(ctx, sid, "ac_fc"),
        service.summary(ctx, {}, "ac_cs"),
    ]
    import re

    for p in payloads:
        for text in _texts(p):
            words = {w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ]+", text)}
            assert not (words & ENGLISH), text
            assert "n/d" not in text and "nan" not in text.lower().split()


def test_headlines_use_ptbr_numbers(ctx):
    s = service.summary(ctx, {}, "ac_fc")
    m = forecast_error.node_metrics(_all_cells(ctx))
    assert narrative.P1(m["wmape"]) in s["headline"]
    assert narrative.M(m["abs_error"]) in s["headline"]
    assert len(s["headline"]) <= 260
    f = service.focus(ctx, {}, "ac_fc", focus_level="customer", focus=ctx.series["customer"].iloc[0])
    assert f["headline"].startswith(ctx.series["customer"].iloc[0] + ": erro de ")


def _cause(code: str, share: float) -> dict:
    label, group = rootcause.CAUSES[code]
    return {"code": code, "label": label, "group": group, "abs_error": share * 100.0, "share": share}


def test_inherent_top_cause_also_names_the_leading_controllable_cause():
    causes = [_cause("promocao", 0.19), _cause("patamar", 0.11), _cause("volatilidade", 0.27), _cause("ruido", 0.2)]
    cause1 = forecast_error.top_cause(causes)
    assert cause1["code"] == "volatilidade"
    lead = forecast_error.lead_controllable(causes, cause1)
    assert lead["code"] == "promocao"
    # a controllable top cause, or a negligible controllable share, adds nothing
    assert forecast_error.lead_controllable(causes[:2], causes[0]) is None
    tiny = [_cause("preco", forecast_error.LEAD_CONTROLLABLE_MIN_SHARE / 2), _cause("volatilidade", 0.6)]
    assert forecast_error.lead_controllable(tiny, tiny[1]) is None

    text = narrative.forecast_diagnosis(
        {
            "systematic_share": 0.32,
            "cause1": cause1["label"],
            "cause1_abs_error": 27.0,
            "cause1_n_cells": 10,
            "cause1_direction": "mixed",
            "lead_controllable": lead["label"],
            "lead_controllable_abs_error": 19.0,
            "lead_controllable_share": 0.19,
        },
        "ac_fc",
    )
    assert len(text) == 3
    assert text[2].startswith("Entre as causas controláveis, promoção não antecipada lidera")
    assert "19% do erro" in text[2]


def test_company_focus_actions_follow_the_leading_controllable_cause(ctx):
    f = service.focus(ctx, {}, "ac_fc", None, "revenue")
    lead = forecast_error.lead_controllable(f["causes"], forecast_error.top_cause(f["causes"]))
    if lead is None:  # fixture without an inherent top cause: the rule does not apply
        return
    assert any(lead["label"].lower() in d for d in f["diagnosis"])
    assert any(a["kind"] != "ask_ai" for a in f["actions"])
