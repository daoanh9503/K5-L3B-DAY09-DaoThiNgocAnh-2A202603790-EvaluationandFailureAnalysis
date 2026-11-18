"""Regression test from docs/trace_case.md: seeded_regression C-002@11 (FM-03 ticket_trust).

First wrong step: event 3 `model_override {"delay_days": 5}` overrides the DB's delay_days=2,
so a claim that must be denied gets a 20.000đ refund. The graders must flag the buggy trial and
leave the same claim@seed on `fixed` alone.
"""
import pytest

pytestmark = pytest.mark.student
CLAIM, SEED = "C-002", 11


def grade(shape):
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9 import graders
    from lab9.trace_case import investigate

    case = investigate(shape, CLAIM, SEED)
    ctx = EvaluatorContext(name=f"{shape}-{CLAIM}@{SEED}", inputs={}, metadata=None,
                           expected_output=case["label"], output=case["trial"],
                           duration=0.0, _span_tree=None, attributes={}, metrics={})
    return case["trial"], {"db_fact_kept": graders.DbFactKept().evaluate(ctx).value,
                           "refund_amount_correct": graders.RefundAmountCorrect().evaluate(ctx).value}


def test_ticket_trust_first_wrong_step_is_flagged():
    trial, scores = grade("seeded_regression")
    kinds = [e.get("kind") for e in trial["events"]]
    first = kinds.index("model_override")
    assert kinds[first - 1] == "investigator"                      # DB fact was read correctly just before
    assert trial["events"][first]["payload"] == {"delay_days": 5}  # ticket's 5 days replace the DB's 2
    assert scores == {"db_fact_kept": False, "refund_amount_correct": False}


def test_fixed_keeps_db_fact_on_same_trial():
    trial, scores = grade("fixed")
    assert "model_override" not in [e.get("kind") for e in trial["events"]]
    assert scores == {"db_fact_kept": True, "refund_amount_correct": True}
