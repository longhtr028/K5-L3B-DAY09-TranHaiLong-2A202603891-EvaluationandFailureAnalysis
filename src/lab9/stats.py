"""Calibration and paired item-level uncertainty for the LogiX evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from math import comb, isfinite
from numbers import Integral

import numpy as np
from scipy.stats import bootstrap


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """Count FAIL as positive. Refuse unpaired observations or unknown labels."""
    cells = {("FAIL", "FAIL"): "tp", ("PASS", "FAIL"): "fp",
             ("FAIL", "PASS"): "fn", ("PASS", "PASS"): "tn"}
    counts = dict.fromkeys(cells.values(), 0)
    for pair in zip(human, judge, strict=True):
        if pair not in cells:
            raise ValueError(f"invalid PASS/FAIL pair: {pair}")
        counts[cells[pair]] += 1
    return counts


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    counts = confusion(human, judge)
    hits = counts["tp"]
    return hits / max(1, hits + counts["fp"]), hits / max(1, hits + counts["fn"])


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    counts = confusion(human, judge)
    tp, fp, fn, tn = (counts[k] for k in ("tp", "fp", "fn", "tn"))
    n = tp + fp + fn + tn
    expected = (tp + fn) * (tp + fp) + (tn + fp) * (tn + fn)
    if n * n == expected:
        raise ValueError("kappa is undefined without a chance-adjusted denominator")
    return (n * (tp + tn) - expected) / (n * n - expected)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    if not all(isfinite(v) and 0 <= v <= 1 for v in (observed_rate, sensitivity, specificity)):
        raise ValueError("rates must be finite probabilities")
    denominator = sensitivity + specificity - 1
    if denominator == 0:
        raise ValueError("prevalence is unidentifiable for this judge")
    return min(1.0, max(0.0, (observed_rate + specificity - 1) / denominator))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """Resample corresponding items together after averaging seeds within item."""
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if x.ndim != 1 or x.shape != y.shape or not x.size:
        raise ValueError("expected two nonempty, equally sized vectors")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("item means must be finite")
    differences = x - y
    delta = float(differences.mean())
    if np.all(differences == differences[0]):
        return delta, delta, delta

    def mean_difference(left, right, axis):
        return np.mean(left - right, axis=axis)

    interval = bootstrap((x, y), mean_difference, paired=True, method="percentile",
                         n_resamples=n_resamples, rng=np.random.default_rng(rng),
                         confidence_level=confidence).confidence_interval
    return delta, float(interval.low), float(interval.high)


def _trial_combinations(n: int, c: int, k: int) -> int:
    if not all(isinstance(v, Integral) and not isinstance(v, bool) for v in (n, c, k)):
        raise ValueError("n, c and k must be integers")
    if not (0 <= c <= n and 1 <= k <= n):
        raise ValueError("require 0 <= c <= n and 1 <= k <= n")
    return comb(n, k)


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that at least one trial in a size-k sample passes."""
    total = _trial_combinations(n, c, k)
    return (total - comb(n - c, k)) / total


def pass_hat_k(n: int, c: int, k: int) -> float:
    """Probability that every trial in a size-k sample passes."""
    total = _trial_combinations(n, c, k)
    return comb(c, k) / total
