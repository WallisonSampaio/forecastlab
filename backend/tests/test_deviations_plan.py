"""Plan lens of the deviation deep dive (spec §4.2.2–§4.2.6, §4.8): full grid, exact PVM bridge,
additivity, drill consistency, probability, recurrence and the Paasche price index."""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from app.deviations import cells, common, plan, service
from app.services.context import get_context
from app.sop.cockpit import cockpit
from app.sop.feasibility import assess

PLAN_CMPS = ("fc_pl", "fc_tg", "ac_pl")


@pytest.fixture(scope="module")
def ctx(api_client):
    c = get_context()
    assert c.has_run and not c.plan.empty
    return c


def _close(a: float, b: float, scale: float) -> bool:
    return abs(a - b) <= 1e-6 * max(1.0, abs(scale))


def _steps(focus: dict) -> dict[str, float]:
    return {s["key"]: s["value"] for s in focus["bridge"]}


def _regions(ctx) -> list[str]:
    return sorted(ctx.series["region"].unique())


def _periods(ctx, cmp: str) -> list[str | None]:
    out: list[str | None] = [None]
    if cmp in ("fc_pl", "fc_tg"):
        out += [q for q, _ in common.quarters(ctx)]
        out.append(f"{ctx.future_dates[0]:%Y-%m}")
    else:
        out.append(f"{ctx.ltm_dates[-1]:%Y-%m}")
    return out


# ------------------------------------------------------------------------------------------ grid
def test_cells_are_the_full_grid(ctx):
    ids = pd.Index(ctx.series["series_id"])
    for cmp in PLAN_CMPS:
        months, _ = common.window(ctx, cmp)
        c = cells.plan_cells(ctx, cmp, ids, months)
        assert len(c) == len(ids) * len(months)
        assert not c.duplicated(["series_id", "date"]).any()
        assert list(c.columns) == cells.PLAN_CELL_COLUMNS


def test_ac_pl_reference_counts_budgeted_cells_without_sales(ctx):
    """P = Σ budget over ids × U12M even when budgeted cells have no actuals row (left join is wrong)."""
    ltm = pd.DatetimeIndex(ctx.ltm_dates)
    plan_rows = ctx.plan[ctx.plan["date"].isin(ltm) & (ctx.plan["budget_revenue"] > 0)]
    drop_keys = set(zip(plan_rows["series_id"].head(5), plan_rows["date"].head(5), strict=True))
    act = ctx.actuals
    mask = pd.Series([(s, d) in drop_keys for s, d in zip(act["series_id"], act["date"], strict=True)], index=act.index)
    assert mask.sum() == 5
    ctx2 = dataclasses.replace(ctx, actuals=act[~mask].reset_index(drop=True))

    ids = pd.Index(ctx2.series["series_id"])
    grid = cells.plan_cells(ctx2, "ac_pl", ids, ltm)
    assert len(grid) == len(ids) * len(ltm)

    f = plan.focus(ctx2, {}, "ac_pl", "u12m", "revenue")
    steps = _steps(f)
    budget = float(
        ctx2.plan.loc[ctx2.plan["series_id"].isin(ids) & ctx2.plan["date"].isin(ltm), "budget_revenue"].sum()
    )
    actual = float(ctx2.actuals.loc[ctx2.actuals["date"].isin(ltm), "revenue"].sum())
    assert _close(steps["reference"], budget, budget)
    assert _close(steps["compared"], actual, budget)
    # A left join from the actuals would lose the 5 budgeted cells.
    left = ctx2.actuals[ctx2.actuals["date"].isin(ltm)].merge(ctx2.plan, on=["series_id", "date"], how="left")
    assert float(left["budget_revenue"].sum()) < budget - 1


# ------------------------------------------------------------------------------------------ bridge
@pytest.mark.parametrize("cmp", PLAN_CMPS)
def test_pvm_identity_is_exact(ctx, cmp):
    scopes = [{}] + [{"region": [r]} for r in _regions(ctx)]
    for filters in scopes:
        for period in _periods(ctx, cmp):
            f = plan.focus(ctx, filters, cmp, period, "revenue")
            assert f["available"], (filters, period, f.get("reason"))
            s = _steps(f)
            effects = s["volume"] + s["mix"] + s["price"] + s.get("events", 0.0)
            p = s["reference"]
            v = s["compared"] - p
            if cmp == "fc_tg":
                assert _close(s["budget_subtotal"], p + s["challenge"], p)
                assert _close(effects + s["challenge"], v, p), (filters, period)
            else:
                assert _close(effects, v, p), (filters, period)
            # The bridge adds up step by step: reference + deltas = compared.
            deltas = sum(x["value"] for x in f["bridge"] if x["kind"] == "delta")
            assert _close(p + deltas, s["compared"], p)


