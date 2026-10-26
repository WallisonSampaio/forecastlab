"""Journey state and forecast trust (spec §1.5, §4.3.1, §4.3.2, §4.6).

* ``journey_status`` – single source of the journey stage (dados | modelos | pronto) and run state.
* ``trust`` – "can I take this number to the meeting?": out-of-sample accuracy, bias, gain over the
  naive method, wins per model (WMAPE is not comparable across models, because the router sends each
  model only to some demand patterns), confidence split, backtest by month, caution list and verdict.
* ``scope_quality`` – the same quality numbers for any set of series (used by the report).

Accuracy is measured in UNITS on the champion backtest cells (``context.backtest_metrics``); revenue
amounts use the realized cell price (backtest) or the series price (horizon).
"""

from __future__ import annotations

import copy
import json
import math
import re
from datetime import date, datetime
from typing import Any

import pandas as pd

from app import db
from app.deviations import common, forecast_error
from app.fva.fva import fva_report
from app.metrics import bias_class
from app.services import datasets, ptbr, runs
from app.services.context import PlanningContext, backtest_metrics, resolve_run
from app.validation.health import score_label

NO_RUN = "Ainda não há uma execução de forecast concluída."
NO_BACKTEST = "Esta execução não tem resultados de backtest para medir o erro fora da amostra."
NAIVE_MODEL = "Naive"
CONFIDENCE_LEVELS = ("High", "Medium", "Low")
CAUTION_WMAPE = 0.35  # caution list: confidence Low or series WMAPE ≥ 35% ...
MAX_CAUTION = 5  # ... top 5 by consensus revenue over the horizon
_FALLBACK_RE = re.compile(r"(\d+) série\(s\) usaram")

# Plural adjective of each demand pattern inside "Nas 66 séries sazonais, …".
SERIES_TYPE_PLURAL = {
    "Stable": "estáveis",
    "Trending": "crescentes",
    "Declining": "em declínio",
    "Seasonal": "sazonais",
    "Intermittent": "intermitentes",
    "Promo Driven": "dirigidas por promoção",
    "Distribution Driven": "dirigidas por distribuição",
    "Structural Change": "com mudança estrutural",
    "Volatile": "voláteis",
    "Short History": "de histórico curto",
    "Inactive": "inativas",
}

# Verdict thresholds (spec §4.3.2), unit-tested at the boundaries.
VERDICT_RULES = {
    "confiavel": {"min_accuracy": 0.80, "max_abs_bias": 0.05, "max_low_share": 0.20, "min_gain_pp": 0.0},
    "cautela": {"min_accuracy": 0.65, "max_abs_bias": 0.10, "min_gain_pp": 0.0},
}
VERDICT_LABEL = {
    "confiavel": "Confiável para decisão",
    "cautela": "Use com cautela — trate o número como faixa P10–P90",
    "nao_confiavel": "Não confiável — revise a base antes de decidir",
}
# Short form for compact places (the report's accuracy KPI delta).
VERDICT_SHORT = {"confiavel": "Confiável para decisão", "cautela": "Use com cautela", "nao_confiavel": "Não confiável"}


# ------------------------------------------------------------------------------------------ journey
def _iso(v: Any) -> str | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, datetime | pd.Timestamp):
        return pd.Timestamp(v).isoformat(timespec="seconds")
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _day(v: Any) -> str | None:
    """Date as 'YYYY-MM-DD' (same format as ``context.clean``)."""
    if v is None:
        return None
    ts = pd.Timestamp(v)
    return None if pd.isna(ts) else ts.strftime("%Y-%m-%d")


