import copy
from itertools import combinations
from types import SimpleNamespace

import pytest

from lab9 import gate, stats
from lab9.graders import DbFactKept, RefundAmountCorrect, ReplyAmountCorrect
from lab9.trace_case import investigate

pytestmark = pytest.mark.student


@pytest.mark.parametrize("shape,ok", [("seeded_regression", False), ("fixed", True)])
def test_c002_ticket_delay_does_not_override_order(shape, ok):
    case = investigate(shape, "C-002", 11)
    trial = case["trial"]
    ctx = SimpleNamespace(output=trial, expected_output=case["label"])
    assert trial["events"][1]["payload"]["lookup_order"]["order"]["delay_days"] == 2
    assert DbFactKept().evaluate(ctx).value is ok
    assert RefundAmountCorrect().evaluate(ctx).value is ok
    assert trial["lab8_pass"] is ok


@pytest.mark.parametrize("text,correct", [
    ("Dạ, LogiX đã hoàn 35.000đ cho đơn O-808.", False),
    ("LogiX đã hoàn phí 20,000 VND cho đơn O-808.", True),
    ("Phí ship 35.000đ. Đã hoàn 20 000 đồng.", True),
    ("Đã hoàn 20000₫. Tiền về trong 3–5 ngày.", True),
    ("Yêu cầu đang được xem xét.", True),
])
def test_reply_uses_committed_amount(text, correct):
    ctx = SimpleNamespace(output={"snapshot": {"refund_vnd": 20000},
                                  "events": [{"kind": "reply", "payload": {"text": text}}]})
    assert ReplyAmountCorrect().evaluate(ctx).value is correct


def test_advanced_integrity_rejects_plausible_but_inconsistent_reports():
    rows = [{"item_id": "A", "seed": seed, "pass_rate": True, "slices": ["money"]} for seed in (1, 2)]
    base = {"manifest": {"items": 1, "seeds": [1, 2]}, "metrics": {"pass_rate": 1.0},
            "rows": rows, "evaluator_failures": []}
    spec = {"metrics": [{"id": "pass_rate"}]}
    for patch in ({"rows": [rows[0], rows[0]]}, {"evaluator_failures": ["boom"]},
                  {"metrics": {"pass_rate": 0.9}}, {"rows": [rows[0], dict(rows[1], slices=[])]}):
        assert gate.integrity_check(base | patch, base, spec)
    assert gate.integrity_check(copy.deepcopy(base), base, spec) == []


def test_advanced_pass_k_matches_enumerated_subsets():
    for n in range(1, 8):
        for c in range(n + 1):
            outcomes = [True] * c + [False] * (n - c)
            for k in range(1, n + 1):
                draws = list(combinations(outcomes, k))
                assert stats.pass_at_k(n, c, k) == pytest.approx(sum(map(any, draws)) / len(draws))
                assert stats.pass_hat_k(n, c, k) == pytest.approx(sum(map(all, draws)) / len(draws))
