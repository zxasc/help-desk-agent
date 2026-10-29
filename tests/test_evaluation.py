import json
from dataclasses import dataclass, field

import pytest

from help_desk_agent.core import AgentResult, ToolCall, ToolRun
from help_desk_agent.evaluation import EvalCase, check

ANSWER = "You get 90.00 EUR back to your card."
CASE = EvalCase(
    id="refund-full",
    category="refund",
    question="How much do I get back for CW-1001?",
    expected_tools=["calculate_refund"],
    forbidden_tools=["get_booking"],
    numbers=[90],
    forbidden_numbers=[92],
    contains=[["card", "voucher"]],
    not_contains=["cancel it for you"],
)
REFUND_RUN = ToolRun(
    call=ToolCall(id="call-1", name="calculate_refund", arguments="{}"),
    result=json.dumps({"total_refund_eur": 90.0, "deposit_refund_eur": 50.0}),
)
BOOKING_RUN = ToolRun(
    call=ToolCall(id="call-2", name="get_booking", arguments="{}"),
    result="{}",
)


@dataclass(frozen=True, kw_only=True)
class CheckCase:
    id: str
    answer: str | None
    tool_runs: list[ToolRun] = field(default_factory=lambda: [REFUND_RUN])
    expected_failures: list[str]


CHECK_CASES = [
    CheckCase(
        id="answer with expected tool and amount passes",
        answer=ANSWER,
        expected_failures=[],
    ),
    CheckCase(
        id="number format and case do not matter",
        answer="You get €90,00 back as a VOUCHER.",
        expected_failures=[],
    ),
    CheckCase(
        id="missing expected tool fails",
        answer="You get 90 EUR back to your card.",
        tool_runs=[],
        expected_failures=[
            "did not call calculate_refund",
            "amount 90 does not come from any tool result",
        ],
    ),
    CheckCase(
        id="forbidden tool fails",
        answer=ANSWER,
        tool_runs=[BOOKING_RUN, REFUND_RUN],
        expected_failures=["called get_booking"],
    ),
    CheckCase(
        id="answer without required number fails",
        answer="You get 50 EUR back to your card.",
        expected_failures=["missing 90"],
    ),
    CheckCase(
        id="answer with forbidden number fails",
        answer="You get 90 EUR, or 92 to your card.",
        expected_failures=["mentions 92"],
    ),
    CheckCase(
        id="answer without any of the phrasings fails",
        answer="You get 90 EUR back.",
        expected_failures=["missing 'card' / 'voucher'"],
    ),
    CheckCase(
        id="answer with forbidden phrase fails",
        answer=f"{ANSWER} I can cancel it for you.",
        expected_failures=["mentions 'cancel it for you'"],
    ),
    CheckCase(
        id="made up amount fails",
        answer=f"{ANSWER} Plus 2 EUR fee.",
        expected_failures=["amount 2 does not come from any tool result"],
    ),
    CheckCase(
        id="real contact details pass",
        answer=f"{ANSWER} Call +48 000 000 000 or help@citywheels.example.",
        expected_failures=[],
    ),
    CheckCase(
        id="made up contact details fail",
        answer=f"{ANSWER} Call +48 123 456 789 or info@citywheels.com.",
        expected_failures=[
            "made-up contact detail +48 123 456 789",
            "made-up contact detail info@citywheels.com",
        ],
    ),
    CheckCase(
        id="empty answer fails",
        answer=None,
        expected_failures=["missing 90", "missing 'card' / 'voucher'", "empty answer"],
    ),
]


@pytest.mark.parametrize("case", CHECK_CASES, ids=lambda case: case.id)
def test_check(case: CheckCase):
    result = AgentResult(answer=case.answer, tool_runs=case.tool_runs)

    assert check(CASE, result).failures == case.expected_failures
