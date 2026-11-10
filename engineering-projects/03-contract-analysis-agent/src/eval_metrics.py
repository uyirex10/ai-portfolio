"""Clause-level evaluation metrics. Pure functions, no LLM involved --
takes gold labels and predicted labels (however they were produced) and
computes precision/recall/F1/support. Gold-label computation (does a
clause count as a positive example for type T) only needs the frozen
splitter's offsets and CUAD's labeled spans; it needs no LLM call at
all and is always computable, independent of whether predictions exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

GOLD_OVERLAP_THRESHOLD = 0.50


def overlap_fraction(clause_start: int, clause_end: int, span_start: int, span_end: int) -> float:
    """Fraction of the CLAUSE's length that the span overlaps -- not the
    span's length. A clause is "positive for T" if enough of *it* is
    covered by a T-labeled span, which is what determines whether a
    classifier looking at that clause's text should have called it T."""
    inter_start = max(clause_start, span_start)
    inter_end = min(clause_end, span_end)
    inter = max(0, inter_end - inter_start)
    clause_len = clause_end - clause_start
    return inter / clause_len if clause_len else 0.0


def is_gold_positive(clause_start: int, clause_end: int, spans: List[Tuple[int, int]],
                      threshold: float = GOLD_OVERLAP_THRESHOLD) -> bool:
    return any(overlap_fraction(clause_start, clause_end, s, e) >= threshold for s, e in spans)


@dataclass
class ClassificationMetrics:
    clause_type: str
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def support(self) -> int:
        return self.tp + self.fn

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


def compute_metrics(gold: Dict[str, bool], pred: Dict[str, bool], clause_type: str) -> ClassificationMetrics:
    """`gold`/`pred`: clause_id -> bool, for ONE clause_type. Every
    clause_id in `gold` must be accounted for; a clause_id gold has but
    pred lacks is treated as predicted False (fail closed -- an absent
    prediction is not assumed positive)."""
    tp = fp = fn = tn = 0
    for cid, is_gold in gold.items():
        is_pred = pred.get(cid, False)
        if is_gold and is_pred:
            tp += 1
        elif is_gold and not is_pred:
            fn += 1
        elif not is_gold and is_pred:
            fp += 1
        else:
            tn += 1
    return ClassificationMetrics(clause_type=clause_type, tp=tp, fp=fp, fn=fn, tn=tn)


def macro_average(metrics: List[ClassificationMetrics]) -> dict:
    if not metrics:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "support": 0}
    return {
        "precision": sum(m.precision for m in metrics) / len(metrics),
        "recall": sum(m.recall for m in metrics) / len(metrics),
        "f1": sum(m.f1 for m in metrics) / len(metrics),
        "support": sum(m.support for m in metrics),
    }


def classify_error(clause_text: str, gold_spans: List[Tuple[int, int]], clause_start: int,
                    clause_end: int, is_false_positive: bool) -> str:
    """Best-effort auto-tag for one error, not a certainty -- 'other' is
    the honest fallback whenever none of the heuristics clearly fire."""
    if not gold_spans:
        return "other"

    clause_len = clause_end - clause_start
    # For each span: how much of the CLAUSE it covers, and how much of
    # the SPAN ITSELF falls inside the clause (the two differ a lot when
    # the clause is much bigger than the span).
    clause_fracs = [overlap_fraction(clause_start, clause_end, s, e) for s, e in gold_spans]
    best_clause_frac = max(clause_fracs)

    if is_false_positive:
        if 0 < best_clause_frac < GOLD_OVERLAP_THRESHOLD:
            return "boundary problem"  # likely an adjacent clause actually holds the real span
        return "other"

    # False negative: gold says positive, prediction said no.
    if best_clause_frac == 0:
        return "extraction gap"  # the labeled span doesn't overlap this clause at all

    best_idx = clause_fracs.index(best_clause_frac)
    s, e = gold_spans[best_idx]
    span_len = e - s
    span_frac = (min(clause_end, e) - max(clause_start, s)) / span_len if span_len else 0
    if span_frac >= 0.8 and clause_len and span_len / clause_len < 0.20:
        return "buried span"  # the span is basically all there, just diluted by a much bigger clause
    if best_clause_frac < GOLD_OVERLAP_THRESHOLD:
        return "boundary problem"
    return "other"
