"""HTTP contract of /api/deviations/* (spec §4.3.3, §4.8): validation in pt-BR, shapes, notices and
"no English in human-readable strings"."""

from __future__ import annotations

import re
from typing import Any

import pytest

from app.deviations import common
from app.services.context import get_context

CMPS = ("fc_pl", "fc_tg", "ac_pl", "ac_fc", "ac_cs")
PLAN = ("fc_pl", "fc_tg", "ac_pl")
ENGLISH = re.compile(r"\b(budget|target|revenue|balanced|over|under|none|nan)\b", re.IGNORECASE)
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


def _english(payload: Any, path: str = "$") -> list[str]:
    """Human-readable strings (values under TEXT_KEYS) that contain an English word."""
    found: list[str] = []
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k in TEXT_KEYS:
                values = v if isinstance(v, list) else [v]
                found += [f"{path}.{k}: {s}" for s in values if isinstance(s, str) and ENGLISH.search(s)]
            if isinstance(v, dict | list):
                found += _english(v, f"{path}.{k}")
    elif isinstance(payload, list):
        for i, v in enumerate(payload):
            found += _english(v, f"{path}[{i}]")
    return found


def _get(client, endpoint: str, **params) -> Any:
    r = client.get(f"/api/deviations/{endpoint}", params=params)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def ctx(api_client):
    return get_context()


@pytest.fixture(scope="module")
def series_id(ctx) -> str:
    return str(ctx.series["series_id"].iloc[0])


# ------------------------------------------------------------------------------------------ validation
@pytest.mark.parametrize(
    ("endpoint", "params", "detail"),
    [
        ("summary", {"cmp": "xx"}, common.MSG_INVALID_CMP),
        ("summary", {"cmp": "fc_pl", "period": "zz"}, common.MSG_INVALID_PERIOD),
        ("summary", {"cmp": "fc_pl", "period": "u12m"}, common.MSG_INVALID_PERIOD),
        ("summary", {"cmp": "fc_pl", "period": "2001-01"}, common.MSG_INVALID_PERIOD),
        ("summary", {"cmp": "ac_pl", "period": "h"}, common.MSG_INVALID_PERIOD),
        ("summary", {"cmp": "ac_pl", "period": "t1"}, common.MSG_INVALID_PERIOD),
        ("summary", {"cmp": "fc_pl", "level": "planeta"}, common.MSG_INVALID_LEVEL),
        ("summary", {"cmp": "fc_pl", "level": "champion"}, common.MSG_INVALID_LEVEL),
        ("summary", {"cmp": "fc_pl", "measure": "euros"}, common.MSG_INVALID_MEASURE),
        ("focus", {"cmp": "fc_tg", "focus_level": "planeta", "focus": "x"}, common.MSG_INVALID_LEVEL),
        ("focus", {"cmp": "fc_pl", "period": "t9"}, common.MSG_INVALID_PERIOD),
        ("exceptions", {"cmp": "fc_pl", "focus_level": "planeta"}, common.MSG_INVALID_LEVEL),
        ("exceptions", {"cmp": "fc_pl", "direction": "lateral"}, common.MSG_INVALID_DIRECTION),
        ("series", {"cmp": "zz", "series_id": "a|b"}, common.MSG_INVALID_CMP),
    ],
)
def test_invalid_input_is_400_in_portuguese(api_client, endpoint, params, detail):
    r = api_client.get(f"/api/deviations/{endpoint}", params=params)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == detail


def test_unknown_series_is_404(api_client, series_id):
    r = api_client.get("/api/deviations/series", params={"cmp": "fc_pl", "series_id": "Cliente X|SKU-0"})
    assert r.status_code == 404
    assert r.json()["detail"] == "Série 'Cliente X · SKU-0' não encontrada"
    r = api_client.get("/api/deviations/series", params={"cmp": "fc_pl", "series_id": series_id, "period": "zz"})
    assert r.status_code == 400 and r.json()["detail"] == common.MSG_INVALID_PERIOD


def test_missing_cmp_is_a_portuguese_422(api_client):
    r = api_client.get("/api/deviations/summary")
    assert r.status_code == 422 and r.json()["detail"].startswith("Requisição inválida")


# ------------------------------------------------------------------------------------------ shapes
@pytest.mark.parametrize("cmp", CMPS)
def test_summary_shape(api_client, cmp):
    s = _get(api_client, "summary", cmp=cmp)
    assert s["cmp"] == cmp and s["lens"] == ("plan" if cmp in PLAN else "forecast")
    if not s["available"]:
        assert s["reason"] and cmp == "ac_cs"  # the fixture has no historical adjustments
        return
    assert len(s["kpis"]) == 4
    assert all(k["label"] for k in s["kpis"])
    assert s["headline"]
    assert len(s["comparisons"]) == 5 and {c["cmp"] for c in s["comparisons"]} == set(CMPS)
    assert s["periods"][0]["code"] == common.DEFAULT_PERIOD[cmp]
    rows = s["breakdown"]["rows"]
    assert rows and all(isinstance(r["label"], str) and r["label"].strip() for r in rows)
    assert s["breakdown"]["level_label"] and s["breakdown"]["levels"]


def test_comparisons_flag_missing_history(api_client):
    s = _get(api_client, "summary", cmp="fc_pl")
    by = {c["cmp"]: c for c in s["comparisons"]}
    assert all(by[c]["available"] for c in PLAN)
    assert by["ac_cs"]["available"] is False and by["ac_cs"]["reason"] == "sem histórico de ajustes"