def test_bridge_matches_cockpit(ctx):
    k = cockpit(ctx, {}, "revenue")["kpis"]
    s = _steps(plan.focus(ctx, {}, "fc_pl", "h", "revenue"))
    assert _close(s["reference"], k["budget"], k["budget"])
    assert _close(s["compared"], k["consensus"], k["budget"])
    summary = service.summary(ctx, {}, "fc_pl", None, "revenue", None)
    assert _close(summary["kpis"][0]["value"], k["gap_vs_budget"], k["budget"])


def test_fc_tg_bridge_steps(ctx):
    f = plan.focus(ctx, {}, "fc_tg", "h", "revenue")
    keys = [s["key"] for s in f["bridge"]]
    assert keys == ["reference", "challenge", "budget_subtotal", "volume", "mix", "price", "events", "compared"]
    s = _steps(f)
    h = pd.DatetimeIndex(ctx.future_dates)
    p = ctx.plan[ctx.plan["date"].isin(h)]
    target, budget = float(p["target_revenue"].sum()), float(p["budget_revenue"].sum())
    assert _close(s["reference"], target, target)
    assert _close(s["challenge"], -(target - budget), target)
    assert _close(s["budget_subtotal"], budget, target)
    assert f["bridge"][0]["notation"] == "TG" and f["bridge"][2]["kind"] == "subtotal"


def test_units_measure_has_no_price_or_mix(ctx):
    for cmp in PLAN_CMPS:
        f = plan.focus(ctx, {}, cmp, None, "units")
        keys = [s["key"] for s in f["bridge"]]
        assert "mix" not in keys and "price" not in keys
        s = _steps(f)
        # Units: volume (+ events) closes the gap between the effects reference and the compared side.
        assert _close(s["volume"] + s.get("events", 0.0), s["compared"] - _ref_units(s, cmp), s["reference"])
        summ = plan.summary(ctx, {}, cmp, None, "units", "customer")
        for row in summ["breakdown"]["rows"]:
            assert row["effects"]["mix"] is None and row["effects"]["price"] is None


def _ref_units(s: dict[str, float], cmp: str) -> float:
    """The effects reference: the budget subtotal for fc_tg, the reference otherwise."""
    return s["budget_subtotal"] if cmp == "fc_tg" else s["reference"]


# ------------------------------------------------------------------------------------------ additivity
@pytest.mark.parametrize("cmp", PLAN_CMPS)
@pytest.mark.parametrize("level", ["region", "customer", "sku", "series"])
def test_breakdown_is_additive(ctx, cmp, level):
    s = plan.summary(ctx, {}, cmp, None, "revenue", level, limit=3)
    rows, others = s["breakdown"]["rows"], s["breakdown"]["others"]
    node_v = s["kpis"][0]["value"]
    total = sum(r["variance"] for r in rows) + (others["value"] if others else 0.0)
    assert _close(total, node_v, node_v)
    assert len(rows) <= 3 and s["breakdown"]["n_members"] == len(rows) + (others["n"] if others else 0)

    full = plan.summary(ctx, {}, cmp, None, "revenue", level, limit=1000)
    node = _steps(plan.focus(ctx, {}, cmp, None, "revenue"))
    for eff in ("volume", "mix", "price"):
        assert _close(sum(r["effects"][eff] for r in full["breakdown"]["rows"]), node[eff], node["reference"])
    if cmp != "ac_pl":
        assert _close(sum(r["effects"]["events"] for r in full["breakdown"]["rows"]), node["events"], node["reference"])


def test_breakdown_order_and_pareto(ctx):
    s = plan.summary(ctx, {}, "fc_pl", None, "revenue", "series", limit=1000)
    rows = s["breakdown"]["rows"]
    adverse = [r for r in rows if r["variance"] < 0]
    favorable = [r for r in rows if r["variance"] > 0]
    assert rows[: len(adverse)] == adverse
    assert [r["variance"] for r in adverse] == sorted(r["variance"] for r in adverse)
    assert [r["variance"] for r in favorable] == sorted((r["variance"] for r in favorable), reverse=True)
    if adverse:
        assert abs(sum(r["share_of_adverse"] for r in adverse) - 1) < 1e-9
        assert abs(adverse[-1]["cum_share"] - 1) < 1e-9
    conc = s["concentration"]
    if conc:
        assert 1 <= conc["n_top"] <= 3 and len(conc["members"]) == conc["n_top"]
    assert all(r["series_id"] == r["key"] and not r["drillable"] for r in rows)


