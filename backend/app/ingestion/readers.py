"""File readers for .xlsx / .csv / .parquet uploads."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

SUPPORTED = (".xlsx", ".xls", ".csv", ".parquet")


class UnsupportedFileError(ValueError):
    pass


def read_table(content: bytes, file_name: str) -> pd.DataFrame:
    ext = Path(file_name).suffix.lower()
    buf = io.BytesIO(content)
    if ext in (".xlsx", ".xls"):
        xl = pd.ExcelFile(buf)
        # Prefer a sheet called "Data"; otherwise the first sheet.
        sheet = next((s for s in xl.sheet_names if s.strip().lower() in ("data", "dados", "sales")), xl.sheet_names[0])
        return xl.parse(sheet)
    if ext == ".csv":
        text = content.decode("utf-8-sig", errors="replace")
        sample = text[:4096]
        sep = ";" if sample.count(";") > sample.count(",") else ","
        decimal = "," if sep == ";" else "."
        return pd.read_csv(io.StringIO(text), sep=sep, decimal=decimal)
    if ext == ".parquet":
        return pd.read_parquet(buf)
    raise UnsupportedFileError(f"Unsupported file type '{ext}'. Use one of: {', '.join(SUPPORTED)}")