@pytest.mark.parametrize("cmp", PLAN)
def test_derived_plan_notice(api_client, cmp):
    s = _get(api_client, "summary", cmp=cmp)
    assert common.NOTICE_DERIVED_PLAN in s["notices"]


def test_fc_pl_kpi_matches_cockpit_gap(api_client):
    k = api_client.get("/api/sop/cockpit", params={"measure": "revenue"}).json()["kpis"]
    s = _get(api_client, "summary", cmp="fc_pl")
    assert abs(s["kpis"][0]["value"] - k["gap_vs_budget"]) <= 1e-6 * max(1.0, abs(k["budget"]))


def test_plan_periods_and_levels(api_client, ctx):
    s = _get(api_client, "summary", cmp="fc_pl", region=[ctx.series["region"].iloc[0]])
    codes = [p["code"] for p in s["periods"]]
    assert codes[:2] == ["h", "t1"] and f"{ctx.future_dates[0]:%Y-%m}" in codes
    levels = {lv["value"]: lv for lv in s["breakdown"]["levels"]}
    assert levels["region"]["disabled"] and levels["region"]["reason"].startswith("Já filtrado:")
    assert s["breakdown"]["level"] == "channel" and s["node"]["path"][0]["dim"] == "region"
    month = f"{ctx.future_dates[1]:%Y-%m}"
    m = _get(api_client, "summary", cmp="fc_pl", period=month)
    assert m["period"]["code"] == month and len(m["period"]["months"]) == 1


def test_focus_and_exceptions_flow(api_client):
    s = _get(api_client, "summary", cmp="fc_pl", level="customer")
    member = s["breakdown"]["rows"][0]["key"]
    f = _get(api_client, "focus", cmp="fc_pl", focus_level="customer", focus=member)
    assert f["focus"]["member"] == member and f["headline"]
    assert [b["key"] for b in f["bridge"]] == ["reference", "volume", "mix", "price", "events", "compared"]
    assert f["monthly"] and f["quarters"] and isinstance(f["diagnosis"], list) and len(f["diagnosis"]) <= 3
    ask = [a for a in f["actions"] if a["kind"] == "ask_ai"]
    assert ask and ask[0]["prefill"]["question"]
    e = _get(api_client, "exceptions", cmp="fc_pl", direction="all", focus_level="customer", focus=member, limit=2)
    assert e["total"] >= len(e["rows"]) and len(e["rows"]) <= 2
    for r in e["rows"]:
        assert r["customer"] == member and r["impact"] >= 0 and r["recommended_action"]["label"]


def test_series_drawer(api_client, series_id):
    d = _get(api_client, "series", cmp="fc_pl", series_id=series_id)
    assert d["series_id"] == series_id and d["label"]
    assert d["header"]["customer"] and d["header"]["series_type_label"]
    assert d["timeline"] and d["months"] and d["evidence"] is None
    assert {"volume", "mix", "price", "events"} <= set(d["effects"])
    assert "realized_variance_pct" in d["summary"]
    u = _get(api_client, "series", cmp="ac_pl", series_id=series_id, measure="units")
    assert u["effects"]["mix"] is None and u["effects"]["price"] is None


def test_units_measure_bridge(api_client):
    f = _get(api_client, "focus", cmp="fc_tg", measure="units")
    assert [b["key"] for b in f["bridge"]] == [
        "reference",
        "challenge",
        "budget_subtotal",
        "volume",
        "events",
        "compared",
    ]


# ------------------------------------------------------------------------------------------ pt-BR
@pytest.mark.parametrize("cmp", CMPS)
def test_no_english_in_human_readable_strings(api_client, ctx, cmp, series_id):
    period = None if cmp in PLAN else "bt"
    payloads = [
        _get(api_client, "summary", cmp=cmp),
        _get(
            api_client, "summary", cmp=cmp, measure="units", level="series", customer=[ctx.series["customer"].iloc[0]]
        ),
        _get(api_client, "focus", cmp=cmp),
        _get(api_client, "exceptions", cmp=cmp, **({"direction": "all"} if cmp in PLAN else {})),
        _get(api_client, "series", cmp=cmp, series_id=series_id),
    ]
    s = payloads[0]
    if s["available"] and s["breakdown"]["rows"]:
        row = s["breakdown"]["rows"][0]
        payloads.append(_get(api_client, "focus", cmp=cmp, focus_level=s["breakdown"]["level"], focus=row["key"]))
    if period is None:
        payloads.append(_get(api_client, "focus", cmp=cmp, measure="units"))
    bad = [hit for p in payloads for hit in _english(p)]
    assert not bad, bad


def test_scanner_catches_english():
    assert _english({"hint": "Budget gap", "rows": [{"label": "ok"}], "notices": ["nan"]}) == [
        "$.hint: Budget gap",
        "$.notices: nan",
    ]
    assert _english({"bias_class": "Over", "key": "budget_subtotal", "lens": "plan"}) == []


def test_focus_level_defaults_to_the_breakdown_level(api_client):
    """The frontend sends ``level`` with every call; a focus without ``focus_level`` belongs to it."""
    s = _get(api_client, "summary", cmp="fc_pl", level="customer")
    member = s["breakdown"]["rows"][0]["key"]
    f = _get(api_client, "focus", cmp="fc_pl", level="customer", focus=member)
    assert f["available"] and f["focus"]["level"] == "customer" and f["focus"]["member"] == member
    e = _get(api_client, "exceptions", cmp="fc_pl", level="customer", focus=member, direction="all")
    assert all(r["customer"] == member for r in e["rows"])
