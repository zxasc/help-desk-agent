from datetime import timedelta
from typing import Any

import pytest

from help_desk_agent import tools
from help_desk_agent.core import CURRENT_TIME

DEFAULT_HOURS_UNTIL_START = 72
DEFAULT_RENTAL_PRICE_EUR = 40.0
DEFAULT_DEPOSIT_EUR = 50.0
BOOKING_FEE_EUR = 2.0
BIKES_PER_BOOKING = 1
RENTAL_LENGTH = timedelta(days=1)


def make_booking(
    booking_id: str,
    *,
    hours_until_start: float = DEFAULT_HOURS_UNTIL_START,
    status: str = "confirmed",
    rental_price_eur: float = DEFAULT_RENTAL_PRICE_EUR,
    deposit_eur: float = DEFAULT_DEPOSIT_EUR,
    paid_with: str = "card",
) -> dict[str, Any]:
    start = CURRENT_TIME + timedelta(hours=hours_until_start)
    return {
        "id": booking_id,
        "status": status,
        "bike_type": "city",
        "bikes": BIKES_PER_BOOKING,
        "start": start.isoformat(),
        "end": (start + RENTAL_LENGTH).isoformat(),
        "add_ons": [],
        "rental_price_eur": rental_price_eur,
        "booking_fee_eur": BOOKING_FEE_EUR,
        "deposit_eur": deposit_eur,
        "paid_with": paid_with,
    }


MOCK_BOOKINGS = [
    make_booking("CW-1001"),
]


@pytest.fixture(autouse=True)
def mock_bookings(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    bookings = {b["id"]: b for b in MOCK_BOOKINGS}
    monkeypatch.setattr(tools, "load_bookings", lambda: bookings)
    return bookings
