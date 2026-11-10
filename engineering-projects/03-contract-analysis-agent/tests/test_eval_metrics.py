import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eval_metrics import (  # noqa: E402
    classify_error, compute_metrics, is_gold_positive, macro_average, overlap_fraction,
)


def test_overlap_fraction_full_containment_is_one():
    # clause [10,90) is entirely inside the much wider span [0,100)
    assert overlap_fraction(10, 90, 0, 100) == 1.0


def test_overlap_fraction_no_overlap_is_zero():
    assert overlap_fraction(0, 10, 20, 30) == 0.0


def test_overlap_fraction_partial():
    # clause [0,100), span [50,150): overlap [50,100) = 50 of clause's 100
    assert overlap_fraction(0, 100, 50, 150) == 0.5


def test_is_gold_positive_at_threshold():
    assert is_gold_positive(0, 100, [(50, 150)], threshold=0.5) is True
    assert is_gold_positive(0, 100, [(51, 150)]) is False  # 49% < 50%


def test_is_gold_positive_any_span_matches():
    spans = [(1000, 1010), (0, 60)]  # second span covers 60% of [0,100)
    assert is_gold_positive(0, 100, spans) is True


def test_compute_metrics_basic_counts():
    gold = {"c1": True, "c2": True, "c3": False, "c4": False}
    pred = {"c1": True, "c2": False, "c3": True, "c4": False}
    m = compute_metrics(gold, pred, "Governing Law")
    assert (m.tp, m.fn, m.fp, m.tn) == (1, 1, 1, 1)
    assert m.support == 2
    assert m.precision == 0.5
    assert m.recall == 0.5
    assert round(m.f1, 4) == 0.5


def test_compute_metrics_missing_prediction_treated_as_false():
    gold = {"c1": True}
    pred = {}  # c1 has no entry at all
    m = compute_metrics(gold, pred, "Governing Law")
    assert m.fn == 1 and m.tp == 0


def test_compute_metrics_perfect_score():
    gold = {"c1": True, "c2": False}
    pred = {"c1": True, "c2": False}
    m = compute_metrics(gold, pred, "x")
    assert m.precision == 1.0 and m.recall == 1.0 and m.f1 == 1.0


def test_compute_metrics_no_positives_at_all_does_not_divide_by_zero():
    gold = {"c1": False, "c2": False}
    pred = {"c1": False, "c2": False}
    m = compute_metrics(gold, pred, "x")
    assert m.precision == 0.0 and m.recall == 0.0 and m.f1 == 0.0 and m.support == 0


def test_macro_average_of_two_types():
    m1 = compute_metrics({"a": True}, {"a": True}, "A")  # P=R=F1=1
    m2 = compute_metrics({"b": True}, {"b": False}, "B")  # P=R=F1=0
    avg = macro_average([m1, m2])
    assert avg["precision"] == 0.5
    assert avg["recall"] == 0.5
    assert avg["f1"] == 0.5
    assert avg["support"] == 2


def test_classify_error_boundary_problem_false_negative():
    # Span [70,100) over clause [0,100): only 30% clause-side overlap, and
    # the span itself is fully inside the clause (span_frac=1.0) but the
    # span isn't small relative to the clause (30/100 is not <20%), so
    # this should read as a boundary misalignment, not a buried span.
    tag = classify_error("clause text", gold_spans=[(70, 100)], clause_start=0, clause_end=100,
                          is_false_positive=False)
    assert tag == "boundary problem"


def test_classify_error_buried_span_false_negative():
    # Gold span [10,15) is entirely inside a much larger clause [0,1000) --
    # span_frac=1.0 (the whole span is captured) but it's under 20% of the
    # clause's own length, so the clause-side overlap fraction is tiny.
    tag = classify_error("clause text", gold_spans=[(10, 15)], clause_start=0, clause_end=1000,
                          is_false_positive=False)
    assert tag == "buried span"


def test_classify_error_extraction_gap_false_negative():
    tag = classify_error("clause text", gold_spans=[(500, 600)], clause_start=0, clause_end=100,
                          is_false_positive=False)
    assert tag == "extraction gap"


def test_classify_error_other_false_positive_with_no_gold_spans():
    tag = classify_error("clause text", gold_spans=[], clause_start=0, clause_end=100,
                          is_false_positive=True)
    assert tag == "other"


def test_classify_error_boundary_problem_false_positive():
    tag = classify_error("clause text", gold_spans=[(80, 95)], clause_start=0, clause_end=100,
                          is_false_positive=True)
    assert tag == "boundary problem"