def test_drill_consistency(ctx):
    for cmp in PLAN_CMPS:
        by_region = plan.summary(ctx, {}, cmp, None, "revenue", "region", limit=1000)["breakdown"]["rows"]
        for row in by_region:
            node = plan.summary(ctx, {"region": [row["key"]]}, cmp, None, "revenue", None)
            assert _close(node["kpis"][0]["value"], row["variance"], row["p"])


# ------------------------------------------------------------------------------------------ probability
def test_probability_matches_assess(ctx):
    a = assess(ctx, {}, None, "revenue")
    s = plan.summary(ctx, {}, "fc_tg", "h", "revenue", None)
    kpi = next(k for k in s["kpis"] if k["id"] == "prob_hit")
    assert abs(kpi["value"] - a["probability"]) <= 1e-9
    f = plan.focus(ctx, {}, "fc_tg", "h", "revenue")
    assert f["available"]
    pl = plan.summary(ctx, {}, "fc_pl", "h", "revenue", None)
    prob_pl = next(k for k in pl["kpis"] if k["id"] == "prob_hit")["value"]
    assert 0.0 <= prob_pl <= 1.0


# ------------------------------------------------------------------------------------------ recurrence
def test_recurrence_equals_ac_pl_variance(ctx):
    fc = plan.summary(ctx, {}, "fc_pl", None, "revenue", "customer", limit=1000)["breakdown"]["rows"]
    ac = {
        r["key"]: r
        for r in plan.summary(ctx, {}, "ac_pl", None, "revenue", "customer", limit=1000)["breakdown"]["rows"]
    }
    assert fc
    for row in fc:
        realized = ac[row["key"]]["variance_pct"]
        if realized is None:
            assert row["realized_variance_pct"] is None
        else:
            assert abs(row["realized_variance_pct"] - realized) < 1e-12
    for row in ac.values():
        assert row["realized_variance_pct"] is None  # only fc_* rows carry it


# ------------------------------------------------------------------------------------------ drivers
def test_paasche_gap_is_mix_free():
    """Two series, prices exactly at budget; the mix shifts towards the expensive series."""
    df = pd.DataFrame(
        {
            "q_stat": [100.0, 300.0, 50.0, 400.0],  # realized units: mix moves to series B
            "p_x": [10.0, 20.0, 10.0, 20.0],  # realized prices = budget prices
            "eq": [200.0, 100.0, 200.0, 100.0],  # budget units
            "er": [2000.0, 2000.0, 2000.0, 2000.0],  # budget revenue -> budget price 10 / 20
            "promotion": [0.0, 0.0, 0.0, 0.0],
        }
    )
    assert plan.paasche_gap(df) == pytest.approx(0.0, abs=1e-12)
    # A naive unit-value ratio would report a price change that is only mix.
    uv_real = (df["q_stat"] * df["p_x"]).sum() / df["q_stat"].sum()
    uv_budget = df["er"].sum() / df["eq"].sum()
    assert abs(uv_real / uv_budget - 1) > 0.1
    df2 = df.assign(p_x=df["p_x"] * 0.95)
    assert plan.paasche_gap(df2) == pytest.approx(-0.05, abs=1e-12)
    df3 = df2.assign(promotion=[1.0, 0.0, 0.0, 0.0], p_x=[5.0, 19.0, 9.5, 19.0])
    assert plan.paasche_gap(df3, regular_only=True) == pytest.approx(-0.05, abs=1e-12)


def test_volume_split_sums_to_volume(ctx):
    f = plan.focus(ctx, {}, "ac_pl", "u12m", "revenue")
    vs = f["drivers"]["volume_split"]
    s = _steps(f)
    assert vs is not None and 0 < vs["coverage"] <= 1
    assert _close(vs["anticipated"] + vs["surprise"] + vs["uncovered"], s["volume"], s["reference"])
    assert f["drivers"]["reg_price_gap"] is not None and f["drivers"]["avg_price_gap"] is not None
    assert f["drivers"]["price_promo"] is not None
    assert plan.focus(ctx, {}, "ac_pl", "u12m", "units")["drivers"]["price_promo"] is None


def test_fc_drivers_and_monthly(ctx):
    f = plan.focus(ctx, {}, "fc_pl", "t1", "revenue")
    assert f["drivers"]["plan_price_premium"] is not None
    assert len(f["monthly"]) == len(ctx.future_dates)  # the whole window, to pick a month
    q = f["quarters"]
    assert q and abs(sum(x["variance"] for x in q) - sum(m["variance"] for m in f["monthly"])) < 1e-6 * abs(
        _steps(f)["reference"]
    )
    for m in f["monthly"]:
        assert m["low"] <= m["x"] <= m["high"]
    assert f["period"]["code"] == "t1" and len(f["period"]["months"]) == 3


