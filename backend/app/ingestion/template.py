"""Downloadable Excel upload template."""

from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from app.exports.excel_style import SUB_FONT, TITLE_FONT, signature_rows, style_table

from .schema import DESCRIPTIONS, DISPLAY, OPTIONAL, REQUIRED

EXAMPLE = [
    [
        "2024-01-01",
        "Southeast",
        "Modern Trade",
        "Customer A",
        "SKU-001",
        1250,
        "Customer A - DC 01",
        250000,
        "Product 001 500ml",
        "Beverages",
        "Brand X",
        3112.5,
        2.49,
        0,
        78.5,
        0,
        1,
        450.0,
        0,
    ],
    [
        "2024-02-01",
        "Southeast",
        "Modern Trade",
        "Customer A",
        "SKU-001",
        1410,
        "Customer A - DC 01",
        250000,
        "Product 001 500ml",
        "Beverages",
        "Brand X",
        3299.4,
        2.34,
        1,
        79.0,
        0,
        2,
        900.0,
        1,
    ],
    [
        "2024-03-01",
        "Southeast",
        "Modern Trade",
        "Customer A",
        "SKU-001",
        1180,
        "Customer A - DC 01",
        250000,
        "Product 001 500ml",
        "Beverages",
        "Brand X",
        2938.2,
        2.49,
        0,
        79.2,
        1,
        1,
        450.0,
        0,
    ],
    [
        "2024-01-01",
        "South",
        "E-commerce",
        "Customer B",
        "SKU-002",
        320,
        "Customer B - Web",
        90000,
        "Product 002 1L",
        "Snacks",
        "Brand Y",
        2236.8,
        6.99,
        0,
        55.0,
        0,
        1,
        120.0,
        0,
    ],
]
PLAN_HEADERS = ["Date", "Customer", "SKU", "BudgetUnits", "TargetUnits", "BudgetRevenue", "TargetRevenue"]


def build_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    cols = REQUIRED + OPTIONAL
    ws.append([DISPLAY[c] for c in cols])
    for row in EXAMPLE:
        ws.append(row)
    style_table(ws, {"Units": "units", "Revenue": "currency2", "Price": "currency2"})

    info = wb.create_sheet("Instructions")
    info["A1"] = "ForecastLab - Upload Template"
    info["A1"].font = TITLE_FONT
    info["A2"] = "One row per Customer x SKU x Month. Daily/weekly rows are aggregated to monthly automatically."
    info["A2"].font = SUB_FONT
    info["A3"] = "Accepted files: .xlsx, .csv, .parquet. Column names are matched case-insensitively (EN/PT aliases)."
    info["A3"].font = SUB_FONT
    info.append([])
    info.append(["Column", "Required", "Description"])
    header_row = info.max_row
    for c in cols:
        info.append([DISPLAY[c], "Yes" if c in REQUIRED else "Optional", DESCRIPTIONS[c]])
    for cell in info[header_row]:
        cell.font = Font(bold=True)
    info.column_dimensions["A"].width = 24
    info.column_dimensions["B"].width = 12
    info.column_dimensions["C"].width = 100
    for row in info.iter_rows(min_row=header_row + 1):
        row[2].alignment = Alignment(wrap_text=True)
    signature_rows(info, info.max_row + 3)

    plan = wb.create_sheet("Plan (optional)")
    plan.append(PLAN_HEADERS)
    plan.append(["2025-01-01", "Customer A", "SKU-001", 1300, 1400, 3237.0, 3486.0])
    style_table(
        plan, {"BudgetUnits": "units", "TargetUnits": "units", "BudgetRevenue": "currency", "TargetRevenue": "currency"}
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
