"""CLI: python -m synthetic_data_generator --seed 42 --out ../data/synthetic"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .generator import generate_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the ForecastLab synthetic demo dataset.")
    parser.add_argument("--seed", type=int, default=42, help="random_seed (same seed -> same data)")
    parser.add_argument("--end-month", default="2026-09", help="last history month (YYYY-MM)")
    parser.add_argument("--months", type=int, default=60, help="months of history")
    parser.add_argument("--out", default="../data/synthetic", help="output folder")
    parser.add_argument("--samples", default="../data/samples", help="folder for small upload samples")
    args = parser.parse_args()

    ds = generate_dataset(random_seed=args.seed, end_month=args.end_month, n_months=args.months)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ds.sales.to_csv(out / "sales_history.csv", index=False, date_format="%Y-%m-%d")
    ds.sales.to_parquet(out / "sales_history.parquet", index=False)
    ds.plan.to_csv(out / "budget_target_plan.csv", index=False, date_format="%Y-%m-%d")
    ds.historical_overrides.to_csv(out / "historical_overrides.csv", index=False, date_format="%Y-%m-%d")
    ds.future_overrides.to_csv(out / "pending_commercial_events.csv", index=False, date_format="%Y-%m-%d")
    (out / "metadata.json").write_text(json.dumps(ds.metadata, indent=2, default=str), encoding="utf-8")

    samples = Path(args.samples)
    samples.mkdir(parents=True, exist_ok=True)
    subset = ds.sales[ds.sales["Region"].isin(["South", "Midwest"])]
    subset.to_excel(samples / "forecastlab_sample_upload.xlsx", index=False)
    subset.to_csv(samples / "forecastlab_sample_upload.csv", index=False, date_format="%Y-%m-%d")

    print(
        f"Generated {len(ds.sales):,} rows / {ds.metadata['n_series']} series "
        f"({ds.metadata['start']} -> {ds.metadata['end']}) with seed={args.seed}"
    )
    print(f"Plan rows: {len(ds.plan):,} | historical overrides: {len(ds.historical_overrides):,}")


if __name__ == "__main__":
    main()
