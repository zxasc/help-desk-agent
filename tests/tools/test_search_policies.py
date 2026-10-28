import pytest

from help_desk_agent.tools import search_policies

TOP_RESULT_INDEX = 0
SUMMER_OPENING_HOURS = "08:00–20:00"


def _headings(result: dict) -> list[str]:
    return [r["heading"] for r in result["results"]]


@pytest.mark.parametrize(
    ("question", "expected_heading"),
    [
        pytest.param(
            "What time do you open on Saturday?",
            "When are you open?",
            id="opening hours question finds opening hours",
        ),
        pytest.param(
            "How much is an e-bike for a whole day?",
            "Bike rental",
            id="price question finds bike rental prices",
        ),
        pytest.param(
            "I want to cancel my booking, what is the refund?",
            "Cancelling a booking",
            id="refund question finds cancellation rules",
        ),
        pytest.param(
            "How do I contact the staff?",
            "Contact the staff",
            id="contact question finds staff contact",
        ),
        pytest.param(
            "Can I take my dog?",
            "Can I take my dog?",
            id="faq question finds matching faq entry",
        ),
        pytest.param(
            "What is the late return fee?",
            "Late return",
            id="late return question finds late return fee",
        ),
    ],
)
def test_search_policies_ranks_relevant_section_first(question, expected_heading):
    assert _headings(search_policies(question))[TOP_RESULT_INDEX] == expected_heading


def test_search_policies_finds_age_limits_for_age_question():
    assert "Are there age limits?" in _headings(
        search_policies("Can my 14-year-old rent an e-bike?")
    )


def test_search_policies_returns_source_file_and_text():
    top = search_policies("opening hours")["results"][TOP_RESULT_INDEX]
    expected = {
        "source": "faq.md",
        "heading": "When are you open?",
        "text_has_opening_hours": True,
    }

    assert {
        "source": top["source"],
        "heading": top["heading"],
        "text_has_opening_hours": SUMMER_OPENING_HOURS in top["text"],
    } == expected


def test_search_policies_returns_no_results_for_unrelated_question():
    question = "What is the capital of Australia?"
    expected = {
        "query": question,
        "results": [],
        "message": "No matching policy found.",
    }

    assert search_policies(question) == expected


@pytest.mark.parametrize(
    "top_k",
    [
        pytest.param(1, id="top_k 1 returns one section"),
        pytest.param(2, id="top_k 2 returns two sections"),
        pytest.param(3, id="top_k 3 returns three sections"),
    ],
)
def test_search_policies_respects_top_k(top_k):
    assert len(search_policies("bike", top_k=top_k)["results"]) == top_k
