import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from help_desk_agent.core import CURRENT_TIME, Tool

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
POLICIES_DIR = DATA_DIR / "policies"
BOOKINGS_PATH = DATA_DIR / "bookings.json"

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "do",
    "does",
    "for",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "me",
    "much",
    "my",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "where",
    "will",
    "with",
    "you",
    "your",
}

# Prefix length used to match word forms, e.g. "cancel" ~ "cancelled" ~ "cancellation"
STEM_LENGTH = 5


@dataclass(frozen=True, kw_only=True)
class PolicySection:
    source: str
    heading: str
    text: str


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in STOPWORDS]


def _matches(query_word: str, words: set[str]) -> bool:
    if len(query_word) < 3:
        return query_word in words  # "e", "14": prefixes would match almost anything
    stem = query_word[:STEM_LENGTH]
    # Second check covers short base forms: "opening" ~ "open", "rented" ~ "rent"
    return any(
        w.startswith(stem) or (len(w) >= 4 and query_word.startswith(w)) for w in words
    )


def load_policy_sections(policies_dir: Path = POLICIES_DIR) -> list[PolicySection]:
    """Split every policy file into its `##` sections."""
    sections = []
    for path in sorted(policies_dir.glob("*.md")):
        for chunk in re.split(r"^(?=## )", path.read_text(), flags=re.MULTILINE):
            lines = chunk.strip().splitlines()
            if not lines or not lines[0].startswith("## "):
                continue  # document title and intro
            sections.append(
                PolicySection(
                    source=path.name,
                    heading=lines[0].removeprefix("## ").strip(),
                    text="\n".join(lines[1:]).strip(),
                )
            )
    return sections


def search_policies(query: str, top_k: int = 3) -> dict[str, Any]:
    """Find the policy sections that share the most words with the query."""
    query_words = set(_tokenize(query))
    scored = []
    for section in load_policy_sections():
        heading_words = set(_tokenize(section.heading))
        body_words = set(_tokenize(section.text))
        # A match in the heading counts double: headings say what a section is about
        score = sum(
            2 * _matches(w, heading_words) + _matches(w, body_words)
            for w in query_words
        )
        if score > 0:
            scored.append((score, section))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = [
        {"source": s.source, "heading": s.heading, "text": s.text}
        for _, s in scored[:top_k]
    ]
    if not results:
        return {"query": query, "results": [], "message": "No matching policy found."}
    return {"query": query, "results": results}


def _normalize_booking_id(booking_id: str) -> str:
    booking_id = booking_id.strip().upper()
    if booking_id.isdigit():
        booking_id = f"CW-{booking_id}"
    return booking_id


def load_bookings(path: Path = BOOKINGS_PATH) -> dict[str, dict[str, Any]]:
    return {b["id"]: b for b in json.loads(path.read_text())}


def get_booking(booking_id: str) -> dict[str, Any]:
    booking_id = _normalize_booking_id(booking_id)
    booking = load_bookings().get(booking_id)
    if booking is None:
        return {"found": False, "booking_id": booking_id, "error": "Booking not found."}
    return {"found": True, "booking": booking}


def _eur(amount: Decimal) -> float:
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _refund_percent(hours_before_start: float) -> int:
    if hours_before_start >= 48:
        return 100
    if hours_before_start >= 24:
        return 50
    return 0


def calculate_refund(booking_id: str, now: datetime = CURRENT_TIME) -> dict[str, Any]:
    lookup = get_booking(booking_id)
    if not lookup["found"]:
        return lookup
    booking = lookup["booking"]

    if booking["status"] != "confirmed":
        return {
            "booking_id": booking["id"],
            "can_cancel": False,
            "reason": f"Bookings with status '{booking['status']}' cannot be cancelled "
            "and nothing is refunded.",
            "total_refund_eur": 0.0,
        }

    start = datetime.fromisoformat(booking["start"])
    hours_before_start = (start - now).total_seconds() / 3600
    percent = _refund_percent(hours_before_start)

    rental_refund = Decimal(str(booking["rental_price_eur"])) * percent / 100
    deposit_refund = Decimal(str(booking["deposit_eur"]))  # always refunded in full

    if booking["paid_with"] == "voucher":
        refund_method = "As a new voucher of the same value, never as money."
    else:
        refund_method = "To the same card within 5 working days."

    return {
        "booking_id": booking["id"],
        "can_cancel": True,
        "cancelled_at": now.isoformat(),
        "hours_before_start": round(hours_before_start, 1),
        "rental_refund_percent": percent,
        "rental_refund_eur": _eur(rental_refund),
        "booking_fee_refund_eur": 0.0,  # never refunded
        "deposit_refund_eur": _eur(deposit_refund),
        "total_refund_eur": _eur(rental_refund + deposit_refund),
        "refund_method": refund_method,
    }


BOOKING_ID_PARAMETERS = {
    "type": "object",
    "properties": {
        "booking_id": {
            "type": "string",
            "description": "Booking number, for example CW-1001.",
        }
    },
    "required": ["booking_id"],
}


TOOLS = {
    tool.name: tool
    for tool in (
        Tool(
            name="search_policies",
            description="Search the CityWheels policy documents (prices, opening hours, "
            "cancellations, refunds, FAQ, staff contact) and return the most relevant sections.",
            func=search_policies,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords or the customer's question.",
                    }
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_booking",
            description="Get the details of one booking by its booking number.",
            func=get_booking,
            parameters=BOOKING_ID_PARAMETERS,
        ),
        Tool(
            name="calculate_refund",
            description="Calculate how much the customer gets back if they cancel the "
            "booking now. Always use this for refund amounts.",
            func=calculate_refund,
            parameters=BOOKING_ID_PARAMETERS,
        ),
    )
}