def test_focus_member_uses_parent_price(ctx):
    """A selected member keeps the parent's P̄: its bridge equals its ONDE row effects."""
    rows = plan.summary(ctx, {}, "fc_pl", None, "revenue", "customer", limit=1000)["breakdown"]["rows"]
    row = rows[0]
    f = plan.focus(ctx, {}, "fc_pl", None, "revenue", "customer", row["key"])
    s = _steps(f)
    assert f["focus"] == {"level": "customer", "member": row["key"], "label": row["label"]}
    for eff in ("volume", "mix", "price", "events"):
        assert _close(s[eff], row["effects"][eff], row["p"])
    assert any(a["kind"] == "ask_ai" for a in f["actions"])


def test_exceptions_rules(ctx):
    for cmp in PLAN_CMPS:
        e = plan.exceptions(ctx, {}, cmp, None, "revenue", direction="all", limit=1000)
        assert e["total"] == len(e["rows"])
        p = abs(_steps(plan.focus(ctx, {}, cmp, None, "revenue"))["reference"])
        for r in e["rows"]:
            assert abs(r["variance"]) >= max(10_000.0, plan.SERIES_SHARE_OF_P * p) - 1e-6
            assert r["tags"] and r["tags"][0]["code"] != "incerteza"
            assert r["impact"] >= 0 and r["recommended_action"]["label"]
        adverse = plan.exceptions(ctx, {}, cmp, None, "revenue", direction="adverse", limit=1000)
        assert all(r["variance"] < 0 for r in adverse["rows"])
        page = plan.exceptions(ctx, {}, cmp, None, "revenue", direction="all", limit=2, offset=1)
        assert page["total"] == e["total"] and page["rows"] == e["rows"][1:3]


# ------------------------------------------------------------------------------------------ actions
def test_exception_rows_and_drawer_carry_the_full_menu(ctx):
    """Same menus as the forecast lens: row "Ações" and the drawer's action bar (§2.3.4, §2.3.6)."""
    e = plan.exceptions(ctx, {}, "fc_pl", None, "revenue", direction="all", limit=3)
    for r in e["rows"]:
        assert {"open_series", "create_override", "simulate", "ask_ai"} <= {a["kind"] for a in r["actions"]}
    sid = e["rows"][0]["series_id"] if e["rows"] else str(ctx.series["series_id"].iloc[0])
    kinds = [a["kind"] for a in plan.series(ctx, sid, "fc_pl", None, "revenue")["actions"]]
    assert {"open_workspace", "create_override", "simulate", "ask_ai"} <= set(kinds)
    assert "open_series" not in kinds


def test_target_challenge_simulation_carries_the_distribution_lever(ctx):
    """'desafio_comercial' -> simulate {distribution_change_pct} from the feasibility levers (§4.4)."""
    a = assess(ctx, {}, None, "revenue")
    dist = next((lv["required_change"] for lv in a.get("levers", []) if lv["lever"] == "Distribution"), None)
    f = plan.focus(ctx, {}, "fc_tg", "h", "revenue")
    steps = _steps(f)
    sc = plan._scope(ctx, {}, "fc_tg", common.parse_period(ctx, "fc_tg", "h"), "revenue")
    got = plan._distribution_lever(sc, sc.ids, {"x": steps["compared"], "p": steps["reference"]})
    if dist is None:
        assert got is None
    else:
        assert got == pytest.approx(round(dist, 4))
    if f["tags"] and f["tags"][0]["code"] == "desafio_comercial" and got is not None:
        sim = next(x for x in f["actions"] if x["kind"] == "simulate")
        assert sim["prefill"]["distribution_change_pct"] == got


# ------------------------------------------------------------------------------------------ cache
def test_cache_belongs_to_its_context(ctx, monkeypatch):
    """A context rebuilt at the old one's address (id reuse after an override save) gets fresh values."""
    monkeypatch.setattr(common, "id", lambda _obj: 42, raising=False)  # every context at one address
    common.clear_cache()
    try:
        assert common.cached(ctx, "probe", build=lambda: "antes") == "antes"
        assert common.cached(ctx, "probe", build=lambda: "outro") == "antes"
        rebuilt = dataclasses.replace(ctx)
        assert common.cached(rebuilt, "probe", build=lambda: "depois") == "depois"
    finally:
        common.clear_cache()
