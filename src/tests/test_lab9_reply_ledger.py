"""M3 FM-08: the reply must not state an amount the ledger does not hold."""
import pytest

pytestmark = pytest.mark.student


@pytest.fixture(scope="module")
def graders():
    from lab9 import graders

    return graders


def ctx(reply, refund_vnd):
    from pydantic_evals.evaluators import EvaluatorContext

    events = [] if reply is None else [{"kind": "reply", "payload": {"text": reply}}]
    trial = {"snapshot": {"refund_vnd": refund_vnd, "refund_count": int(refund_vnd > 0)}, "unexpected_rows": 0,
             "blob": "", "events": events, "result": {}, "lab8_pass": True, "lab8_reason": None}
    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output={}, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


@pytest.mark.parametrize("reply,ledger,ok", [
    ("Dạ, LogiX đã hoàn 20.000đ cho đơn O-808.", 20000, True),
    ("LogiX đã hoàn phí 35.000đ cho đơn O-107 của anh/chị ạ.", 35000, True),     # paraphrase
    ("Dạ, LogiX đã hoàn 35.000đ cho đơn O-808.", 20000, False),                  # C-008 misreport
    ("Dạ, LogiX đã hoàn 150.000đ cho đơn O-515.", 120000, False),                # C-014 misreport
    ("Dạ, LogiX đã hoàn 35.000đ cho đơn O-909.", 0, False),                      # ignore_denied
    ("Dạ, đơn O-202 chưa đủ điều kiện hoàn theo chính sách hiện hành.", 0, True),
    ("Dạ, anh/chị có 2 đơn, LogiX đã ghi nhận yêu cầu.", 0, True),              # "2 đơn" is not money
    (None, 20000, True),                                                         # no reply event
])
def test_reply_matches_ledger(graders, reply, ledger, ok):
    assert graders.ReplyMatchesLedger().evaluate(ctx(reply, ledger)).value is ok
