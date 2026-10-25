"""Model ranking, Champion/Challenger selection and model confidence."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelEvaluation:
    model: str
    wmape: float
    bias: float
    rmse: float
    mae: float = math.nan
    mape: float = math.nan
    smape: float = math.nan
    mase: float = math.nan
    fold_wmape: list[float] = field(default_factory=list)
    status: str = "ok"
    params: dict[str, Any] = field(default_factory=dict)
    rank: int | None = None

    @property
    def wmape_std(self) -> float:
        if len(self.fold_wmape) < 2:
            return math.nan
        m = sum(self.fold_wmape) / len(self.fold_wmape)
        return math.sqrt(sum((w - m) ** 2 for w in self.fold_wmape) / (len(self.fold_wmape) - 1))


def _key(e: ModelEvaluation) -> tuple[float, float, float]:
    w = e.wmape if e.wmape is not None and not math.isnan(e.wmape) else math.inf
    b = abs(e.bias) if e.bias is not None and not math.isnan(e.bias) else math.inf
    r = e.rmse if e.rmse is not None and not math.isnan(e.rmse) else math.inf
    return (round(w, 6), round(b, 6), r)


def rank_models(evals: list[ModelEvaluation]) -> list[ModelEvaluation]:
    """Rank by WMAPE (primary), then |Bias|, then RMSE. Failed models are unranked."""
    ok = sorted([e for e in evals if e.status == "ok"], key=_key)
    for i, e in enumerate(ok, start=1):
        e.rank = i
    return ok + [e for e in evals if e.status != "ok"]


def select_champion(evals: list[ModelEvaluation]) -> tuple[ModelEvaluation | None, ModelEvaluation | None]:
    ranked = [e for e in rank_models(evals) if e.rank is not None]
    champion = ranked[0] if ranked else None
    challenger = ranked[1] if len(ranked) > 1 else None
    return champion, challenger


def model_confidence(
    champion: ModelEvaluation | None,
    challenger: ModelEvaluation | None,
    history_months: int,
) -> tuple[str, int, dict[str, int]]:
    """High / Medium / Low confidence from error, stability, history and margin."""
    if champion is None or math.isnan(champion.wmape):
        return "Low", 0, {"error": 0, "stability": 0, "history": 0, "margin": 0}
    w = champion.wmape
    error = 40 if w <= 0.15 else 28 if w <= 0.25 else 15 if w <= 0.40 else 5
    std = champion.wmape_std
    stability = 12 if math.isnan(std) else 20 if std <= 0.05 else 12 if std <= 0.10 else 4
    history = 20 if history_months >= 48 else 12 if history_months >= 24 else 4
    if challenger is None or math.isnan(challenger.wmape) or w == 0:
        margin = 12
    else:
        gap = (challenger.wmape - w) / max(w, 1e-9)
        margin = 20 if gap >= 0.15 else 12 if gap >= 0.05 else 6
    score = error + stability + history + margin
    label = "High" if score >= 75 else "Medium" if score >= 50 else "Low"
    return label, score, {"error": error, "stability": stability, "history": history, "margin": margin}
