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

# Hours before start that hit each cancellation rule
FULL_REFUND_MIN_HOURS = 48
HALF_REFUND_MIN_HOURS = 24
BETWEEN_REFUND_LIMITS_HOURS = 30
UNDER_HALF_REFUND_HOURS = 6
EXPENSIVE_RENTAL_PRICE_EUR = 80.0
HIGH_DEPOSIT_EUR = 300.0
ODD_RENTAL_PRICE_EUR = 12.35


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
    make_booking("CW-1001", hours_until_start=DEFAULT_HOURS_UNTIL_START),
    make_booking("CW-2048", hours_until_start=FULL_REFUND_MIN_HOURS),
    make_booking(
        "CW-2030",
        hours_until_start=BETWEEN_REFUND_LIMITS_HOURS,
        rental_price_eur=EXPENSIVE_RENTAL_PRICE_EUR,
        deposit_eur=HIGH_DEPOSIT_EUR,
    ),
    make_booking("CW-2024", hours_until_start=HALF_REFUND_MIN_HOURS),
    make_booking("CW-2006", hours_until_start=UNDER_HALF_REFUND_HOURS),
    make_booking(
        "CW-2035",
        hours_until_start=BETWEEN_REFUND_LIMITS_HOURS,
        rental_price_eur=ODD_RENTAL_PRICE_EUR,
    ),
    make_booking("CW-2099", paid_with="voucher"),
    make_booking("CW-3001", status="cancelled"),
    make_booking("CW-3002", status="completed"),
    make_booking("CW-3003", status="in_progress"),
]


@pytest.fixture(autouse=True)
def mock_bookings(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    bookings = {b["id"]: b for b in MOCK_BOOKINGS}
    monkeypatch.setattr(tools, "load_bookings", lambda: bookings)
    return bookings
