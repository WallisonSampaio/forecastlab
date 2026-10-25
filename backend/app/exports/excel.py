"""Excel exports: full planning workbook and executive summary."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows

from app.alerts.engine import build_alerts
from app.config import APP_NAME, APP_TAGLINE, APP_VERSION
from app.fva.fva import fva_report
from app.scenarios.engine import ScenarioParams, simulate_rows
from app.scenarios.store import compare, get_scenario
from app.services.context import PlanningContext, filter_ids
from app.services.forecast_views import leaderboard, performance_table
from app.sop.cockpit import cockpit
from app.sop.feasibility import feasibility_by

from .excel_style import NAVY, SUB_FONT, TITLE_FONT, signature_rows, style_table

DISCLAIMER = (
    "All data in the demo dataset is synthetic and fictitious. Forecasts are statistical estimates; "
    "validate them in the S&OP process before committing supply or financial plans."
)


def _sheet(wb: Workbook, title: str, df: pd.DataFrame, formats: dict[str, str] | None = None) -> None:
    ws = wb.create_sheet(title[:31])
    if df.empty:
        ws["A1"] = "No data for this selection."
        return
    for row in dataframe_to_rows(df, index=False, header=True):
        ws.append(row)
    style_table(ws, formats)


def _cover(wb: Workbook, ctx: PlanningContext, subtitle: str, filters: dict[str, Any] | None) -> None:
    ws = wb.active
    ws.title = "Cover"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 70
    ws["A1"] = APP_NAME
    ws["A1"].font = TITLE_FONT
    ws["A2"] = APP_TAGLINE
    ws["A2"].font = SUB_FONT
    ws["A4"] = subtitle
    ws["A4"].font = Font(bold=True, size=14, color=NAVY)
    rows = [
        ("Generated at", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Dataset version", ctx.version),
        ("Forecast run", ctx.run_id or "-"),
        ("Last actual month", ctx.last_actual.strftime("%Y-%m")),
        ("Forecast horizon", f"{len(ctx.future_dates)} months"),
        ("Filters", ", ".join(f"{k}={v}" for k, v in (filters or {}).items() if v) or "All"),
        ("Application version", APP_VERSION),
    ]
    for i, (k, v) in enumerate(rows, start=6):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True, color="334155")
        ws.cell(row=i, column=2, value=v)
    r = signature_rows(ws, len(rows) + 8)
    ws.cell(row=r + 1, column=1, value=DISCLAIMER).alignment = Alignment(wrap_text=True)
    ws.merge_cells(start_row=r + 1, start_column=1, end_row=r + 1, end_column=2)
    ws.row_dimensions[r + 1].height = 45
    for row in ws.iter_rows(min_row=1, max_row=3):
        for c in row:
            c.fill = PatternFill(None)


def forecast_detail(
    ctx: PlanningContext, filters: dict[str, Any] | None, scenario_id: str | None = None, history_months: int = 12
) -> pd.DataFrame:
    ids = filter_ids(ctx, filters)
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    attrs = s[
        [
            "series_id",
            "region",
            "channel",
            "customer",
            "sku",
            "product",
            "category",
            "brand",
            "series_type",
            "champion",
            "challenger",
            "wmape",
            "bias",
            "confidence",
        ]
    ]
    f = ctx.forecast[ctx.forecast["series_id"].isin(ids)].copy()
    f["Type"] = "Forecast"
    if scenario_id:
        sc = get_scenario(scenario_id)
        rows = simulate_rows(ctx, ScenarioParams.from_dict(sc["params"]))
        f = f.merge(
            rows[["series_id", "date", "scenario_units", "scenario_revenue"]], on=["series_id", "date"], how="left"
        )
    hist_start = ctx.last_actual - pd.DateOffset(months=history_months - 1)
    a = ctx.actuals[ctx.actuals["series_id"].isin(ids) & (ctx.actuals["date"] >= hist_start)][
        ["series_id", "date", "units", "revenue"]
    ].assign(Type="Actual")
    df = pd.concat([a, f], ignore_index=True)
    if not ctx.plan.empty:
        df = df.merge(ctx.plan, on=["series_id", "date"], how="left")
    df = df.merge(attrs, on="series_id", how="left")
    out = pd.DataFrame(
        {
            "Date": df["date"].dt.strftime("%Y-%m"),
            "Type": df["Type"],
            "Region": df["region"],
            "Channel": df["channel"],
            "Customer": df["customer"],
            "SKU": df["sku"],
            "Product": df["product"],
            "Category": df["category"],
            "Brand": df["brand"],
            "Actual Units": df.get("units"),
            "Actual Revenue": df.get("revenue"),
            "Statistical Forecast": df.get("p50"),
            "Incremental (events)": df.get("incremental"),
            "Consensus Forecast": df.get("consensus"),
            "Consensus Revenue": df.get("consensus") * df.get("price") if "price" in df else None,
            "P10": df.get("p10"),
            "P50": df.get("p50"),
            "P90": df.get("p90"),
            "Budget Units": df.get("budget_units"),
            "Target Units": df.get("target_units"),
            "Budget Revenue": df.get("budget_revenue"),
            "Target Revenue": df.get("target_revenue"),
        }
    )
    if scenario_id:
        out["Scenario Units"] = df.get("scenario_units")
        out["Scenario Revenue"] = df.get("scenario_revenue")
    out["Series Type"] = df["series_type"]
    out["Champion Model"] = df["champion"]
    out["Challenger Model"] = df["challenger"]
    out["WMAPE"] = df["wmape"]
    out["Bias"] = df["bias"]
    out["Confidence"] = df["confidence"]
    return out.sort_values(["Customer", "SKU", "Date"]).reset_index(drop=True)


DETAIL_FORMATS = {
    "Actual Units": "units",
    "Actual Revenue": "currency",
    "Statistical Forecast": "units",
    "Incremental (events)": "units",
    "Consensus Forecast": "units",
    "Consensus Revenue": "currency",
    "P10": "units",
    "P50": "units",
    "P90": "units",
    "Budget Units": "units",
    "Target Units": "units",
    "Budget Revenue": "currency",
    "Target Revenue": "currency",
    "Scenario Units": "units",
    "Scenario Revenue": "currency",
    "WMAPE": "percent",
    "Bias": "percent",
}


def _kv_frame(d: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame([{"KPI": k, "Value": v} for k, v in d.items()])


def build_workbook(
    ctx: PlanningContext, filters: dict[str, Any] | None = None, scenario_id: str | None = None
) -> bytes:
    wb = Workbook()
    _cover(wb, ctx, "Demand Plan & S&OP Export", filters)
    ck = cockpit(ctx, filters, "revenue")
    k = ck.get("kpis", {})
    summary = _kv_frame(
        {
            "Actual LTM (R$)": k.get("actual_ltm"),
            "Statistical Forecast 12M (R$)": k.get("statistical"),
            "Consensus Forecast 12M (R$)": k.get("consensus"),
            "Budget 12M (R$)": k.get("budget"),
            "Target 12M (R$)": k.get("target"),
            "Gap vs Budget (R$)": k.get("gap_vs_budget"),
            "Gap vs Budget (%)": k.get("gap_vs_budget_pct"),
            "Gap vs Target (R$)": k.get("gap_vs_target"),
            "Revenue at Risk (R$)": k.get("risk"),
            "Opportunity (R$)": k.get("opportunity"),
            "Forecast Accuracy": k.get("accuracy"),
            "WMAPE": k.get("wmape"),
            "Bias": k.get("bias"),
            "Target Feasibility": (ck.get("feasibility") or {}).get("classification"),
            "Probability of hitting target": (ck.get("feasibility") or {}).get("probability"),
        }
    )
    ws = wb.create_sheet("Executive Summary")
    for row in dataframe_to_rows(summary, index=False, header=True):
        ws.append(row)
    style_table(ws, widths={"KPI": 36, "Value": 22})
    for r in ws.iter_rows(min_row=2, min_col=2, max_col=2):
        for c in r:
            label = ws.cell(row=c.row, column=1).value or ""
            c.number_format = (
                '"R$" #,##0'
                if "R$" in label
                else "0.0%"
                if any(x in label for x in ("%", "Accuracy", "WMAPE", "Bias", "Probability"))
                else "General"
            )

    _sheet(wb, "Forecast Detail", forecast_detail(ctx, filters, scenario_id), DETAIL_FORMATS)
    lb = pd.DataFrame(leaderboard(ctx, filters))
    if not lb.empty:
        lb = lb[
            [
                "rank",
                "model",
                "family",
                "wmape",
                "accuracy",
                "bias",
                "rmse",
                "series_evaluated",
                "champion_count",
                "challenger_count",
                "win_rate",
            ]
        ]
    _sheet(
        wb,
        "Model Leaderboard",
        lb,
        {"wmape": "percent", "accuracy": "percent", "bias": "percent", "rmse": "number", "win_rate": "percent"},
    )
    _sheet(
        wb,
        "Series Performance",
        pd.DataFrame(performance_table(ctx, filters)),
        {
            "wmape": "percent",
            "accuracy": "percent",
            "bias": "percent",
            "challenger_wmape": "percent",
            "gap_vs_challenger": "percent",
            "wmape_std": "percent",
        },
    )
    cmp = compare(ctx, None, filters, "revenue")
    _sheet(
        wb,
        "Scenarios",
        pd.DataFrame(cmp["rows"]),
        {
            "units": "units",
            "revenue": "currency",
            "vs_base_units": "percent",
            "vs_base_revenue": "percent",
            "vs_budget_units": "percent",
            "vs_budget_revenue": "percent",
            "vs_target_units": "percent",
            "vs_target_revenue": "percent",
            "budget_units": "units",
            "budget_revenue": "currency",
            "target_units": "units",
            "target_revenue": "currency",
        },
    )
    feas = pd.DataFrame(feasibility_by(ctx, "region", filters) + feasibility_by(ctx, "channel", filters))
    _sheet(
        wb,
        "Target Feasibility",
        feas,
        {
            "target": "currency",
            "budget": "currency",
            "consensus": "currency",
            "p10": "currency",
            "p90": "currency",
            "probability": "percent",
            "gap_vs_target": "currency",
            "gap_vs_target_pct": "percent",
            "required_growth": "percent",
        },
    )
    fva = fva_report(ctx, filters)
    _sheet(
        wb,
        "FVA",
        pd.DataFrame(fva.get("overrides", [])),
        {
            "adjustment_pct": "percent",
            "statistical": "units",
            "consensus": "units",
            "actual": "units",
            "error_statistical": "units",
            "error_consensus": "units",
            "fva_units": "units",
        },
    )
    alerts = pd.DataFrame(
        [
            {
                **{
                    k2: a[k2]
                    for k2 in (
                        "severity",
                        "title",
                        "issue",
                        "magnitude",
                        "potential_impact",
                        "explanation",
                        "recommendation",
                    )
                },
                "customer": a["entity"].get("customer"),
                "sku": a["entity"].get("sku"),
            }
            for a in build_alerts(ctx)
        ]
    )
    _sheet(wb, "Alerts", alerts, {"potential_impact": "currency"})
    _sheet(
        wb,
        "Commercial Overrides",
        ctx.overrides.drop(columns=["dataset_version"], errors="ignore"),
        {"uplift_pct": "percent"},
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_executive_workbook(ctx: PlanningContext, filters: dict[str, Any] | None = None) -> bytes:
    wb = Workbook()
    _cover(wb, ctx, "Executive S&OP Summary", filters)
    ck = cockpit(ctx, filters, "revenue")
    _sheet(wb, "KPIs", _kv_frame(ck.get("kpis", {})))
    _sheet(
        wb,
        "Quarters",
        pd.DataFrame(ck.get("quarters", [])),
        {
            "base": "currency",
            "consensus": "currency",
            "budget": "currency",
            "target": "currency",
            "gap_vs_budget": "currency",
        },
    )
    _sheet(
        wb,
        "Top Risks",
        pd.DataFrame(ck.get("risks", [])),
        {"consensus": "currency", "budget": "currency", "gap": "currency", "gap_pct": "percent"},
    )
    _sheet(
        wb,
        "Top Opportunities",
        pd.DataFrame(ck.get("opportunities", [])),
        {"consensus": "currency", "budget": "currency", "gap": "currency", "gap_pct": "percent"},
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
