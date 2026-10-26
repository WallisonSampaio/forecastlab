"""File readers for .xlsx / .csv / .parquet uploads."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from .schema import is_plan_sheet, normalize_key

SUPPORTED = (".xlsx", ".xls", ".csv", ".parquet")
# Preferred data-sheet names (compared after normalize_key: case-, accent- and space-insensitive).
DATA_SHEETS = ("dados", "data", "sales", "vendas", "historico", "historicodevendas")


class UnsupportedFileError(ValueError):
    pass


XLS_UNAVAILABLE = (
    "Não foi possível ler este arquivo .xls (Excel 97-2003) neste ambiente. Salve a planilha como .xlsx e envie "
    "novamente."
)


def unsupported_message(ext: str | None = None) -> str:
    kind = f" ({ext})" if ext else ""
    return f"Tipo de arquivo não suportado{kind}. Use um destes formatos: {', '.join(SUPPORTED)}"


def _data_sheet(sheet_names: list[str]) -> str:
    """The "Dados" sheet (or "Data", "Vendas"…); otherwise the first sheet that is not a plan or instructions sheet."""
    named = next((s for s in sheet_names if normalize_key(s) in DATA_SHEETS), None)
    if named is not None:
        return named
    other = (s for s in sheet_names if not is_plan_sheet(s) and not normalize_key(s).startswith("instruc"))
    return next(other, sheet_names[0])


def read_table(content: bytes, file_name: str) -> pd.DataFrame:
    ext = Path(file_name).suffix.lower()
    buf = io.BytesIO(content)
    if ext in (".xlsx", ".xls"):
        try:
            xl = pd.ExcelFile(buf)
        except ImportError as exc:  # a real Excel 97-2003 file needs the optional "xlrd" package
            raise UnsupportedFileError(XLS_UNAVAILABLE) from exc
        return pd.read_excel(xl, sheet_name=_data_sheet(xl.sheet_names))
    if ext == ".csv":
        text = content.decode("utf-8-sig", errors="replace")
        sample = text[:4096]
        sep = ";" if sample.count(";") > sample.count(",") else ","
        decimal = "," if sep == ";" else "."
        return pd.read_csv(io.StringIO(text), sep=sep, decimal=decimal)
    if ext == ".parquet":
        return pd.read_parquet(buf)
    raise UnsupportedFileError(unsupported_message(ext))
