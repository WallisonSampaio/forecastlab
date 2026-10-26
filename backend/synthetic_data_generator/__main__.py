"""CLI: python -m synthetic_data_generator --seed 42 --out ../data/synthetic"""

from __future__ import annotations

import argparse
import io
import json
import re
import zipfile
from pathlib import Path

from .catalog import CENTRO_OESTE, SUL
from .generator import generate_dataset

# Regiões usadas no arquivo de amostra para upload (subconjunto menor da base completa).
SAMPLE_REGIONS = [SUL, CENTRO_OESTE]
# Nome da aba do .xlsx de amostra ("Dados" é uma das abas que a tela de upload procura primeiro).
SAMPLE_SHEET = "Dados"


def _n(value: int) -> str:
    """Inteiro com separador de milhar em pt-BR (12.345)."""
    return f"{value:,}".replace(",", ".")


def _normalize_xlsx(path: Path, stamp: str) -> None:
    """Fixa os carimbos de data do .xlsx (zip + docProps) para que a mesma seed gere o mesmo arquivo byte a byte."""
    with zipfile.ZipFile(path) as src:
        entries = [(info, src.read(info.filename)) for info in src.infolist()]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info, data in entries:
            if info.filename == "docProps/core.xml":
                data = re.sub(
                    rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*(<)", rb"\g<1>" + stamp.encode() + rb"\g<2>", data
                )
            fixed = zipfile.ZipInfo(info.filename, date_time=(2000, 1, 1, 0, 0, 0))
            fixed.compress_type = zipfile.ZIP_DEFLATED
            fixed.external_attr = info.external_attr
            dst.writestr(fixed, data)
    path.write_bytes(buf.getvalue())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera a base sintética de demonstração do ForecastLab.", add_help=False
    )
    parser.add_argument("-h", "--help", action="help", help="mostra esta ajuda e sai")
    parser.add_argument("--seed", type=int, default=42, help="random_seed (mesma seed -> mesmos dados)")
    parser.add_argument("--end-month", default="2026-09", help="último mês do histórico (AAAA-MM)")
    parser.add_argument("--months", type=int, default=60, help="quantidade de meses de histórico")
    parser.add_argument("--out", default="../data/synthetic", help="pasta de saída")
    parser.add_argument("--samples", default="../data/samples", help="pasta das amostras pequenas para upload")
    args = parser.parse_args()

    ds = generate_dataset(random_seed=args.seed, end_month=args.end_month, n_months=args.months)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # Quebras de linha LF fixas: o mesmo arquivo byte a byte em qualquer sistema operacional.
    csv = {"index": False, "date_format": "%Y-%m-%d", "lineterminator": "\n"}
    ds.sales.to_csv(out / "sales_history.csv", **csv)
    ds.sales.to_parquet(out / "sales_history.parquet", index=False)
    ds.plan.to_csv(out / "budget_target_plan.csv", **csv)
    ds.historical_overrides.to_csv(out / "historical_overrides.csv", **csv)
    ds.future_overrides.to_csv(out / "pending_commercial_events.csv", **csv)
    (out / "metadata.json").write_text(
        json.dumps(ds.metadata, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )

    samples = Path(args.samples)
    samples.mkdir(parents=True, exist_ok=True)
    subset = ds.sales[ds.sales["Region"].isin(SAMPLE_REGIONS)]
    subset.to_excel(samples / "forecastlab_sample_upload.xlsx", index=False, sheet_name=SAMPLE_SHEET)
    _normalize_xlsx(samples / "forecastlab_sample_upload.xlsx", f"{ds.metadata['end']}T00:00:00Z")
    subset.to_csv(samples / "forecastlab_sample_upload.csv", **csv)

    print(
        f"Geradas {_n(len(ds.sales))} linhas / {_n(ds.metadata['n_series'])} séries "
        f"({ds.metadata['start']} -> {ds.metadata['end']}) com seed={args.seed}"
    )
    print(
        f"Linhas do plano: {_n(len(ds.plan))} | ajustes comerciais históricos: "
        f"{_n(len(ds.historical_overrides))} | eventos pendentes: {_n(len(ds.future_overrides))}"
    )
    print(f"Amostra para upload ({', '.join(SAMPLE_REGIONS)}): {_n(len(subset))} linhas")


if __name__ == "__main__":
    main()