def _float(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _n_months(start: Any, end: Any) -> int:
    if start is None or end is None:
        return 0
    a, b = pd.Timestamp(start), pd.Timestamp(end)
    if pd.isna(a) or pd.isna(b):
        return 0
    return (b.year - a.year) * 12 + b.month - a.month + 1


def _run_row(run_id: str | None) -> dict[str, Any] | None:
    if not run_id:
        return None
    df = db.query_df(
        "SELECT run_id, status, finished_at, duration_s, message FROM forecast_runs WHERE run_id = ?", [run_id]
    )
    return None if df.empty else df.iloc[0].to_dict()


def _message(msg: Any) -> str | None:
    """First line of a stored run message (failed runs keep the traceback after it), localised."""
    if not isinstance(msg, str) or not msg.strip():
        return None
    return runs._localize_message(msg.strip().splitlines()[0])


def _dataset_block(version: str, ds: dict[str, Any]) -> dict[str, Any]:
    issues = (ds.get("validation") or {}).get("issues") or []
    score = _float(ds.get("quality_score"))
    plan_source = ds.get("plan_source")
    return {
        "version": version,
        "name": ds.get("name"),
        "status": ds.get("status"),
        "quality_score": score,
        "quality_label": score_label(score) if score is not None else None,
        "n_series": int(ds.get("n_series") or 0),
        "n_customers": int(ds.get("n_customers") or 0),
        "n_skus": int(ds.get("n_skus") or 0),
        "start_date": _day(ds.get("start_date")),
        "end_date": _day(ds.get("end_date")),
        "n_months": _n_months(ds.get("start_date"), ds.get("end_date")),
        "plan_source": plan_source,
        "plan_derived": plan_source == datasets.DERIVED_PLAN_SOURCE,
        "has_plan": bool(db.scalar("SELECT COUNT(*) FROM plan WHERE dataset_version = ?", [version])),
        "n_critical": sum(1 for i in issues if isinstance(i, dict) and i.get("severity") == "critical"),
        "n_warnings": sum(1 for i in issues if isinstance(i, dict) and i.get("severity") == "warning"),
        "has_overrides_history": bool(
            db.scalar("SELECT COUNT(*) FROM historical_overrides WHERE dataset_version = ?", [version])
        ),
    }


def _empty_run() -> dict[str, Any]:
    return {
        "state": "none",
        "run_id": None,
        "progress": None,
        "step": None,
        "done": None,
        "total": None,
        "message": None,
        "finished_at": None,
        "duration_s": None,
        "rerunning": False,
    }


def _run_block(version: str) -> tuple[dict[str, Any], str | None]:
    active_run = resolve_run(version)
    job = runs.current_job()
    if job and job.get("dataset_version") != version:
        job = None
    run = _empty_run()
    row = _run_row(active_run)
    if job:
        run.update(
            state="running",
            progress=_float(job.get("progress")),
            step=job.get("step"),
            done=job.get("done"),
            total=job.get("total"),
            run_id=job.get("run_id"),
        )
    elif active_run:
        run["state"] = "completed"
    else:
        latest = db.scalar(
            "SELECT run_id FROM forecast_runs WHERE dataset_version = ? ORDER BY created_at DESC LIMIT 1", [version]
        )
        failed = _run_row(latest)
        if failed and failed.get("status") == "failed":
            run.update(state="failed", run_id=failed["run_id"], message=_message(failed.get("message")))
            run.update(finished_at=_iso(failed.get("finished_at")), duration_s=_float(failed.get("duration_s")))
    if row:  # the numbers on screen come from the active run, also while a rerun is in progress
        run.update(
            run_id=row["run_id"],
            finished_at=_iso(row.get("finished_at")),
            duration_s=_float(row.get("duration_s")),
            message=_message(row.get("message")),
        )
    run["rerunning"] = bool(job and active_run)
    return run, active_run


def journey_status() -> dict[str, Any]:
    """Single source of the journey state: stage dados | modelos | pronto (always HTTP 200)."""
    version = datasets.active_version()
    ds = datasets.get_dataset(version) if version else None
    if not version or ds is None:
        return {"stage": "dados", "dataset": None, "run": _empty_run()}
    run, active_run = _run_block(version)
    return {
        "stage": "pronto" if active_run else "modelos",
        "dataset": _dataset_block(version, ds),
        "run": run,
    }


# ------------------------------------------------------------------------------------------ trust
def verdict_code(accuracy: float, bias: float, low_share: float, gain_pp: float | None) -> str:
    """confiavel | cautela | nao_confiavel (spec §4.3.2 "Verdict")."""
    gain = gain_pp if gain_pp is not None else -math.inf
    c = VERDICT_RULES["confiavel"]
    if (
        accuracy >= c["min_accuracy"]
        and abs(bias) <= c["max_abs_bias"]
        and low_share <= c["max_low_share"]
        and gain > c["min_gain_pp"]
    ):
        return "confiavel"
    k = VERDICT_RULES["cautela"]
    if accuracy >= k["min_accuracy"] and abs(bias) <= k["max_abs_bias"] and gain > k["min_gain_pp"]:
        return "cautela"
    return "nao_confiavel"


def verdict_reasons(
    accuracy: float, bias: float, low_share: float, gain_pp: float | None, naive: float | None, wmape: float | None
) -> list[str]:
    """One pt-BR sentence per condition of 'Confiável para decisão' that failed (empty when trusted)."""
    c = VERDICT_RULES["confiavel"]
    out: list[str] = []
    if accuracy < c["min_accuracy"]:
        out.append(
            f"Acurácia fora da amostra de {ptbr.pct(accuracy, 1)}, abaixo dos "
            f"{ptbr.pct(c['min_accuracy'], 0)} exigidos para decisão."
        )
    if abs(bias) > c["max_abs_bias"]:
        side = "superestima" if bias > 0 else "subestima"
        out.append(f"Viés de {ptbr.pct(bias, 1, signed=True)}: o forecast {side} a demanda.")
    if low_share > c["max_low_share"]:
        out.append(f"A receita em séries de confiança baixa é de {ptbr.pct(low_share, 0)}.")
    if gain_pp is None or gain_pp <= c["min_gain_pp"]:
        if naive is not None and wmape is not None:
            out.append(
                f"O forecast não supera o método ingênuo: erra {ptbr.pct(wmape, 1)} contra {ptbr.pct(naive, 1)}."
            )
        else:
            out.append("Não foi possível comparar o forecast com o método ingênuo.")
    return out


def verdict_headline(accuracy: float, gain_pp: float | None, high_share: float, naive: float | None) -> str:
    """spec §4.6."""
    acc = ptbr.pct(accuracy, 1)
    if gain_pp is not None and gain_pp > 0:
        return (
            f"O forecast acerta {acc} fora da amostra, erra {ptbr.dec(gain_pp * 100, 1)} p.p. menos que o "
            f"método ingênuo e {ptbr.pct(high_share, 0)} da receita prevista vem de séries com confiança alta."
        )
    naive_acc = f" ({ptbr.pct(1 - naive, 1)})" if naive is not None else ""
    return (
        f"O forecast acerta {acc} fora da amostra, mas não supera o método ingênuo{naive_acc} — "
        "revise a base e os modelos."
    )


def verdict(q: dict[str, Any]) -> dict[str, Any]:
    """{code, label, headline, reasons} from a ``scope_quality`` result."""
    code = q["verdict_code"]
    shares = q["confidence_revenue_share"]
    return {
        "code": code,
        "label": VERDICT_LABEL[code],
        "headline": verdict_headline(q["accuracy"], q["gain_vs_naive_pp"], shares["High"], q["naive_wmape"]),
        "reasons": verdict_reasons(
            q["accuracy"], q["bias"], shares["Low"], q["gain_vs_naive_pp"], q["naive_wmape"], q["wmape"]
        ),
    }


def series_revenue(ctx: PlanningContext) -> pd.Series:
    """Consensus revenue over the horizon H per series (Σ consensus × price), company-wide, cached."""

    def build() -> pd.Series:
        f = ctx.forecast
        if f is None or f.empty:
            return pd.Series(dtype=float)
        f = f[f["date"].isin(ctx.future_dates)]
        return (f["consensus"] * f["price"]).groupby(f["series_id"]).sum().astype(float)

    return common.cached(ctx, "trust.series_revenue", build=build)


def confidence_split(ctx: PlanningContext, ids: pd.Index) -> tuple[dict[str, int], dict[str, float]]:
    """(series count, consensus-revenue share over H) by confidence level High / Medium / Low."""
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    conf = s.set_index("series_id")["confidence"]
    counts = {lv: int((conf == lv).sum()) for lv in CONFIDENCE_LEVELS}
    rev = series_revenue(ctx).reindex(conf.index).fillna(0.0)
    by = rev.groupby(conf).sum()
    total = float(sum(float(by.get(lv, 0.0)) for lv in CONFIDENCE_LEVELS))
    shares = {lv: (float(by.get(lv, 0.0)) / total if total > 0 else 0.0) for lv in CONFIDENCE_LEVELS}
    return counts, shares


def scope_quality(ctx: PlanningContext, ids: pd.Index, naive: float | None = None) -> dict[str, Any] | None:
    """Out-of-sample quality of the forecast for a set of series: accuracy / WMAPE / bias (units,
    ``backtest_metrics``), naive WMAPE, gain, confidence split and verdict code. None without backtest.

    ``naive`` defaults to ``forecast_error.naive_wmape`` (identical to ``fva_report().stairstep.naive``)."""
    m = backtest_metrics(ctx, ids)
    if m["wmape"] is None:
        return None
    if naive is None:
        naive = forecast_error.naive_wmape(ctx, pd.Index(ids))
    wmape, bias, accuracy = float(m["wmape"]), float(m["bias"] or 0.0), float(m["accuracy"] or 0.0)
    gain = (naive - wmape) if naive is not None else None
    counts, shares = confidence_split(ctx, ids)
    return {
        "accuracy": accuracy,
        "wmape": wmape,
        "bias": bias,
        "bias_class": bias_class(bias),
        "bias_label": ptbr.BIAS_CLASS[bias_class(bias)],
        "naive_wmape": naive,
        "gain_vs_naive_pp": gain,
        "error_reduction_vs_naive": (1 - wmape / naive) if naive else None,
        "confidence_series": counts,
        "confidence_revenue_share": shares,
        "verdict_code": verdict_code(accuracy, bias, shares["Low"], gain),
    }


def _naive_rows(ctx: PlanningContext) -> pd.DataFrame:
    def build() -> pd.DataFrame:
        df = db.query_df(
            "SELECT series_id, date, forecast AS naive FROM backtest_results WHERE run_id = ? AND model = ?",
            [ctx.run_id, NAIVE_MODEL],
        )
        df["date"] = pd.to_datetime(df["date"])
        return df.drop_duplicates(["series_id", "date"])

    return common.cached(ctx, "trust.naive_rows", build=build)


def _backtest_monthly(ctx: PlanningContext, ids: pd.Index, months: pd.DatetimeIndex) -> list[dict[str, Any]]:
    """Σ A·p, Σ F_stat·p and Σ F_naive·p per backtest month over the champion cells (realized cell price)."""
    cells = forecast_error.error_cells(ctx, "ac_fc", ids, months)
    if cells.empty:
        return []
    m = cells[["series_id", "date", "actual_rev", "forecast_stat", "p"]].merge(
        _naive_rows(ctx), on=["series_id", "date"], how="left"
    )
    m["statistical"] = m["forecast_stat"] * m["p"]
    m["naive_rev"] = m["naive"].fillna(m["forecast_stat"]) * m["p"]
    g = m.groupby("date")[["actual_rev", "statistical", "naive_rev"]].sum().sort_index()
    return [
        {
            "date": f"{pd.Timestamp(d):%Y-%m-%d}",
            "actual": float(r.actual_rev),
            "statistical": float(r.statistical),
            "naive": float(r.naive_rev),
        }
        for d, r in g.iterrows()
    ]


def _per_series_error(ctx: PlanningContext) -> pd.DataFrame:
    """WMAPE and bias per series over its champion backtest cells (units)."""
    bt = ctx.backtest
    if bt is None or bt.empty:
        return pd.DataFrame(columns=["wmape", "bias"])
    e = bt["forecast"] - bt["actual"]
    g = pd.DataFrame({"series_id": bt["series_id"], "abs_e": e.abs(), "e": e, "a": bt["actual"]}).groupby("series_id")
    t = g[["abs_e", "e", "a"]].sum()
    a = t["a"].where(t["a"] > 0)
    return pd.DataFrame({"wmape": t["abs_e"] / a, "bias": t["e"] / a})


def _champions(ctx: PlanningContext) -> list[dict[str, Any]]:
    from app.forecasting.models import MODEL_REGISTRY

    s = ctx.series
    champ = s.set_index("series_id")["champion"].dropna().astype(str)
    counts = champ.value_counts()
    n = int(counts.sum())
    bt = ctx.backtest
    won = pd.DataFrame(columns=["abs_e", "a"])
    if bt is not None and not bt.empty:
        e = (bt["forecast"] - bt["actual"]).abs()
        won = pd.DataFrame({"abs_e": e, "a": bt["actual"], "m": bt["series_id"].map(champ)}).groupby("m").sum()
    rows = []
    for model, k in counts.items():
        fam = getattr(MODEL_REGISTRY.get(model), "family", "") or ""
        a = float(won.at[model, "a"]) if model in won.index else 0.0
        rows.append(
            {
                "model": model,
                "label": ptbr.model(model),
                "family": fam,
                "family_label": ptbr.FAMILY.get(fam, fam),
                "series": int(k),
                "share": int(k) / n if n else 0.0,
                "wmape_won": float(won.at[model, "abs_e"]) / a if a > 0 else None,
                "is_reference": model == NAIVE_MODEL,
            }
        )
    rows.sort(key=lambda r: (-r["series"], r["model"]))
    return rows


def _patterns(ctx: PlanningContext) -> list[dict[str, Any]]:
    s = ctx.series.dropna(subset=["series_type"])
    out = []
    for code, g in s.groupby("series_type"):
        vc = g["champion"].dropna().astype(str).value_counts()
        top = sorted(vc.items(), key=lambda kv: (-kv[1], kv[0]))[0] if len(vc) else (None, 0)
        out.append(
            {
                "series_type": str(code),
                "label": ptbr.series_type(str(code)),
                "n": len(g),
                "top_model": top[0],
                "top_model_label": ptbr.model(top[0]) if top[0] else ptbr.NA,
                "top_model_series": int(top[1]),
            }
        )
    out.sort(key=lambda r: (-r["n"], r["series_type"]))
    return out


def pattern_insight(patterns: list[dict[str, Any]]) -> str:
    """'Nas 66 séries sazonais, Regressão venceu 31 — cada padrão de demanda tem seu modelo.'"""
    p = next((r for r in patterns if r["top_model"]), None)
    if p is None:
        return "Cada padrão de demanda testa apenas os modelos plausíveis para ele."
    tail = "cada padrão de demanda tem seu modelo."
    if p["n"] == 1:
        return f"Na única série {p['label'].lower()}, {p['top_model_label']} venceu — {tail}"
    adj = SERIES_TYPE_PLURAL.get(p["series_type"], p["label"].lower())
    return f"Nas {p['n']} séries {adj}, {p['top_model_label']} venceu {p['top_model_series']} — {tail}"


def _caution(ctx: PlanningContext, per_series: pd.DataFrame) -> list[dict[str, Any]]:
    s = ctx.series.set_index("series_id")
    w = per_series["wmape"].reindex(s.index)
    b = per_series["bias"].reindex(s.index)
    mask = (s["confidence"] == "Low") | (w >= CAUTION_WMAPE)
    rev = series_revenue(ctx).reindex(s.index).fillna(0.0)
    pick = rev[mask.fillna(False).astype(bool)].sort_values(ascending=False, kind="mergesort").head(MAX_CAUTION)
    out = []
    for sid, r in pick.items():
        row = s.loc[sid]
        out.append(
            {
                "series_id": str(sid),
                "customer": str(row["customer"]),
                "sku": str(row["sku"]),
                "product": str(row["product"]) if pd.notna(row["product"]) else "",
                "wmape": _float(w.get(sid)),
                "bias": _float(b.get(sid)),
                "confidence": str(row["confidence"]) if pd.notna(row["confidence"]) else None,
                "series_type_label": ptbr.series_type(row["series_type"] if pd.notna(row["series_type"]) else None),
                "revenue_12m": float(r),
            }
        )
    return out


def _avg_candidates(ctx: PlanningContext) -> float | None:
    if "candidates" not in ctx.series:
        return None
    sizes = []
    for raw in ctx.series["candidates"].dropna():
        try:
            sizes.append(len(json.loads(raw)))
        except (TypeError, ValueError):
            continue
    return float(sum(sizes) / len(sizes)) if sizes else None


def _n_fallback(message: Any) -> int:
    m = _FALLBACK_RE.search(message) if isinstance(message, str) else None
    return int(m.group(1)) if m else 0


def trust(ctx: PlanningContext) -> dict[str, Any]:
    """Payload of ``GET /api/models/trust`` (contract ``Trust`` in ``frontend/src/types/trust.ts``).

    Company-wide: trust is a property of the run (spec §1.4). Cached per context (§4.7)."""
    if not ctx.has_run:
        return {"available": False, "reason": NO_RUN}
    return copy.deepcopy(common.cached(ctx, "trust", build=lambda: _trust(ctx)))


def _trust(ctx: PlanningContext) -> dict[str, Any]:
    ids = pd.Index(ctx.series["series_id"])
    bt_months = common.backtest_months(ctx)
    if not len(bt_months):
        return {"available": False, "reason": NO_BACKTEST}
    fva = fva_report(ctx)
    stair = fva.get("stairstep") or {}
    q = scope_quality(ctx, ids, naive=stair.get("naive"))
    if q is None:
        return {"available": False, "reason": NO_BACKTEST}
    has_history = common.has_overrides_history(ctx)
    params = common.run_params(ctx)
    row = db.query_df(
        "SELECT finished_at, duration_s, n_series, n_models, message FROM forecast_runs WHERE run_id = ?", [ctx.run_id]
    )
    r = row.iloc[0].to_dict() if not row.empty else {}
    lag = ctx.backtest.assign(abs_e=(ctx.backtest["forecast"] - ctx.backtest["actual"]).abs())
    by_lag = lag.groupby("horizon_step")[["abs_e", "actual"]].sum()
    patterns = _patterns(ctx)
    n_models = int(r.get("n_models") or 0) or None
    if n_models is None:
        from app.forecasting.models import MODEL_REGISTRY

        n_models = len(MODEL_REGISTRY)
    return {
        "available": True,
        "run": {
            "run_id": ctx.run_id,
            "finished_at": _iso(r.get("finished_at")),
            "duration_s": _float(r.get("duration_s")),
            "n_series": int(r.get("n_series") or 0) or len(ctx.series),
            "n_models": n_models,
            "n_folds": params["n_folds"],
            "fold_horizon": params["fold_horizon"],
            "horizon": params["horizon"],
            "avg_candidates": _avg_candidates(ctx),
            "backtest_start": f"{bt_months.min():%Y-%m-%d}",
            "backtest_end": f"{bt_months.max():%Y-%m-%d}",
            "n_fallback": _n_fallback(r.get("message")),
            "lag_label": common.lag_label(params["fold_horizon"]),
        },
        "accuracy": q["accuracy"],
        "wmape": q["wmape"],
        "bias": q["bias"],
        "bias_class": q["bias_class"],
        "bias_label": q["bias_label"],
        "naive_wmape": q["naive_wmape"],
        "gain_vs_naive_pp": q["gain_vs_naive_pp"],
        "error_reduction_vs_naive": q["error_reduction_vs_naive"],
        "consensus_wmape": stair.get("consensus") if has_history else None,
        "fva_pp": stair.get("fva_consensus_vs_statistical") if has_history else None,
        "wmape_by_lag": [
            {"lag": int(k), "wmape": float(v.abs_e / v.actual)} for k, v in by_lag.iterrows() if v.actual > 0
        ],
        "confidence_series": q["confidence_series"],
        "confidence_revenue_share": q["confidence_revenue_share"],
        "champions": _champions(ctx),
        "by_pattern": patterns,
        "pattern_insight": pattern_insight(patterns),
        "backtest_monthly": _backtest_monthly(ctx, ids, bt_months),
        "caution": _caution(ctx, _per_series_error(ctx)),
        "verdict": verdict(q),
    }
