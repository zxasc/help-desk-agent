import re
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from help_desk_agent.agent import Agent
from help_desk_agent.core import AgentResult
from help_desk_agent.exceptions import LLMException

CITYWHEELS_PHONE = "+48 000 000 000"
CITYWHEELS_EMAIL = "help@citywheels.example"


NUMBER = re.compile(r"\d+(?:[.,]\d+)?")  # 90, 90.00 and 90,00 are all the number 9
MONEY = re.compile(
    r"€\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*(?:€|eur\b|euro)", re.IGNORECASE
)  # A number with a euro sign or EUR before or after it: €90, 90 EUR, 90.00€
PHONE = re.compile(
    r"\+\d[\d ()-]{6,}\d"
)  # Only numbers with a country code, so amounts and dates never look like phones
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


@dataclass(frozen=True, kw_only=True)
class EvalCase:
    id: str
    category: str
    question: str
    expected_tools: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    numbers: list[float] = field(default_factory=list)
    forbidden_numbers: list[float] = field(default_factory=list)
    contains: list[list[str]] = field(
        default_factory=list
    )  # The answer must contain at least one phrase from each inner list
    not_contains: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class EvalOutcome:
    case: EvalCase
    answer: str | None
    tools_called: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def load_cases(path: Path) -> list[EvalCase]:
    with path.open("rb") as file:
        questions = tomllib.load(file)["question"]
    return [EvalCase(**question) for question in questions]


def _normalize(text: str) -> str:
    return text.lower().replace("\u2019", "'")


def _to_number(text: str) -> float:
    return float(text.replace(",", "."))


def _numbers(text: str) -> list[float]:
    return [_to_number(match) for match in NUMBER.findall(text)]


def _money(text: str) -> list[float]:
    return [_to_number(before or after) for before, after in MONEY.findall(text)]


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _amounts_not_from_tools(answer: str, tool_results: list[str]) -> list[float]:
    numbers_in_tool_results = [
        number for result in tool_results for number in _numbers(result)
    ]
    return [
        amount for amount in _money(answer) if amount not in numbers_in_tool_results
    ]


def _fake_contact_details(answer: str) -> list[str]:
    phones = [
        phone
        for phone in PHONE.findall(answer)
        if _digits(phone) != _digits(CITYWHEELS_PHONE)
    ]
    emails = [
        email for email in EMAIL.findall(answer) if email.lower() != CITYWHEELS_EMAIL
    ]
    return phones + emails


def check(case: EvalCase, result: AgentResult) -> EvalOutcome:
    tools_called = [run.call.name for run in result.tool_runs]
    tool_results = [run.result for run in result.tool_runs]
    answer = result.answer or ""
    text = _normalize(answer)
    numbers = _numbers(answer)
    failures = [
        *[
            f"did not call {tool}"
            for tool in case.expected_tools
            if tool not in tools_called
        ],
        *[f"called {tool}" for tool in case.forbidden_tools if tool in tools_called],
        *[f"missing {n:g}" for n in case.numbers if n not in numbers],
        *[f"mentions {n:g}" for n in case.forbidden_numbers if n in numbers],
        *[
            f"missing {' / '.join(repr(p) for p in phrases)}"
            for phrases in case.contains
            if not any(_normalize(phrase) in text for phrase in phrases)
        ],
        *[
            f"mentions {phrase!r}"
            for phrase in case.not_contains
            if _normalize(phrase) in text
        ],
        *[
            f"amount {amount:g} does not come from any tool result"
            for amount in _amounts_not_from_tools(answer, tool_results)
        ],
        *[
            f"made-up contact detail {detail}"
            for detail in _fake_contact_details(answer)
        ],
    ]
    if not answer:
        failures.append("empty answer")
    return EvalOutcome(
        case=case,
        answer=result.answer,
        tools_called=tools_called,
        failures=failures,
    )


async def run_case(agent: Agent, case: EvalCase) -> EvalOutcome:
    try:
        result = await agent.run(case.question)
    except LLMException as exc:
        return EvalOutcome(
            case=case, answer=None, tools_called=[], failures=[f"LLM error: {exc}"]
        )
    return check(case, result)


def render_results(outcomes: list[EvalOutcome], *, model: str) -> str:
    passed = sum(outcome.passed for outcome in outcomes)
    totals = Counter(outcome.case.category for outcome in outcomes)
    passes = Counter(outcome.case.category for outcome in outcomes if outcome.passed)

    lines = [
        "# Evaluation results",
        "",
        f"Model: `{model}`",
        "",
        f"**{passed}/{len(outcomes)} questions passed.**",
        "",
        "| Category | Passed |",
        "| --- | --- |",
        *[
            f"| {category} | {passes[category]}/{total} |"
            for category, total in totals.items()
        ],
        "",
        "| Result | Question | Category | Tools called | Failed checks |",
        "| --- | --- | --- | --- | --- |",
    ]
    for outcome in outcomes:
        lines.append(
            "| {result} | `{id}` | {category} | {tools} | {failures} |".format(
                result="✅" if outcome.passed else "❌",
                id=outcome.case.id,
                category=outcome.case.category,
                tools=", ".join(outcome.tools_called) or "none",
                failures="; ".join(outcome.failures),
            )
        )

    lines += ["", "## Answers", ""]
    for outcome in outcomes:
        lines += [
            f"### {'✅' if outcome.passed else '❌'} `{outcome.case.id}`",
            "",
            f"> {outcome.case.question}",
            "",
            outcome.answer or "_(no answer)_",
            "",
        ]
    return "\n".join(lines)
